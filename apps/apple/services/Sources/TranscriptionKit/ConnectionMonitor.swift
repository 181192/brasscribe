import Foundation
import Observation

/// Keeps this device connected to its paired computer while the app is in the foreground:
/// a heartbeat every 20 s (one request: `GET /v1/devices/me` for a paired device, `GET /v1/health` without a
/// credential), a silent move to the engine's new address (the last address first, then the network by server id),
/// monthly token rotation, "pair again" only on 401 from the paired engine itself, and "update" when the engine's
/// interface version is not this app's (then the heartbeat is all it is asked).
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
        case .mismatch(let n, let update): m.handle(.mismatch(serverName: n, update), at: t)
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

    enum Check: Equatable { case ok(EngineRecord), unauthorized, unreachable, otherServer, mismatch(InterfaceMatch.Update) }

    /// One heartbeat: the last address, then the network by server id. Returns the delay to the next one.
    @discardableResult
    public func heartbeat() async -> TimeInterval? {
        defer { checks += 1 }
        guard var r = record ?? localRecord() else { return machine.handle(.forgotten, at: now()) }
        var address = r.lastAddress
        var (result, service) = await check(r, at: address)
        switch result {
        case .unreachable, .otherServer:
            if !r.isProvisional, let found = await find(r.serverID), found.absoluteString != r.lastAddress {
                address = found.absoluteString
                (result, service) = await check(r, at: address)
            }
        case .ok, .unauthorized, .mismatch: break   // the engine itself answered: nothing to look for
        }
        if staged { return nil }
        switch result {
        case .ok(let updated):
            r = updated
            r.lastOK = now()
            if let service { r = await rotateIfDue(r, with: service) }
            remember(r)
            lastSeen = r.lastOK
            return machine.handle(.heartbeatOK(serverName: r.serverName), at: now())
        case .unauthorized:
            return machine.handle(.unauthorized, at: now())
        case .mismatch(let update):
            // Nothing is rotated, and the credential is as it was when the computer answers with this app's version.
            // Only a new address is kept: what the app asks next goes to the engine that answered, and gets "update",
            // not to the old address and "can't reach".
            if record != nil, address != r.lastAddress {
                r.lastAddress = address
                remember(r)
            }
            lastSeen = now()
            return machine.handle(.mismatch(serverName: r.serverName, update), at: now())
        case .unreachable, .otherServer:
            if record == nil { return machine.handle(.forgotten, at: now()) }   // no engine on this Mac
            return machine.handle(.heartbeatFailed, at: now())
        }
    }

    /// Brasscribe on this same computer answers without pairing.
    private func localRecord() -> EngineRecord? {
        localAddress.map { EngineRecord(serverID: "", serverName: "", token: nil, lastAddress: $0.absoluteString) }
    }

    /// One heartbeat at one address, and the service it went through. A paired device asks `GET /v1/devices/me`,
    /// which says in one answer which engine this is, whether the credential still works and the engine's interface
    /// version (Bandroom may have been updated since the last one). `GET /v1/health` is asked without a credential,
    /// and when the engine accepts the credential but not as a device (404). Which engine answers is settled before
    /// its interface version is looked at: another engine at the old address is not there, whatever its version, and
    /// neither is an answer that is no engine's (a network's sign-in page): the network is searched for ours.
    func check(_ r: EngineRecord, at address: String) async -> (Check, CompanionService?) {
        guard let url = URL(string: address) else { return (.unreachable, nil) }
        let svc = CompanionService(baseURL: url, token: r.token, session: session)
        var out = r
        out.lastAddress = address
        // the engine this record is for; none yet for Brasscribe on this same computer
        let ours = r.isProvisional ? nil : r.serverID
        // without a device entry, health is the whole heartbeat
        func fromHealth() async -> Check {
            let h: CompanionService.Health
            do { h = try await svc.health(timeout: 5, from: ours) }
            catch TranscriptionError.interfaceMismatch(let update) { return .mismatch(update) }
            catch { return .unreachable }
            // Brasscribe on this same computer trusts loopback; an engine that wants pairing is not it
            if r.token == nil, h.authRequired { return .unreachable }
            if let ours, h.serverID != ours { return .otherServer }
            if case .mismatch(let update) = InterfaceMatch.of(engine: h.interfaceVersion) { return .mismatch(update) }
            out.serverID = h.serverID
            out.serverName = h.serverName
            return .ok(out)
        }
        if r.token == nil { return (await fromHealth(), svc) }
        do {
            let me = try await svc.thisDevice(from: ours)
            if let ours, me.serverID != ours { return (.otherServer, svc) }
            if case .mismatch(let update) = InterfaceMatch.of(engine: me.interfaceVersion) { return (.mismatch(update), svc) }
            out.serverID = me.serverID
            out.deviceID = me.deviceID
            out.rotateAfter = me.rotateAfter
            // a credential moved from the old plain storage has no engine name yet; health has it
            if out.serverName.isEmpty, let h = try? await svc.health(timeout: 5) { out.serverName = h.serverName }
            return (.ok(out), svc)
        } catch TranscriptionError.notPaired {
            // 401 is "pair again" only from the engine that gave the credential, and health says which engine answers.
            // Another engine at the old address never had it, and one that health does not reach is not there. With
            // another interface version the update comes first: pairing would be refused until then.
            do {
                let h = try await svc.health(timeout: 5, from: ours)
                if let ours, h.serverID != ours { return (.otherServer, svc) }
                if case .mismatch(let update) = InterfaceMatch.of(engine: h.interfaceVersion) { return (.mismatch(update), svc) }
                return (.unauthorized, svc)
            } catch TranscriptionError.interfaceMismatch(let update) {
                return (.mismatch(update), svc)
            } catch {
                return (.unreachable, svc)
            }
        } catch TranscriptionError.http(404, _) {
            // loopback, or a static engine token: accepted without a device entry
            return (await fromHealth(), svc)
        } catch TranscriptionError.interfaceMismatch(let update) {
            return (.mismatch(update), svc)
        } catch {
            return (.unreachable, svc)
        }
    }

    /// Through the service the heartbeat just used: it already knows the engine's interface version is this app's.
    private func rotateIfDue(_ r: EngineRecord, with service: CompanionService) async -> EngineRecord {
        guard r.rotationDue(now: now()), r.token != nil else { return r }
        guard let token = try? await service.rotate() else { return r }
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
    public func adopt(_ result: CompanionService.PairResult, address: URL) {
        let r = EngineRecord(serverID: result.serverID, serverName: result.serverName, deviceID: result.deviceID,
                             token: result.token, lastAddress: address.absoluteString, lastOK: now())
        if let old = record, old.isProvisional { try? store.delete(serverID: "") }
        try? store.save(r)
        record = r
        staged = false
        active = true
        machine = ConnectionMachine()
        schedule(machine.handle(.start(serverName: r.serverName), at: now()))
    }

    /// Unpair: tell the computer (when it can be reached) and forget the credential here. A computer with another
    /// interface version is told nothing: the credential is forgotten on this device only.
    public func forget() async {
        guard let r = record else { return }
        if let url = r.baseURL, r.token != nil, state.kind != .mismatch {
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
    /// Without a code in the link, returns the address to ask for approval at. Throws `.interfaceMismatch` when that
    /// engine's interface version is not this app's.
    public func pair(link: PairingLink, deviceName: String, platform: String) async throws -> URL? {
        var lastError: Error = TranscriptionError.unreachable("")
        for url in link.baseURLs {
            let svc = CompanionService(baseURL: url, session: session)
            let h: CompanionService.Health
            do { h = try await svc.health(timeout: 4, from: link.serverID) }
            catch TranscriptionError.interfaceMismatch(let update) { throw TranscriptionError.interfaceMismatch(update) }
            catch { continue }   // nothing there, or not an engine's answer: the link's next address
            if h.serverID != link.serverID { continue }
            // the right computer with another interface version: no pair request, with a code or by asking it
            if case .mismatch(let update) = InterfaceMatch.of(engine: h.interfaceVersion) { throw TranscriptionError.interfaceMismatch(update) }
            guard let code = link.code else { return url }
            do {
                let result = try await svc.pair(code: code, deviceName: deviceName, platform: platform)
                adopt(result, address: url)
                return nil
            } catch { lastError = error }
        }
        throw lastError
    }
}
