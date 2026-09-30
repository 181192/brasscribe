import Foundation
import Testing
@testable import BandroomKit

@MainActor
@Suite struct StatusMonitorTests {
    @Test func pollsEveryFiveSecondsWhileOpenAndThirtyWhileClosed() async {
        let engine = FakeEngine(), clock = TestClock()
        let m = StatusMonitor(now: { clock.now }, sleep: { _ in })
        m.client = engine
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 1)
        #expect(m.interval == 30)

        clock.advance(10)
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 1, "closed: not yet")

        m.isPanelOpen = true
        #expect(m.interval == 5)
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 2, "opening refreshes at once")

        clock.advance(3)
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 2)
        clock.advance(2)
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 3)

        m.isPanelOpen = false
        clock.advance(29)
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 3)
        clock.advance(1)
        await m.tick()
        #expect(engine.calls.filter { $0 == "status" }.count == 4)
    }

    @Test func pairingRequestsAreCheckedEveryThreeSecondsAndAnnouncedOnce() async {
        let engine = FakeEngine(), clock = TestClock()
        let m = StatusMonitor(now: { clock.now }, sleep: { _ in })
        var announced: [String] = []
        m.onNewRequest = { announced.append($0.name) }
        m.client = engine
        await m.tick()
        engine.requestsValue = [PairRequestInfo(requestId: "r1", name: "Kari's iPhone", platform: "ios", matchCode: "4719", createdAt: "")]
        clock.advance(3)
        await m.tick()
        clock.advance(3)
        await m.tick()
        #expect(announced == ["Kari's iPhone"])
        #expect(m.requests.map(\.matchCode) == ["4719"])
        #expect(engine.calls.filter { $0 == "requests" }.count == 3)
    }

    @Test func fetchesTheJobOnlyWhileSomethingIsBeingMade() async {
        let engine = FakeEngine(), clock = TestClock()
        let m = StatusMonitor(now: { clock.now }, sleep: { _ in })
        var running: [Int] = []
        m.onJobsChanged = { running.append($0) }
        m.client = engine
        await m.refresh()
        #expect(!engine.calls.contains("jobs"))
        #expect(m.job == nil)
        engine.statusValue.jobsRunning = 1
        engine.statusValue.jobsQueued = 1
        engine.jobsValue = [
            Job(id: "j1", profile: "solo", title: "Old Hundredth", status: "running", created: 0, started: clock.now.timeIntervalSince1970 - 300,
                progress: 0.62, stages: [StageState(name: "beats", kind: "beats", status: "ran"),
                                         StageState(name: "contour.solo", kind: "transcribe", status: "running")],
                deviceName: "Kari's iPhone"),
            Job(id: "j2", profile: "solo", title: "Next", status: "queued", created: 1, progress: 0, stages: []),
        ]
        await m.refresh()
        #expect(m.job == JobSummary(jobId: "j1", title: "Old Hundredth", deviceName: "Kari's iPhone", step: .transcribing, percent: 62, minutesLeft: 4, waiting: 1))
        #expect(running == [0, 1])
    }

    @Test func withoutAnEngineNothingIsBeingMade() async {
        let engine = FakeEngine()
        engine.statusValue.jobsRunning = 1
        engine.jobsValue = [Job(id: "j1", profile: "solo", title: "Old Hundredth", status: "running", created: 0, started: 0,
                                progress: 0.5, stages: [])]
        let m = StatusMonitor(sleep: { _ in })
        m.client = engine
        await m.refresh()
        #expect(m.status?.jobsRunning == 1)
        #expect(m.job != nil)
        m.client = nil
        #expect(m.status == nil)
        #expect(m.job == nil)
    }

    @Test func unreachableEngineIsNotReachable() async {
        let engine = FakeEngine()
        engine.failAll = true
        let m = StatusMonitor(sleep: { _ in })
        m.client = engine
        await m.refresh()
        #expect(!m.reachable)
        #expect(m.status == nil)
    }

    @Test func anEngineThatStopsAnsweringIsUnresponsiveAfterThreeChecks() async {
        let engine = FakeEngine()
        let m = StatusMonitor(sleep: { _ in })
        m.client = engine
        await m.refresh()
        engine.failAll = true
        await m.refresh()
        await m.refresh()
        #expect(!m.isUnresponsive, "two missed checks can be a busy moment")
        await m.refresh()
        #expect(m.isUnresponsive)
        engine.failAll = false
        await m.refresh()
        #expect(!m.isUnresponsive, "an answer clears it")
        engine.failAll = true
        for _ in 0..<3 { await m.refresh() }
        m.client = nil
        #expect(!m.isUnresponsive, "a new engine starts afresh")
    }

    @Test func connectedDevicesFirstThenByLastUse() {
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        let f = ISO8601DateFormatter()
        func d(_ id: String, ago: TimeInterval, online: Bool? = nil) -> DeviceInfo {
            DeviceInfo(deviceId: id, name: id, platform: "ios", pairedAt: f.string(from: now.addingTimeInterval(-9e5)),
                       lastSeen: f.string(from: now.addingTimeInterval(-ago)), online: online)
        }
        let list = StatusMonitor.ordered([d("old", ago: 86400 * 3), d("recent", ago: 3600), d("on", ago: 7200, online: true)], now: now)
        #expect(list.map(\.deviceId) == ["on", "recent", "old"])
    }

    @Test func removeAndExpiredRequests() async throws {
        let engine = FakeEngine()
        engine.devicesValue = [DeviceInfo(deviceId: "a", name: "Kari's iPhone", platform: "ios", pairedAt: "", lastSeen: "")]
        let m = StatusMonitor(sleep: { _ in })
        m.client = engine
        await m.refresh()
        try await m.removeDevice("a")
        #expect(engine.calls.contains("remove a"))
        #expect(m.devices.isEmpty)

        let r = PairRequestInfo(requestId: "r9", name: "Pixel", platform: "android", matchCode: "1234", createdAt: "")
        engine.requestsValue = [r]
        #expect(try await m.decide(r, approve: true))
        engine.decideError = .http(status: 404, retryAfter: nil)
        #expect(try await m.decide(r, approve: true) == false)
    }
}

