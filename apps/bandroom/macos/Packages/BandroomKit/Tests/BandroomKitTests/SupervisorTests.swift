import Foundation
import Testing
@testable import BandroomKit

@Suite struct SupervisorMachineTests {
    let t0 = Date(timeIntervalSince1970: 1_790_000_000)

    @Test func startsThenRunsWhenHealthy() {
        var m = SupervisorMachine()
        #expect(m.handle(.start, now: t0) == [.launch, .waitForHealth])
        #expect(m.phase == .starting)
        #expect(m.handle(.healthy, now: t0).isEmpty)
        #expect(m.phase == .running)
    }

    @Test func startAndStopFollowThePhase() {
        let all: [SupervisorPhase] = [.idle, .starting, .running, .stopping(then: .stop), .stopping(then: .restart),
                                      .stopping(then: .fail), .stopped, .waitingToRetry(attempt: 1, delay: 2), .failed(nil)]
        #expect(all.filter(\.offersStart) == [.stopped])
        #expect(all.filter(\.offersStop) == [.starting, .running, .stopping(then: .restart), .waitingToRetry(attempt: 1, delay: 2)])
        // Low disk space outranks Stopped in what the panel shows; the phase still offers Start.
        #expect(DisplayState.resolve(setupPercent: nil, phase: .stopped, updating: false, problems: [.lowDisk(freeGB: 2)], jobPercent: nil)
                == .attention(.lowDisk(freeGB: 2)))
    }

    @Test func backoffDoublesAndCaps() {
        #expect((1...6).map(SupervisorMachine.backoff(attempt:)) == [2, 4, 8, 16, 30, 30])
    }

    @Test func crashRetriesWithBackoff() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        _ = m.handle(.healthy, now: t0)
        #expect(m.handle(.exited(status: 256), now: t0) == [.scheduleRetry(after: 2)])
        #expect(m.phase == .waitingToRetry(attempt: 1, delay: 2))
        #expect(m.handle(.retryDue, now: t0.addingTimeInterval(2)) == [.cancelRetry, .launch, .waitForHealth])
        _ = m.handle(.healthy, now: t0)
        #expect(m.handle(.exited(status: 256), now: t0.addingTimeInterval(10)) == [.scheduleRetry(after: 4)])
    }

    @Test func threeCrashesInFiveMinutesIsAnError() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        for i in 0..<2 {
            _ = m.handle(.exited(status: 9), now: t0.addingTimeInterval(Double(i) * 30))
            _ = m.handle(.retryDue, now: t0.addingTimeInterval(Double(i) * 30 + 5))
        }
        #expect(m.handle(.exited(status: 9), now: t0.addingTimeInterval(90)) == [.announceFailure])
        #expect(m.phase == .failed(nil))
    }

    @Test func crashesSpreadOverMoreThanFiveMinutesKeepRetrying() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        for i in 0..<5 {
            let at = t0.addingTimeInterval(Double(i) * 200)
            let effects = m.handle(.exited(status: 9), now: at)
            #expect(effects.first.map { if case .scheduleRetry = $0 { true } else { false } } == true, "crash \(i)")
            _ = m.handle(.retryDue, now: at.addingTimeInterval(5))
        }
    }

    @Test func tryAgainAfterErrorForgetsFailures() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        for i in 0..<3 {
            _ = m.handle(.exited(status: 9), now: t0.addingTimeInterval(Double(i)))
            _ = m.handle(.retryDue, now: t0.addingTimeInterval(Double(i)))
        }
        #expect(m.phase == .failed(nil))
        #expect(m.handle(.start, now: t0.addingTimeInterval(10)) == [.launch, .waitForHealth])
        #expect(m.failures.isEmpty)
    }

    @Test func stopIsNotACrash() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        _ = m.handle(.healthy, now: t0)
        #expect(m.handle(.stop, now: t0) == [.terminate])
        #expect(m.phase == .stopping(then: .stop))
        #expect(m.handle(.exited(status: 15), now: t0).isEmpty)
        #expect(m.phase == .stopped)
        #expect(m.failures.isEmpty)
        #expect(m.handle(.start, now: t0) == [.launch, .waitForHealth])
    }

    @Test func restartRelaunchesAfterExit() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        _ = m.handle(.healthy, now: t0)
        #expect(m.handle(.restart, now: t0) == [.terminate])
        #expect(m.handle(.exited(status: 15), now: t0) == [.launch, .waitForHealth])
        #expect(m.phase == .starting)
        #expect(m.failures.isEmpty)
    }

    @Test func stopWhileRestartingWins() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        _ = m.handle(.healthy, now: t0)
        _ = m.handle(.restart, now: t0)
        _ = m.handle(.stop, now: t0)
        _ = m.handle(.exited(status: 15), now: t0)
        #expect(m.phase == .stopped)
    }

    @Test func healthTimeoutTerminatesAndCountsAsFailure() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        #expect(m.handle(.healthTimedOut, now: t0) == [.terminate])
        #expect(m.handle(.exited(status: 15), now: t0) == [.scheduleRetry(after: 2)])
        #expect(m.failures.count == 1)
    }

    @Test func noFreePortFailsWithReason() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        #expect(m.handle(.launchFailed(.noFreePort), now: t0) == [.announceFailure])
        #expect(m.phase == .failed(.noFreePort))
    }

    @Test func stopWhileWaitingToRetryCancelsIt() {
        var m = SupervisorMachine()
        _ = m.handle(.start, now: t0)
        _ = m.handle(.exited(status: 9), now: t0)
        #expect(m.handle(.stop, now: t0) == [.cancelRetry])
        #expect(m.phase == .stopped)
        // A retry that fires late does nothing.
        #expect(m.handle(.retryDue, now: t0).isEmpty)
    }
}

