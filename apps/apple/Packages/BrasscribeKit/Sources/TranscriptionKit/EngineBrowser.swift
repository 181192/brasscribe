import Foundation
import Network
import Observation

/// Finds engines on the local network that advertise `_brasscribe._tcp` (`brasscribe serve --lan`).
/// Discovery only suggests addresses; the engine still requires pairing. The TXT record carries the
/// engine's stable `id` (matched against a stored credential) and `host`, the computer's own name.
@MainActor @Observable
public final class EngineBrowser {
    public static let serviceType = "_brasscribe._tcp"

    public struct Engine: Identifiable, Hashable, Sendable {
        /// The mDNS instance name ("Brasscribe on Studio", maybe with " (2)" after a name clash).
        public let name: String
        /// The engine's stable server id, from TXT `id`; nil for engines too old to send it.
        public var serverID: String?
        /// The computer's name, from TXT `host`.
        public var host: String?
        public var id: String { name }

        public init(name: String, serverID: String? = nil, host: String? = nil) {
            self.name = name; self.serverID = serverID; self.host = host
        }

        /// The computer's name for sentences such as "Brasscribe on {computer}".
        public var computerName: String { host ?? EngineRecord.computerName(fromServerName: name) }
    }

    public private(set) var engines: [Engine] = []
    /// Why browsing is not working, e.g. local network access was declined.
    public private(set) var problem: String?

    private var browser: NWBrowser?
    private var endpoints: [String: NWEndpoint] = [:]

    public init() {}

    public func start() {
        // unit tests render the pairing views; browsing would ask for local network access
        guard browser == nil, ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil else { return }
        let b = NWBrowser(for: .bonjourWithTXTRecord(type: Self.serviceType, domain: nil), using: .tcp)
        b.browseResultsChangedHandler = { [weak self] results, _ in
            let found = results.map { r -> (NWEndpoint, [String: String]) in
                if case let .bonjour(txt) = r.metadata { return (r.endpoint, txt.dictionary) }
                return (r.endpoint, [:])
            }
            MainActor.assumeIsolated { self?.update(found) }
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

    private func update(_ found: [(NWEndpoint, [String: String])]) {
        endpoints = [:]
        var list: [Engine] = []
        for (endpoint, txt) in found {
            guard case let .service(name, _, _, _) = endpoint else { continue }
            endpoints[name] = endpoint
            list.append(Engine(name: name, serverID: txt["id"].flatMap { $0.isEmpty ? nil : $0 },
                               host: txt["host"].flatMap { $0.isEmpty ? nil : $0 }))
        }
        engines = list.sorted { $0.name < $1.name }
    }

    /// Browses (if not already) until the engine with this server id shows up, then resolves its address.
    /// Nil when it hasn't appeared within `timeout`.
    public func find(serverID: String, timeout: TimeInterval = 5) async -> URL? {
        let wasRunning = browser != nil
        start()
        defer { if !wasRunning { stop() } }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline, !Task.isCancelled {
            if let e = engines.first(where: { $0.serverID == serverID }) { return try? await resolve(e) }
            try? await Task.sleep(for: .milliseconds(250))
        }
        return nil
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
