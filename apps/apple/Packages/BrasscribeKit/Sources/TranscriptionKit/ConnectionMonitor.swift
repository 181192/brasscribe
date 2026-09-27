import Foundation
import Observation

/// Keeps this device connected to its paired computer while the app is in the foreground:
/// a `GET /v1/devices/me` heartbeat every 20 s, a silent move to the engine's new address (the last
/// address first, then the network by server id), monthly token rotation, and "pair again" only on 401.
/// The state logic lives in `ConnectionMachine`; this class adds the timers and the network.
@MainActor @Observable
public final class ConnectionMonitor {
    public private(set) var machine = ConnectionMachine()
    public var state: ConnectionState { machine.state }
    /// The engine this device works with (the most recently reached one when several are stored).
    public private(set) var record: EngineRecord?
    /// When the last heartbeat was answered.
    public private(set) var lastSeen: Date?
    /// True while showing a staged state (screenshots): no heartbeats run.
    public private(set) var staged = false
    /// Heartbeats done since launch; the first result is not announced.
    public private(set) var checks = 0

    /// An address for loopback use without pairing (Brasscribe on this same Mac).
    public var localAddress: URL?

    @ObservationIgnored let store: CredentialStore
    @ObservationIgnored let session: URLSession
    @ObservationIgnored let find: @MainActor (String) async -> URL?
    @ObservationIgnored let now: () -> Date
    @ObservationIgnored private var loop: Task<Void, Never>?
    @ObservationIgnored private var active = false

    public init(store: CredentialStore, session: URLSession = .shared,
                find: @escaping @MainActor (String) async -> URL? = { id in await EngineBrowser().find(serverID: id) },
                now: @escaping () -> Date = Date.init) {
        self.store = store; self.session = session; self.find = find; self.now = now
        record = Self.pick((try? store.all()) ?? [])
        // with a stored engine, the first thing to show is "Looking for …", never "Not connected"
        if let record, record.token != nil { machine = ConnectionMachine(state: .reconnecting(serverName: record.serverName)) }
    }

    /// The record to use: the last one that answered, else any.
    static func pick(_ records: [EngineRecord]) -> EngineRecord? {
        records.max { ($0.lastOK ?? .distantPast, $0.serverID) < ($1.lastOK ?? .distantPast, $1.serverID) }
    }

    public var serverName: String { record?.serverName ?? "" }

    // MARK: lifecycle

    /// Launch or back in the foreground.
    public func resume() {
        guard !staged else { return }
        active = true
        if let record {
            schedule(machine.handle(.start(serverName: record.serverName), at: now()))
        } else if localAddress != nil {
            schedule(0)
        } else {
            machine.handle(.forgotten, at: now())
        }
    }

    /// In the background: no heartbeats.
    public func suspend() {
        active = false
        loop?.cancel(); loop = nil
        machine.handle(.suspended, at: now())
    }

    /// Whether "Connect" can try right away (a paired engine, or Brasscribe on this same computer);
    /// otherwise it means pairing.
    public var canConnect: Bool { record != nil || localAddress != nil }

    /// "Connect", from the offline row.
    public func connect() {
        guard !staged, canConnect else { return }
        active = true
        schedule(machine.handle(.connectRequested(serverName: record?.serverName ?? ""), at: now()))
    }

    /// The network changed, or a request just failed: check now instead of waiting.
    public func poke() {
        guard !staged, active, record != nil || localAddress != nil else { return }
        if case .needsPairing = state { return }
        if case .offline = state { connect(); return }
        schedule(0)
    }

    /// Show a state without talking to anything (screenshots and UI tests).
    public func stage(_ state: ConnectionState, record: EngineRecord?) {
        staged = true
        loop?.cancel(); loop = nil
        self.record = record
        lastSeen = record?.lastOK
        var m = ConnectionMachine()
        let t = now()
        switch state {
        case .connected(let n): m.handle(.heartbeatOK(serverName: n), at: t)
        case .reconnecting(let n): m.handle(.start(serverName: n), at: t)
        case .offline: m.handle(.forgotten, at: t)
        case .needsPairing(let n): m.handle(.start(serverName: n), at: t); m.handle(.unauthorized, at: t)
        }
        machine = m
    }

    private func schedule(_ delay: TimeInterval?) {
        loop?.cancel(); loop = nil
        guard let delay, active else { return }
        loop = Task { [weak self] in
            var next: TimeInterval? = delay
            while let d = next, !Task.isCancelled {
                if d > 0 { try? await Task.sleep(for: .seconds(d)) }
                guard !Task.isCancelled, let self else { return }
                next = await self.heartbeat()
            }
        }
    }

    // MARK: heartbeat

    enum Check: Equatable { case ok(EngineRecord), unauthorized, unreachable, otherServer }

    /// One heartbeat: the last address, then the network by server id. Returns the delay to the next one.
    @discardableResult
    public func heartbeat() async -> TimeInterval? {
        defer { checks += 1 }
        guard var r = record ?? localRecord() else { return machine.handle(.forgotten, at: now()) }
        var result = await check(r, at: r.lastAddress)
        if case .ok = result {} else if result != .unauthorized, !r.isProvisional, let found = await find(r.serverID),
                                         found.absoluteString != r.lastAddress {
            result = await check(r, at: found.absoluteString)
        }
        if staged { return nil }
        switch result {
        case .ok(let updated):
            r = updated
            r.lastOK = now()
            r = await rotateIfDue(r)
            remember(r)
            lastSeen = r.lastOK
            return machine.handle(.heartbeatOK(serverName: r.serverName), at: now())
        case .unauthorized:
            return machine.handle(.unauthorized, at: now())
        case .unreachable, .otherServer:
            if record == nil { return machine.handle(.forgotten, at: now()) }   // no engine on this Mac
            return machine.handle(.heartbeatFailed, at: now())
        }
    }