@MainActor
@Suite struct EngineSupervisorTests {
    func make(_ launcher: FakeLauncher, _ engine: FakeEngine, clock: TestClock = TestClock(), port: Int? = 8765) -> (EngineSupervisor, URL) {
        let dir = tempDir()
        let paths = BandroomPaths(data: dir.appending(path: "data"), logs: dir.appending(path: "logs"))
        try? paths.ensure()
        let checkout = dir.appending(path: "checkout")
        try? FileManager.default.createDirectory(at: checkout, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: checkout.appending(path: "pixi.toml").path, contents: Data())
        let config = EngineConfiguration(source: .checkout(checkout), pixi: URL(fileURLWithPath: "/usr/bin/true"), paths: paths,
                                         computerName: "Kalli's MacBook", adminToken: "secret")
        let sup = EngineSupervisor(configuration: config, launcher: launcher, makeClient: { _, _ in engine },
                                   sleep: { _ in await Task.yield() }, now: { clock.now }, pickPort: { port },
                                   baseEnvironment: ["HOME": "/Users/k", "PATH": "/nowhere"])
        return (sup, paths.engineStatus)
    }

    @Test func launchesWithTheEngineEnvironmentAndWritesEngineJSON() async throws {
        let launcher = FakeLauncher(), engine = FakeEngine()
        let (sup, statusFile) = make(launcher, engine)
        var healthy = false
        sup.onHealthy = { _ in healthy = true }
        sup.start()
        await settle()
        #expect(sup.phase == .running)
        #expect(healthy)
        let plan = try #require(launcher.launched.first)
        #expect(Array(plan.arguments.suffix(5)) == ["brasscribe", "serve", "--lan", "--port", "8765"])
        #expect(plan.arguments.contains("--frozen"))
        #expect(plan.environment["BRASSCRIBE_ADMIN_TOKEN"] == "secret")
        #expect(plan.environment["BRASSCRIBE_COMPUTER_NAME"] == "Kalli's MacBook")
        #expect(plan.environment["PATH"]?.hasPrefix("/usr/bin") == true)
        #expect(plan.environment["BRASSCRIBE_TOKEN"] == nil)
        #expect(plan.environment["BRASSCRIBE_BAND_SOUNDS_DIR"] == nil)
        let file = try #require(EngineStatusFile.read(statusFile))
        #expect(file.port == 8765)
        #expect(file.serverId == engine.healthValue.serverId)
        #expect(file.version == "0.9.4")
    }

