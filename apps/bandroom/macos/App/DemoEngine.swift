#if DEBUG
import BandroomKit
import Foundation

/// Canned engine answers for screenshots (BANDROOM_DEMO=busy|idle): the mockup's band, no engine running.
final class DemoEngine: EngineAPI, @unchecked Sendable {
    let busy: Bool
    private let lock = NSLock()
    private var pairingOpen = false

    init(busy: Bool) { self.busy = busy }

    private static let serverId = "3f9c2a7e5b1d4c8a9e0f1a2b3c4d5e6f"
    private static let name = "Brasscribe on Kalli's MacBook"

    private static func iso(_ ago: TimeInterval) -> String {
        ISO8601DateFormatter().string(from: Date().addingTimeInterval(-ago))
    }

    func health() async throws -> Health {
        Health(version: "0.9.4", device: "mps", serverId: Self.serverId, serverName: Self.name)
    }

    func status() async throws -> EngineStatus {
        EngineStatus(serverId: Self.serverId, serverName: Self.name, version: "0.9.4", onlineDevices: busy ? 2 : 1,
                     pairedDevices: 3, pairingOpen: lock.withLock { pairingOpen }, jobsRunning: busy ? 1 : 0, jobsQueued: busy ? 1 : 0)
    }

    func devices() async throws -> [DeviceInfo] {
        [DeviceInfo(deviceId: "a1", name: "Kari's iPhone", platform: "ios", pairedAt: Self.iso(86400 * 20), lastSeen: Self.iso(5), online: true),
         DeviceInfo(deviceId: "b2", name: "Jon's Pixel", platform: "android", pairedAt: Self.iso(86400 * 12), lastSeen: Self.iso(busy ? 10 : 86400 * 3),
                    online: busy),
         DeviceInfo(deviceId: "c3", name: "Band iPad", platform: "ipados", pairedAt: Self.iso(86400 * 40), lastSeen: Self.iso(86400 * 10), online: false)]
    }

    func removeDevice(id: String) async throws {}

    private func state(open: Bool) -> PairingState {
        PairingState(open: open, code: open ? "482913" : nil, serverId: Self.serverId, serverName: Self.name,
                     hosts: ["192.168.1.20:8765", "10.0.0.4:8765"],
                     uri: "brasscribe://pair?v=1&id=\(Self.serverId)&name=Brasscribe%20on%20Kalli%27s%20MacBook&h=192.168.1.20:8765,10.0.0.4:8765"
                        + (open ? "&code=482913" : ""))
    }

    func pairing() async throws -> PairingState { state(open: lock.withLock { pairingOpen }) }
    func openPairing(_ body: PairingOpen) async throws -> PairingState {
        lock.withLock { pairingOpen = true }
        return state(open: true)
    }
    func closePairing() async throws -> PairingState {
        lock.withLock { pairingOpen = false }
        return state(open: false)
    }
    func pairingRequests() async throws -> [PairRequestInfo] {
        ProcessInfo.processInfo.environment["BANDROOM_DEMO_REQUEST"] == nil ? []
            : [PairRequestInfo(requestId: "r1", name: "Kari's iPhone", platform: "ios", matchCode: "4719", createdAt: Self.iso(10))]
    }
    func decide(requestId: String, approve: Bool) async throws -> PairRequestInfo {
        PairRequestInfo(requestId: requestId, name: "Kari's iPhone", platform: "ios", matchCode: "4719", createdAt: Self.iso(10),
                        status: approve ? "approved" : "denied")
    }
    func jobs() async throws -> [Job] {
        guard busy else { return [] }
        let started = Date().timeIntervalSince1970 - 290
        return [Job(id: "j1", profile: "orchestra-with-soloist", title: "Old Hundredth", status: "running", created: started, started: started,
                    progress: 0.62, stages: [StageState(name: "beats", kind: "beats", status: "ran"),
                                             StageState(name: "stems", kind: "stems", status: "ran"),
                                             StageState(name: "contour", kind: "transcribe", status: "running")],
                    deviceName: "Kari's iPhone"),
                Job(id: "j2", profile: "solo", title: "Kari's solo", status: "queued", created: started + 60, progress: 0, stages: [])]
    }
}
#endif
