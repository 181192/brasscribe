import Foundation
import Testing
@testable import BandroomKit

/// What pixi writes when it is older than `requires-pixi` (a run of 0.79.0 against ">=0.80").
let refusalOutput = """
    Error:   × this project requires pixi '>=0.80', but you have pixi 0.79.0
        ╭─[envs/pixi.toml:14:18]
     13 │ ]
     14 │ requires-pixi = ">=0.80"
        ·                  ───┬──
        ·                     ╰── this version requirement is not satisfied
     15 │
        ╰────

    """

private func writeLog(_ url: URL, _ text: String) {
    try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try? Data(text.utf8).write(to: url)
}

private let stamp = "\n--- 2026-10-01 19:31:32 +0000 pixi run --manifest-path envs/pixi.toml --frozen -e default brasscribe serve\n"

@Suite struct PixiRefusalTests {
    @Test func readsTheRequirementAndTheVersion() throws {
        let r = try #require(PixiRefusal.find(in: refusalOutput))
        #expect(r.required == ">=0.80")
        #expect(r.found == "0.79.0")
        #expect(r.message == "Error:   × this project requires pixi '>=0.80', but you have pixi 0.79.0")
    }

    @Test func otherOutputIsNoRefusal() {
        #expect(PixiRefusal.find(in: "Error: × failed to solve the environment\nTraceback (most recent call last):") == nil)
        #expect(PixiRefusal.find(in: "") == nil)
    }

    @Test func onlyTheLatestRunCounts() {
        let log = tempDir().appending(path: "engine.log")
        writeLog(log, stamp + refusalOutput + stamp + "Traceback (most recent call last):\nKeyError: 'x'\n")
        #expect(PixiRefusal.inLatestRun(log: log) == nil)
        writeLog(log, "Traceback\n" + stamp + refusalOutput)
        #expect(PixiRefusal.inLatestRun(log: log)?.found == "0.79.0")
        #expect(PixiRefusal.inLatestRun(log: log.appendingPathExtension("missing")) == nil)
    }

    @Test func outranksSettingUpAndTheFailedState() {
        let r = PixiRefusal(required: ">=0.80", found: "0.79.0", message: "m")
        #expect(DisplayState.resolve(setupPercent: 9, phase: .idle, updating: false, problems: [.pixiTooOld(r)], jobPercent: nil)
                == .attention(.pixiTooOld(r)))
        #expect(DisplayState.resolve(setupPercent: nil, phase: .failed(.pixiTooOld(r)), updating: false, problems: [.lowDisk(freeGB: 2)],
                                     jobPercent: nil) == .attention(.pixiTooOld(r)))
        // Other problems still wait for setup.
        #expect(DisplayState.resolve(setupPercent: 9, phase: .idle, updating: false, problems: [.lowDisk(freeGB: 2)], jobPercent: nil)
                == .settingUp(percent: 9))
    }
}

@MainActor
@Suite struct PixiRefusalSupervisionTests {
    func make(_ launcher: FakeLauncher, _ engine: FakeEngine) -> (EngineSupervisor, BandroomPaths) {
        let dir = tempDir()
        let paths = BandroomPaths(data: dir.appending(path: "data"), logs: dir.appending(path: "logs"))
        try? paths.ensure()
        let checkout = dir.appending(path: "checkout")
        try? FileManager.default.createDirectory(at: checkout, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: checkout.appending(path: "pixi.toml").path, contents: Data())
        let config = EngineConfiguration(source: .checkout(checkout), pixi: URL(fileURLWithPath: "/usr/bin/true"), paths: paths,
                                         computerName: "Kari's MacBook", adminToken: "secret")
        let sup = EngineSupervisor(configuration: config, launcher: launcher, makeClient: { _, _ in engine },
                                   sleep: { _ in await Task.yield() }, pickPort: { 8765 },
                                   baseEnvironment: ["HOME": "/var/empty", "PATH": "/nowhere"])
        return (sup, paths)
    }

    @Test func aRefusedStartGivesUpAtOnceAndSaysWhy() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        engine.failAll = true
        let (sup, paths) = make(launcher, engine)
        var failure: LaunchFailure??
        sup.onFailure = { failure = $0 }
        sup.start()
        await settle()
        writeLog(paths.engineLog, stamp + refusalOutput)
        launcher.crash(sup.pid!, status: 1 << 8)
        await settle(60)
        let refusal = PixiRefusal(required: ">=0.80", found: "0.79.0",
                                  message: "Error:   × this project requires pixi '>=0.80', but you have pixi 0.79.0")
        #expect(sup.phase == .failed(.pixiTooOld(refusal)))
        #expect(failure == .some(.pixiTooOld(refusal)))
        #expect(launcher.launched.count == 1)
        #expect(sup.lastExitStatus == 1 << 8)
    }

    @Test func aRefusalFromAnEarlierRunIsNotBlamedForACrash() async {
        let launcher = FakeLauncher(), engine = FakeEngine()
        engine.failAll = true
        let (sup, paths) = make(launcher, engine)
        sup.start()
        await settle()
        writeLog(paths.engineLog, stamp + refusalOutput + stamp + "Traceback (most recent call last):\n")
        launcher.crash(sup.pid!, status: 1 << 8)
        await settle(60)
        // An ordinary crash: started again after the back-off.
        #expect(sup.phase == .starting)
        #expect(launcher.launched.count == 2)
        #expect(sup.machine.failures.count == 1)
    }

    @Test func aRefusedInstallSaysWhy() async throws {
        let dir = tempDir()
        let paths = BandroomPaths(data: dir.appending(path: "data"), logs: dir.appending(path: "logs"))
        try paths.ensure()
        let checkout = dir.appending(path: "checkout")
        try FileManager.default.createDirectory(at: checkout, withIntermediateDirectories: true)
        let config = EngineConfiguration(source: .checkout(checkout), pixi: URL(fileURLWithPath: "/usr/bin/true"), paths: paths,
                                         computerName: "Kari's MacBook", adminToken: "secret")
        let setupLog = paths.logs.appending(path: "setup.log")
        let launcher = FakeLauncher()
        launcher.exitStatus = 1 << 8
        let boot = Bootstrapper(launcher: launcher)

        writeLog(setupLog, stamp + refusalOutput)
        await boot.run(configuration: config, bundledWorkspace: nil, base: [:])
        guard case .failed = boot.phase else { Issue.record("not failed: \(boot.phase)"); return }
        #expect(boot.pixiRefusal?.required == ">=0.80")

        // Another failure on the next run forgets the refusal.
        writeLog(setupLog, stamp + refusalOutput + stamp + "Error: × failed to download\n")
        await boot.run(configuration: config, bundledWorkspace: nil, base: [:])
        #expect(boot.pixiRefusal == nil)
    }
}