@MainActor
@Suite struct PairingModelTests {
    @Test func opensForTenMinutesAndShowsTheCode() async {
        let engine = FakeEngine()
        let p = PairingModel(client: engine, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await p.open()
        #expect(p.phase == .open)
        #expect(engine.opened.first == PairingOpen(ttlSeconds: 600, singleUse: true, extend: false))
        #expect(p.code == "482913")
        #expect(p.displayCode == "482 913")
        #expect(p.host == "Kalli's MacBook")
        #expect(p.address?.ip == "192.168.1.20")
        #expect(p.address?.port == "8765")
        await p.close()
    }

    @Test func noticesTheNewPhone() async {
        let engine = FakeEngine()
        engine.devicesValue = [DeviceInfo(deviceId: "old", name: "Old iPad", platform: "ios", pairedAt: "", lastSeen: "")]
        let p = PairingModel(client: engine, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await p.open()
        p.startPolling()  // replaced by explicit polls below
        await p.close()
        await p.open()
        await p.poll()
        #expect(p.pairedDevice == nil)
        engine.devicesValue.append(DeviceInfo(deviceId: "new", name: "Kari's iPhone", platform: "ios", pairedAt: "", lastSeen: ""))
        engine.pairingValue.open = false  // single use: the code is spent
        await p.poll()
        #expect(p.pairedDevice == "Kari's iPhone")
        #expect(p.code == nil)

        await p.pairAnother()
        #expect(p.pairedDevice == nil)
        #expect(p.code == "482915")
        await p.close()
    }

    @Test func extendsTheWindowBeforeItRunsOut() async {
        let engine = FakeEngine(), clock = TestClock()
        clock.now = ISO8601DateFormatter().date(from: "2026-09-27T12:00:00Z")!
        let p = PairingModel(client: engine, now: { clock.now }, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await p.open()
        #expect(engine.pairingValue.expiresAt == "2026-09-27T12:10:00+00:00")
        await p.poll()
        #expect(!engine.calls.contains("extend"), "plenty of time left")
        clock.now = ISO8601DateFormatter().date(from: "2026-09-27T12:09:00Z")!
        await p.poll()
        #expect(engine.calls.contains("extend"))
        #expect(engine.opened.last == PairingOpen(ttlSeconds: 600, singleUse: true, extend: true))
        #expect(p.state?.expiresAt == "2026-09-27T12:20:00+00:00")
        await p.close()
    }

    @Test func showsTheLockout() async {
        let engine = FakeEngine(), clock = TestClock()
        clock.now = ISO8601DateFormatter().date(from: "2026-09-27T12:00:00Z")!
        let p = PairingModel(client: engine, now: { clock.now }, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await p.open()
        engine.pairingValue.lockedUntil = "2026-09-27T12:00:30+00:00"
        await p.poll()
        #expect(p.isLockedOut)
        clock.advance(31)
        await p.poll()
        #expect(!p.isLockedOut)
        await p.close()
    }

    @Test func closingClosesTheEnginesWindow() async {
        let engine = FakeEngine()
        let p = PairingModel(client: engine, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await p.open()
        await p.close()
        #expect(engine.calls.last == "close")
        #expect(p.phase == .idle)
    }

    @Test func closingWhileTheCodeIsBeingMadeClosesTheEnginesWindowAfterwards() async {
        let engine = FakeEngine(), gate = Gate()
        engine.beforeOpen = { await gate.wait() }
        let p = PairingModel(client: engine, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        let opening = Task { await p.open() }
        while !engine.calls.contains("open") { await Task.yield() }
        // The window closes while the engine is still making the code: its close arrives first.
        await p.close()
        #expect(engine.calls.last == "close")
        gate.open()
        await opening.value
        #expect(!engine.pairingValue.open, "the code made after the close must not stay open")
        #expect(engine.calls.last == "close")
        #expect(p.phase == .idle)
        #expect(p.code == nil)
    }

    @Test func aPollInFlightWhenTheWindowClosesChangesNothing() async {
        let engine = FakeEngine()
        let p = PairingModel(client: engine, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await p.open()
        await p.close()
        await p.poll()
        #expect(!engine.calls.contains("pairing"))
        #expect(p.phase == .idle)
    }

    @Test func withoutAnEngineItSaysSo() async {
        let p = PairingModel(client: nil, sleep: { _ in })
        await p.open()
        #expect(p.phase == .unavailable)
        let engine = FakeEngine()
        engine.failAll = true
        let q = PairingModel(client: engine, sleep: { _ in try? await Task.sleep(for: .seconds(3600)) })
        await q.open()
        #expect(q.phase == .unavailable)
    }
}

@Suite struct DisplayStateTests {
    @Test func precedence() {
        let run = SupervisorPhase.running
        #expect(DisplayState.resolve(setupPercent: 32, phase: .failed(nil), updating: false, problems: [], jobPercent: nil) == .settingUp(percent: 32))
        #expect(DisplayState.resolve(setupPercent: nil, phase: .failed(nil), updating: true, problems: [.lowDisk(freeGB: 2)], jobPercent: 50) == .error)
        #expect(DisplayState.resolve(setupPercent: nil, phase: run, updating: true, problems: [.lowDisk(freeGB: 2)], jobPercent: 50) == .attention(.lowDisk(freeGB: 2)))
        #expect(DisplayState.resolve(setupPercent: nil, phase: run, updating: true, problems: [], jobPercent: 50) == .updating)
        #expect(DisplayState.resolve(setupPercent: nil, phase: run, updating: false, problems: [], jobPercent: 50) == .busy(percent: 50))
        #expect(DisplayState.resolve(setupPercent: nil, phase: run, updating: false, problems: [], jobPercent: nil) == .running)
        #expect(DisplayState.resolve(setupPercent: nil, phase: .starting, updating: false, problems: [], jobPercent: nil) == .starting)
        #expect(DisplayState.resolve(setupPercent: nil, phase: .waitingToRetry(attempt: 1, delay: 2), updating: false, problems: [], jobPercent: nil) == .starting)
        #expect(DisplayState.resolve(setupPercent: nil, phase: .stopped, updating: false, problems: [], jobPercent: nil) == .stopped)
        #expect(DisplayState.resolve(setupPercent: nil, phase: .failed(.notInstalled("x")), updating: false, problems: [], jobPercent: nil) == .attention(.missingDownload([])))
    }

    @Test func pieChangesInEightSteps() {
        #expect([0, 12, 13, 62, 99, 100].map(DisplayState.pieStep(percent:)) == [0, 0, 1, 4, 7, 8])
    }

    @Test func words() {
        #expect([10, 40, 85, 86].map { WorkLoad.from(percent: $0) } == [.calm, .busy, .busy, .veryBusy])
        #expect([60, 25, 10, 9].map { MemoryLevel.from(freePercent: $0) } == [.plentyFree, .gettingFull, .gettingFull, .almostFull])
        #expect(ComputerName.host(fromServerName: "Brasscribe on Kalli's MacBook") == "Kalli's MacBook")
        #expect(JobStep.from(kind: "stems") == .separatingInstruments)
        #expect(JobStep.from(kind: "layers") == .separatingSoloist)
        #expect(JobStep.from(kind: "export") == .engraving)
    }
}