    /// Brasscribe on this same computer answers without pairing.
    private func localRecord() -> EngineRecord? {
        localAddress.map { EngineRecord(serverID: "", serverName: "", token: nil, lastAddress: $0.absoluteString) }
    }

    func check(_ r: EngineRecord, at address: String) async -> Check {
        guard let url = URL(string: address) else { return .unreachable }
        let svc = CompanionService(baseURL: url, token: r.token, session: session)
        var out = r
        out.lastAddress = address
        if r.token == nil {
            // Brasscribe on this same computer trusts loopback: its heartbeat is /v1/health
            guard let h = try? await svc.health(timeout: 5), !h.authRequired else { return .unreachable }
            if let id = h.serverID {
                if !r.isProvisional, id != r.serverID { return .otherServer }
                out.serverID = id
            }
            if let n = h.serverName { out.serverName = n }
            return .ok(out)
        }
        do {
            let me = try await svc.thisDevice()
            if !r.isProvisional, me.serverID != r.serverID { return .otherServer }
            out.serverID = me.serverID
            out.deviceID = me.deviceID
            out.rotateAfter = me.rotateAfter
            if out.serverName.isEmpty || r.isProvisional, let h = try? await svc.health(timeout: 5), let n = h.serverName { out.serverName = n }
            return .ok(out)
        } catch TranscriptionError.notPaired {
            return .unauthorized
        } catch TranscriptionError.http(404, _) {
            // loopback, or a static engine token: accepted without a device entry
            guard let h = try? await svc.health(timeout: 5) else { return .unreachable }
            if let id = h.serverID {
                if !r.isProvisional, id != r.serverID { return .otherServer }
                out.serverID = id
            }
            if let n = h.serverName { out.serverName = n }
            return .ok(out)
        } catch {
            return .unreachable
        }
    }

    private func rotateIfDue(_ r: EngineRecord) async -> EngineRecord {
        guard r.rotationDue(now: now()), r.token != nil, let url = r.baseURL else { return r }
        guard let token = try? await CompanionService(baseURL: url, token: r.token, session: session).rotate() else { return r }
        var out = r
        out.token = token
        out.rotateAfter = now().addingTimeInterval(30 * 86_400)
        // the new token is written before anything uses it
        try? store.save(out)
        return out
    }

    /// Store a record under its server id, replacing a provisional one it came from.
    private func remember(_ r: EngineRecord) {
        if r.token == nil && (record == nil || record?.token == nil) { record = r; return }   // same computer, no pairing: nothing to keep
        if let old = record, old.isProvisional, !r.isProvisional { try? store.delete(serverID: "") }
        try? store.save(r)
        record = r
    }

    // MARK: pairing

    /// After pairing: keep the credential and start the heartbeat.
    public func adopt(_ result: CompanionService.PairResult, address: URL, fallbackName: String = "") async {
        var r = EngineRecord(serverID: result.serverID ?? "", serverName: result.serverName ?? fallbackName, deviceID: result.deviceID,
                             token: result.token, lastAddress: address.absoluteString, lastOK: now())
        if r.serverID.isEmpty || r.serverName.isEmpty,
           let h = try? await CompanionService(baseURL: address, session: session).health(timeout: 5) {
            if r.serverID.isEmpty, let id = h.serverID { r.serverID = id }
            if r.serverName.isEmpty, let n = h.serverName { r.serverName = n }
        }
        if let old = record, old.isProvisional { try? store.delete(serverID: "") }
        try? store.save(r)
        record = r
        staged = false
        active = true
        machine = ConnectionMachine()
        schedule(machine.handle(.start(serverName: r.serverName), at: now()))
    }

    /// Unpair: tell the computer (when it can be reached) and forget the credential here.
    public func forget() async {
        guard let r = record else { return }
        if let url = r.baseURL, r.token != nil {
            try? await CompanionService(baseURL: url, token: r.token, session: session).unpair()
        }
        try? store.delete(serverID: r.serverID)
        loop?.cancel(); loop = nil
        record = Self.pick((try? store.all()) ?? [])
        lastSeen = nil
        machine = ConnectionMachine()
        if let next = record { schedule(machine.handle(.start(serverName: next.serverName), at: now())) }
        else { machine.handle(.forgotten, at: now()) }
    }

    /// Pair from a scanned or pasted link: the first address that answers as the right engine gets the code.
    /// Without a code in the link, returns the address to ask for approval at.
    public func pair(link: PairingLink, deviceName: String, platform: String) async throws -> URL? {
        var lastError: Error = TranscriptionError.unreachable("")
        for url in link.baseURLs {
            let svc = CompanionService(baseURL: url, session: session)
            guard let h = try? await svc.health(timeout: 4) else { continue }
            if let id = h.serverID, id != link.serverID { continue }
            guard let code = link.code else { return url }
            do {
                let result = try await svc.pair(code: code, deviceName: deviceName, platform: platform)
                await adopt(result, address: url, fallbackName: link.serverName)
                return nil
            } catch { lastError = error }
        }
        throw lastError
    }
}
