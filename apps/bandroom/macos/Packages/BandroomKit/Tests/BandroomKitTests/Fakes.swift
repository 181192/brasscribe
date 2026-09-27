import Foundation
@testable import BandroomKit

/// An in-memory engine: records calls, returns what the test sets.
final class FakeEngine: EngineAPI, @unchecked Sendable {
    private let lock = NSLock()
    private var _calls: [String] = []
    var calls: [String] { lock.withLock { _calls } }

    var healthValue = Health(version: "0.9.4", device: "mps", serverId: "3f9c2a7e00000000000000000000abcd", serverName: "Brasscribe on Kalli's MacBook")
    var statusValue = EngineStatus(serverId: "3f9c2a7e00000000000000000000abcd", serverName: "Brasscribe on Kalli's MacBook",
                                   version: "0.9.4", onlineDevices: 2, pairedDevices: 3, pairingOpen: false, jobsRunning: 0, jobsQueued: 0)
    var devicesValue: [DeviceInfo] = []
    var jobsValue: [Job] = []
    var requestsValue: [PairRequestInfo] = []
    var pairingValue = PairingState(open: false, code: nil, serverId: "3f9c2a7e00000000000000000000abcd",
                                    serverName: "Brasscribe on Kalli's MacBook", hosts: ["192.168.1.20:8765"],
                                    uri: "brasscribe://pair?v=1&id=3f9c")
    var opened: [PairingOpen] = []
    var decideError: EngineError?
    var failAll = false
    var nextCode = 482913

    private func record(_ s: String) throws {
        lock.withLock { _calls.append(s) }
        if failAll { throw EngineError.unreachable }
    }

    func health() async throws -> Health { try record("health"); return healthValue }
    func status() async throws -> EngineStatus { try record("status"); return statusValue }
    func devices() async throws -> [DeviceInfo] { try record("devices"); return devicesValue }
    func removeDevice(id: String) async throws {
        try record("remove \(id)")
        devicesValue.removeAll { $0.deviceId == id }
    }
    func pairing() async throws -> PairingState { try record("pairing"); return pairingValue }
    func openPairing(_ body: PairingOpen) async throws -> PairingState {
        try record(body.extend ? "extend" : "open")
        opened.append(body)
        if !body.extend {
            pairingValue.open = true
            pairingValue.code = String(nextCode)
            nextCode += 1
            pairingValue.expiresAt = body.ttlSeconds == nil ? nil : "2026-09-27T12:10:00+00:00"
        } else {
            pairingValue.expiresAt = "2026-09-27T12:20:00+00:00"
        }
        return pairingValue
    }
    func closePairing() async throws -> PairingState {
        try record("close")
        pairingValue.open = false
        pairingValue.code = nil
        return pairingValue
    }
    func pairingRequests() async throws -> [PairRequestInfo] { try record("requests"); return requestsValue }
    func decide(requestId: String, approve: Bool) async throws -> PairRequestInfo {
        try record("\(approve ? "approve" : "deny") \(requestId)")
        if let decideError { throw decideError }
        var r = requestsValue.first { $0.requestId == requestId }!
        r.status = approve ? "approved" : "denied"
        requestsValue.removeAll { $0.requestId == requestId }
        return r
    }
    func jobs() async throws -> [Job] { try record("jobs"); return jobsValue }
}

/// A launcher that starts nothing; the test decides when the "process" exits.
final class FakeLauncher: ProcessLauncher, @unchecked Sendable {
    private let lock = NSLock()
    var launched: [LaunchPlan] = []
    var terminated: [Int32] = []
    var exits: [Int32: @Sendable (Int32) -> Void] = [:]
    var nextPid: Int32 = 4000
    var failWith: LaunchFailure?

    func launch(_ plan: LaunchPlan, onExit: @escaping @Sendable (Int32) -> Void) throws -> Int32 {
        try lock.withLock {
            if let failWith { throw failWith }
            nextPid += 1
            launched.append(plan)
            exits[nextPid] = onExit
            return nextPid
        }
    }

    func terminate(pid: Int32, grace: TimeInterval) {
        let exit = lock.withLock { () -> (@Sendable (Int32) -> Void)? in
            terminated.append(pid)
            return exits.removeValue(forKey: pid)
        }
        exit?(15)
    }

    /// Simulates a crash of the current process.
    func crash(_ pid: Int32, status: Int32 = 256) {
        let exit = lock.withLock { exits.removeValue(forKey: pid) }
        exit?(status)
    }
}

/// A clock the test moves by hand.
final class TestClock: @unchecked Sendable {
    var now = Date(timeIntervalSince1970: 1_790_000_000)
    func advance(_ s: TimeInterval) { now = now.addingTimeInterval(s) }
}

func tempDir() -> URL {
    let url = FileManager.default.temporaryDirectory.appending(path: "bandroom-tests-\(UUID().uuidString)")
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

/// Lets queued main-actor tasks run.
@MainActor
func settle(_ rounds: Int = 20) async {
    for _ in 0..<rounds { await Task.yield() }
}
