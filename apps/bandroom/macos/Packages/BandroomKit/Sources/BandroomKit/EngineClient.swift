import Foundation

public enum EngineError: Error, Equatable, Sendable {
    /// Nothing answers on the port (not started yet, or stopped).
    case unreachable
    /// HTTP error; `retryAfter` from the Retry-After header on 429.
    case http(status: Int, retryAfter: Double?)
    case decoding(String)

    public var isNotFound: Bool { if case .http(404, _) = self { true } else { false } }
}

/// What Bandroom asks of the engine. All calls go to loopback with the admin bearer token.
public protocol EngineAPI: Sendable {
    func health() async throws -> Health
    /// GET /v1/status, or the same numbers put together from older endpoints when the engine predates it.
    func status() async throws -> EngineStatus
    func devices() async throws -> [DeviceInfo]
    func removeDevice(id: String) async throws
    func pairing() async throws -> PairingState
    func openPairing(_ body: PairingOpen) async throws -> PairingState
    func closePairing() async throws -> PairingState
    func pairingRequests() async throws -> [PairRequestInfo]
    func decide(requestId: String, approve: Bool) async throws -> PairRequestInfo
    func jobs() async throws -> [Job]
}

public final class EngineClient: EngineAPI, @unchecked Sendable {
    public let baseURL: URL
    private let token: String?
    private let session: URLSession
    private let now: @Sendable () -> Date

    public init(port: Int, token: String?, session: URLSession? = nil, now: @escaping @Sendable () -> Date = Date.init) {
        self.baseURL = URL(string: "http://127.0.0.1:\(port)")!
        self.token = token
        self.now = now
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.ephemeral
            config.timeoutIntervalForRequest = 5
            config.connectionProxyDictionary = [:]
            self.session = URLSession(configuration: config)
        }
    }

    // MARK: requests

    func request(_ method: String, _ path: String, body: Data? = nil) -> URLRequest {
        var r = URLRequest(url: baseURL.appending(path: path))
        r.httpMethod = method
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token { r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body {
            r.httpBody = body
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return r
    }

    func send(_ req: URLRequest) async throws -> Data {
        let data: Data, response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw EngineError.unreachable
        }
        guard let http = response as? HTTPURLResponse else { throw EngineError.unreachable }
        guard (200..<300).contains(http.statusCode) else {
            let retry = http.value(forHTTPHeaderField: "Retry-After").flatMap(Double.init)
            throw EngineError.http(status: http.statusCode, retryAfter: retry)
        }
        return data
    }

    func get<T: Decodable>(_ path: String, as: T.Type = T.self) async throws -> T {
        try decode(try await send(request("GET", path)))
    }

    func decode<T: Decodable>(_ data: Data) throws -> T {
        do { return try JSONDecoder().decode(T.self, from: data) } catch { throw EngineError.decoding(String(describing: error)) }
    }

    // MARK: EngineAPI

    public func health() async throws -> Health { try await get("/v1/health") }

    public func status() async throws -> EngineStatus {
        do {
            return try await get("/v1/status")
        } catch let e as EngineError where e.isNotFound {
            return try await composedStatus()
        }
    }

    /// For engines without /v1/status: the same figures from health, devices, pairing and jobs.
    func composedStatus() async throws -> EngineStatus {
        async let h = health()
        async let d = devices()
        async let p = pairing()
        async let j = jobs()
        let (health, devices, pairing, jobs) = try await (h, d, p, j)
        let t = now()
        return EngineStatus(serverId: health.serverId, serverName: health.serverName, version: health.version,
                            onlineDevices: devices.filter { $0.isOnline(now: t) }.count, pairedDevices: devices.count,
                            pairingOpen: pairing.open, jobsRunning: jobs.filter { $0.status == "running" }.count,
                            jobsQueued: jobs.filter { $0.status == "queued" }.count)
    }

    public func devices() async throws -> [DeviceInfo] { try await get("/v1/devices") }

    public func removeDevice(id: String) async throws {
        _ = try await send(request("DELETE", "/v1/devices/\(id)"))
    }

    public func pairing() async throws -> PairingState { try await get("/v1/pairing") }

    public func openPairing(_ body: PairingOpen) async throws -> PairingState {
        let data = try JSONEncoder().encode(body)
        return try decode(try await send(request("POST", "/v1/pairing", body: data)))
    }

    public func closePairing() async throws -> PairingState {
        try decode(try await send(request("DELETE", "/v1/pairing")))
    }

    public func pairingRequests() async throws -> [PairRequestInfo] { try await get("/v1/pairing/requests") }

    public func decide(requestId: String, approve: Bool) async throws -> PairRequestInfo {
        try decode(try await send(request("POST", "/v1/pairing/requests/\(requestId)/\(approve ? "approve" : "deny")")))
    }

    public func jobs() async throws -> [Job] { try await get("/v1/jobs") }
}
