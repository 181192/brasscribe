import Foundation
import Network
import Observation

/// Finds engines on the local network that advertise `_brasscribe._tcp` (`brasscribe serve --lan`).
/// Discovery only suggests addresses; the engine still requires pairing.
@MainActor @Observable
public final class EngineBrowser {
    public static let serviceType = "_brasscribe._tcp"

    public struct Engine: Identifiable, Hashable, Sendable {
        public let name: String
        public var id: String { name }
    }

    public private(set) var engines: [Engine] = []
    /// Why browsing is not working, e.g. local network access was declined.
    public private(set) var problem: String?

    private var browser: NWBrowser?
    private var endpoints: [String: NWEndpoint] = [:]

    public init() {}

    public func start() {
        guard browser == nil else { return }
        let b = NWBrowser(for: .bonjour(type: Self.serviceType, domain: nil), using: .tcp)
        b.browseResultsChangedHandler = { [weak self] results, _ in
            MainActor.assumeIsolated { self?.update(results.map(\.endpoint)) }
        }
        b.stateUpdateHandler = { [weak self] state in
            MainActor.assumeIsolated {
                switch state {
                case .waiting(let e), .failed(let e): self?.problem = e.localizedDescription
                case .ready: self?.problem = nil
                default: break
                }
            }
        }
        b.start(queue: .main)
        browser = b
    }

    public func stop() {
        browser?.cancel()
        browser = nil
    }

    private func update(_ found: [NWEndpoint]) {
        endpoints = [:]
        for endpoint in found {
            if case let .service(name, _, _, _) = endpoint { endpoints[name] = endpoint }
        }
        engines = endpoints.keys.sorted().map(Engine.init(name:))
    }

    /// The engine's base URL, resolved to an IPv4 address and port.
    public func resolve(_ engine: Engine) async throws -> URL {
        guard let endpoint = endpoints[engine.name] else { throw URLError(.cannotFindHost) }
        let params = NWParameters.tcp
        (params.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options)?.version = .v4
        let connection = NWConnection(to: endpoint, using: params)
        let queue = DispatchQueue(label: "EngineBrowser.resolve")
        let once = Once()
        return try await withCheckedThrowingContinuation { cont in
            connection.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    if case let .hostPort(host, port)? = connection.currentPath?.remoteEndpoint,
                       let url = Self.url(host: host, port: port.rawValue) {
                        once.run { cont.resume(returning: url) }
                    } else {
                        once.run { cont.resume(throwing: URLError(.cannotFindHost)) }
                    }
                    connection.cancel()
                case .waiting(let e), .failed(let e):
                    once.run { cont.resume(throwing: e) }
                    connection.cancel()
                default: break
                }
            }
            connection.start(queue: queue)
        }
    }

    nonisolated static func url(host: NWEndpoint.Host, port: UInt16) -> URL? {
        let text: String
        switch host {
        case .ipv4(let a): text = a.rawValue.map(String.init).joined(separator: ".")
        case .ipv6(let a): text = "[\("\(a)".split(separator: "%").first ?? "")]"
        case .name(let n, _): text = n
        @unknown default: return nil
        }
        return URL(string: "http://\(text):\(port)")
    }
}

/// Guards a continuation against the connection reporting more than one terminal state.
private final class Once: @unchecked Sendable {
    private var done = false
    private let lock = NSLock()

    func run(_ body: () -> Void) {
        lock.lock(); defer { lock.unlock() }
        guard !done else { return }
        done = true
        body()
    }
}