    @Test func restartsAfterACrash() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        let (sup, _) = make(launcher, engine)
        sup.start()
        await settle()
        let first = sup.pid!
        launcher.crash(first)
        await settle(60)
        #expect(launcher.launched.count == 2)
        #expect(sup.phase == .running)
        #expect(sup.pid != first)
    }

    @Test func everyPhaseChangeIsReported() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        let (sup, _) = make(launcher, engine)
        var phases: [SupervisorPhase] = []
        sup.onPhaseChange = { phases.append($0) }
        sup.start()
        await settle()
        launcher.crash(sup.pid!)
        await settle()
        #expect(Array(phases.prefix(3)) == [.starting, .running, .waitingToRetry(attempt: 1, delay: 2)])
        sup.stop()
        await settle()
        #expect(phases.last == .stopped)
    }

    @Test func stopTerminatesTheProcessGroupAndRemovesEngineJSON() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        let (sup, statusFile) = make(launcher, engine)
        sup.start()
        await settle()
        let pid = sup.pid!
        sup.stop()
        await settle()
        #expect(launcher.terminated == [pid])
        #expect(sup.phase == .stopped)
        #expect(!FileManager.default.fileExists(atPath: statusFile.path))
    }

    @Test func allPortsTakenIsNeedsAttention() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        let (sup, _) = make(launcher, engine, port: nil)
        var failure: LaunchFailure?? = nil
        sup.onFailure = { failure = $0 }
        sup.start()
        await settle()
        #expect(sup.phase == .failed(.noFreePort))
        #expect(failure == .some(.noFreePort))
        #expect(DisplayState.resolve(setupPercent: nil, phase: sup.phase, updating: false, problems: [], jobPercent: nil)
                == .attention(.noFreePort))
    }

    @Test func healthTimeoutGivesUpOnAHungEngine() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        engine.failAll = true
        let clock = TestClock()
        let (sup, _) = make(launcher, engine, clock: clock)
        sup.healthTimeout = 10
        sup.start()
        await settle(5)
        clock.advance(11)
        await settle(20)
        #expect(launcher.terminated.count >= 1)
        sup.stop()
        await settle()
    }

    @Test func stoppingNeverLaunchesAgain() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        let (sup, _) = make(launcher, engine)
        sup.start()
        await settle()
        sup.stop()
        await settle(60)
        #expect(launcher.launched.count == 1)
    }
}

@Suite struct PortPickerTests {
    @Test func skipsBusyPorts() {
        #expect(PortPicker.firstFree(isFree: { $0 >= 8767 }) == 8767)
        #expect(PortPicker.firstFree(isFree: { _ in false }) == nil)
    }

    /// A listening socket on `address` at a port the system picks; returns the descriptor and the port.
    private func listen(on address: in_addr_t, reuse: Bool) throws -> (fd: Int32, port: Int) {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        try #require(fd >= 0)
        var one: Int32 = 1
        if reuse { setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, socklen_t(MemoryLayout<Int32>.size)) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr = in_addr(s_addr: address)
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bound = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, len) == 0 && Darwin.listen(fd, 4) == 0 && getsockname(fd, $0, &len) == 0 }
        }
        try #require(bound)
        return (fd, Int(UInt16(bigEndian: addr.sin_port)))
    }

    @Test(arguments: [true, false])
    func aPortAnotherProgramListensOnIsBusy(reuse: Bool) throws {
        let loopback = UInt32(0x7f00_0001).bigEndian
        for address in [loopback, INADDR_ANY] {
            let (fd, port) = try listen(on: address, reuse: reuse)
            #expect(!PortPicker.isFree(port), "listening on \(address == INADDR_ANY ? "all addresses" : "127.0.0.1")")
            close(fd)
        }
    }

    @Test func aPortNobodyUsesIsFree() throws {
        let (fd, port) = try listen(on: INADDR_ANY, reuse: true)
        close(fd)
        #expect(PortPicker.isFree(port))
    }
}

@Suite struct BandSoundsTests {
    @Test func theBundledBandSoundsReachTheEngine() throws {
        let resources = tempDir()
        #expect(EngineConfiguration.findBandSounds(resources: resources) == nil)
        let band = resources.appending(path: "band")
        try FileManager.default.createDirectory(at: band, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: band.appending(path: "brasscribe-band.sf2").path, contents: Data("RIFF".utf8))
        #expect(EngineConfiguration.findBandSounds(resources: resources) == nil, "no part map: Studio could not use it")
        FileManager.default.createFile(atPath: band.appending(path: "mapping.json").path, contents: Data("{}".utf8))
        let found = try #require(EngineConfiguration.findBandSounds(resources: resources))
        #expect(found.path == band.path)
        let paths = BandroomPaths(data: resources.appending(path: "data"), logs: resources.appending(path: "logs"))
        let config = EngineConfiguration(source: .checkout(resources), pixi: nil, paths: paths, computerName: "Mac",
                                         adminToken: "secret", bandSounds: found)
        #expect(config.environment(base: [:])["BRASSCRIBE_BAND_SOUNDS_DIR"] == band.path)
    }
}
