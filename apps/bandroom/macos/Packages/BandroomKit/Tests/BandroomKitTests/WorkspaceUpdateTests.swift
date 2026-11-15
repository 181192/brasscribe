import Foundation
import Testing
@testable import BandroomKit

/// The app's workspace and the copy in the data folder: stamp compare, the all-or-nothing swap, and what it keeps.
@Suite struct WorkspaceUpdateTests {
    private let fm = FileManager.default

    private func write(_ text: String, _ url: URL) throws {
        try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data(text.utf8).write(to: url)
    }

    private func read(_ url: URL) -> String? {
        (try? Data(contentsOf: url)).map { String(decoding: $0, as: UTF8.self) }
    }

    /// An app workspace at `studio` (the file that changes between builds), stamped as the build script does.
    private func bundle(in root: URL, name: String = "bundle", studio: String, lock: String = "version: 6\n",
                        stamped: Bool = true) throws -> URL {
        let b = root.appending(path: name, directoryHint: .isDirectory)
        try write("[workspace]\nname = \"scribe\"\n", b.appending(path: "pixi.toml"))
        try write(lock, b.appending(path: "pixi.lock"))
        try write(studio, b.appending(path: "engine/src/scribe_engine/static/assets/studio.js"))
        try write("# music\n", b.appending(path: "music/src/music.py"))
        try write("# adapters\n", b.appending(path: "ml/adapters/run_adapter.py"))
        if stamped {
            var stamp = try WorkspaceStamp.compute(b)
            stamp.commit = "c3dc2ad"
            try JSONEncoder().encode(stamp).write(to: b.appending(path: WorkspaceStamp.fileName))
        }
        return b
    }

    /// What the first run leaves: the copy, its pixi environment, and a file of someone's own.
    private func installed(from bundle: URL, root: URL) throws -> URL {
        let ws = root.appending(path: "data/envs", directoryHint: .isDirectory)
        try WorkspaceSwap.install(from: bundle, into: ws).commit()
        try write("#!/bin/sh\n", ws.appending(path: ".pixi/envs/default/bin/scribe"))
        // every environment installed to its end for this lockfile, as setup and the models' installs leave them
        let source = EngineSource.installed(workspace: ws)
        for name in ["default"] + EngineSource.adapterEnvironments {
            try fm.createDirectory(at: ws.appending(path: ".pixi/envs/\(name)"), withIntermediateDirectories: true)
            try source.markInstalled(name)
        }
        try write("keep me", ws.appending(path: "notes.txt"))
        try write("{\"devices\": []}", root.appending(path: "data/companion/devices.json"))
        try write("weights", root.appending(path: "data/models/mega53/model.ckpt"))
        return ws
    }

    private func studio(_ ws: URL) -> String? {
        read(ws.appending(path: "engine/src/scribe_engine/static/assets/studio.js"))
    }

    private func userDataIsIntact(_ ws: URL, root: URL) {
        #expect(read(ws.appending(path: ".pixi/envs/default/bin/scribe")) == "#!/bin/sh\n")
        #expect(read(ws.appending(path: "notes.txt")) == "keep me")
        #expect(read(root.appending(path: "data/companion/devices.json")) == "{\"devices\": []}")
        #expect(read(root.appending(path: "data/models/mega53/model.ckpt")) == "weights")
    }

    // MARK: stamp compare

    @Test func theStampHashesContentNotDates() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let a = try bundle(in: root, name: "a", studio: "one", stamped: false)
        let first = try WorkspaceStamp.compute(a)
        try fm.setAttributes([.modificationDate: Date(timeIntervalSince1970: 0)], ofItemAtPath: a.appending(path: "pixi.toml").path)
        #expect(try WorkspaceStamp.compute(a) == first)
        try write("two", a.appending(path: "engine/src/scribe_engine/static/assets/studio.js"))
        let second = try WorkspaceStamp.compute(a)
        #expect(second.stamp != first.stamp)
        #expect(second.lock == first.lock)
        // The stamp file itself is left out, so writing it doesn't change it.
        try JSONEncoder().encode(second).write(to: a.appending(path: WorkspaceStamp.fileName))
        #expect(try WorkspaceStamp.compute(a) == second)
        #expect(WorkspaceStamp.read(in: a) == second)
    }

    @Test func theStampMatchesTheBuildScript() throws {
        // stage-workspace.sh: `find . -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256`.
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let b = try bundle(in: root, studio: "one", stamped: false)
        let script = Process()
        script.executableURL = URL(fileURLWithPath: "/bin/sh")
        script.arguments = ["-c", "cd \"$0\" && find . -type f ! -name '.DS_Store' -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256 | cut -d' ' -f1", b.path]
        let out = Pipe()
        script.standardOutput = out
        try script.run()
        script.waitUntilExit()
        let shell = String(decoding: out.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        #expect(try WorkspaceStamp.compute(b).stamp == shell)
    }

    @Test func comparingStamps() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio")
        let ws = root.appending(path: "data/envs", directoryHint: .isDirectory)
        #expect(WorkspaceCheck.compare(bundled: v1, installed: ws) == .notInstalled)
        _ = try installed(from: v1, root: root)
        #expect(WorkspaceCheck.compare(bundled: v1, installed: ws) == .upToDate)

        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")
        #expect(WorkspaceCheck.compare(bundled: v2, installed: ws) == .update(lockChanged: false))
        let v3 = try bundle(in: root, name: "v3", studio: "fixed studio", lock: "version: 6\n# new\n")
        #expect(WorkspaceCheck.compare(bundled: v3, installed: ws) == .update(lockChanged: true))
    }

    @Test func aCopyFromBeforeStampsIsOutOfDate() throws {
        // The first versions copied the workspace without a stamp and never replaced it.
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let old = try bundle(in: root, name: "old", studio: "old studio", stamped: false)
        let ws = root.appending(path: "data/envs", directoryHint: .isDirectory)
        try fm.createDirectory(at: ws, withIntermediateDirectories: true)
        for name in try fm.contentsOfDirectory(atPath: old.path) {
            try fm.copyItem(at: old.appending(path: name), to: ws.appending(path: name))
        }
        let new = try bundle(in: root, name: "new", studio: "fixed studio")
        #expect(WorkspaceStamp.read(in: ws) == nil)
        #expect(WorkspaceCheck.compare(bundled: new, installed: ws) == .update(lockChanged: false))
    }

    @Test func aBuildWithoutAStampGetsOneComputed() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let b = try bundle(in: root, studio: "one", stamped: false)
        let ws = try installed(from: b, root: root)
        #expect(WorkspaceStamp.read(in: ws) == (try WorkspaceStamp.compute(b)))
        #expect(WorkspaceCheck.compare(bundled: b, installed: ws) == .upToDate)
    }

    // MARK: the swap

    @Test func anUpdateReplacesTheCodeAndKeepsEverythingElse() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        try write("gone in v2", ws.appending(path: "engine/src/scribe_engine/removed.py"))
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")

        try WorkspaceSwap.install(from: v2, into: ws).commit()
        #expect(studio(ws) == "fixed studio")
        #expect(!fm.fileExists(atPath: ws.appending(path: "engine/src/scribe_engine/removed.py").path))
        #expect(WorkspaceStamp.read(in: ws) == WorkspaceStamp.read(in: v2))
        #expect(!fm.fileExists(atPath: ws.appending(path: WorkspaceSwap.workDir).path))
        userDataIsIntact(ws, root: root)
    }

    @Test func aFailurePartWayPutsTheOldCopyBack() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio")
        let ws = try installed(from: v1, root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")
        struct DiskFull: Error {}
        // engine/ is already in place when music/ fails.
        #expect(throws: DiskFull.self) {
            try WorkspaceSwap.install(from: v2, into: ws) { name in if name == "music" { throw DiskFull() } }
        }
        #expect(studio(ws) == "old studio")
        #expect(WorkspaceStamp.read(in: ws) == WorkspaceStamp.read(in: v1))
        #expect(fm.fileExists(atPath: ws.appending(path: "music/src/music.py").path))
        #expect(!fm.fileExists(atPath: ws.appending(path: WorkspaceSwap.workDir).path))
        userDataIsIntact(ws, root: root)
    }

    @Test func rollbackAfterTheSwapRestoresTheOldCopy() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio")
        let ws = try installed(from: v1, root: root)
        let swap = try WorkspaceSwap.install(from: try bundle(in: root, name: "v2", studio: "fixed studio"), into: ws)
        #expect(studio(ws) == "fixed studio")
        try swap.rollback()
        #expect(studio(ws) == "old studio")
        #expect(WorkspaceStamp.read(in: ws) == WorkspaceStamp.read(in: v1))
        userDataIsIntact(ws, root: root)
    }

    @Test func anUpdateCutShortIsUndoneAtTheNextLaunch() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio", stamped: false)
        let ws = try installed(from: v1, root: root)
        let before = WorkspaceStamp.read(in: ws)
        // The app quit between the swap and the end of `pixi install`: no commit, no rollback.
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio", lock: "version: 6\n# new\n")
        _ = try WorkspaceSwap.install(from: v2, into: ws)
        // v2's stamp is already in place, but the update never finished: the launch check must not trust it.
        #expect(WorkspaceStamp.read(in: ws) == WorkspaceStamp.read(in: v2))
        #expect(WorkspaceCheck.atLaunch(bundled: v2, installed: ws) == .update(lockChanged: true))
        #expect(studio(ws) == "old studio")
        #expect(WorkspaceStamp.read(in: ws) == before)
        #expect(!fm.fileExists(atPath: ws.appending(path: WorkspaceSwap.workDir).path))
        userDataIsIntact(ws, root: root)
    }

    @Test func oldFilesLeftAfterACommitNeverComeBack() throws {
        // The journal went (the commit) but the old copy couldn't all be removed.
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")
        let swap = try WorkspaceSwap.install(from: v2, into: ws)
        try fm.removeItem(at: swap.work.appending(path: WorkspaceSwap.journalName))
        #expect(fm.fileExists(atPath: swap.backup.appending(path: "engine").path))
        #expect(WorkspaceCheck.atLaunch(bundled: v2, installed: ws) == .upToDate)
        #expect(studio(ws) == "fixed studio")
        // And the next update isn't in its way.
        try WorkspaceSwap.install(from: try bundle(in: root, name: "v3", studio: "newer studio"), into: ws).commit()
        #expect(studio(ws) == "newer studio")
        #expect(!fm.fileExists(atPath: ws.appending(path: WorkspaceSwap.workDir).path))
        userDataIsIntact(ws, root: root)
    }

    @Test func codeFetchedAtRunTimeIsCarriedOver() throws {
        // run_adapter.py clones MSST into ml/adapters/mega53/msst when the app didn't ship it.
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        try write("# inference\n", ws.appending(path: "ml/adapters/mega53/msst/inference.py"))
        try WorkspaceSwap.install(from: try bundle(in: root, name: "v2", studio: "fixed studio"), into: ws).commit()
        #expect(read(ws.appending(path: "ml/adapters/mega53/msst/inference.py")) == "# inference\n")
        // An app that ships it wins.
        let v3 = try bundle(in: root, name: "v3", studio: "fixed studio")
        try write("# shipped\n", v3.appending(path: "ml/adapters/mega53/msst/inference.py"))
        try WorkspaceSwap.install(from: v3, into: ws).commit()
        #expect(read(ws.appending(path: "ml/adapters/mega53/msst/inference.py")) == "# shipped\n")
    }

    @Test func entriesNewInTheUpdateGoOnRollback() throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")
        try write("# kvartett\n", v2.appending(path: "kvartett/src/k.py"))
        let swap = try WorkspaceSwap.install(from: v2, into: ws)
        #expect(fm.fileExists(atPath: ws.appending(path: "kvartett").path))
        try swap.rollback()
        #expect(!fm.fileExists(atPath: ws.appending(path: "kvartett").path))
        userDataIsIntact(ws, root: root)
    }

    // MARK: the update, with pixi

    @MainActor
    private func configuration(_ root: URL, workspace: URL) -> EngineConfiguration {
        let paths = BandroomPaths(data: root.appending(path: "data"), logs: root.appending(path: "logs"))
        return EngineConfiguration(source: .installed(workspace: workspace), pixi: URL(fileURLWithPath: "/usr/bin/true"),
                                   paths: paths, computerName: "Band room", adminToken: "t")
    }


    @MainActor @Test func anUnchangedLockfileReusesTheEnvironments() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")
        let launcher = FakeLauncher()
        let boot = Bootstrapper(launcher: launcher)
        guard case .update(let lockChanged) = WorkspaceCheck.compare(bundled: v2, installed: ws) else { Issue.record("no update"); return }
        let ok = await boot.update(configuration: configuration(root, workspace: ws), bundledWorkspace: v2, lockChanged: lockChanged)
        #expect(ok)
        #expect(launcher.launched.isEmpty)
        #expect(boot.phase == .done && !boot.isUpdating)
        #expect(studio(ws) == "fixed studio")
        #expect(WorkspaceCheck.compare(bundled: v2, installed: ws) == .upToDate)
        userDataIsIntact(ws, root: root)
    }

    @MainActor @Test func aNewLockfileInstallsAgain() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio", lock: "version: 6\n# numpy 2.6\n")
        let launcher = FakeLauncher()
        let boot = Bootstrapper(launcher: launcher)
        launcher.exitStatus = 0
        let ok = await boot.update(configuration: configuration(root, workspace: ws), bundledWorkspace: v2, lockChanged: true)
        #expect(ok)
        // the engine's environment only: the models' follow behind the engine once it runs
        #expect(launcher.launched.map(\.arguments.last) == ["default"])
        #expect(launcher.launched.first?.arguments.contains(ws.appending(path: "pixi.toml").path) == true)
        #expect(read(ws.appending(path: "pixi.lock")) == "version: 6\n# numpy 2.6\n")
        #expect(WorkspaceCheck.compare(bundled: v2, installed: ws) == .upToDate)
        userDataIsIntact(ws, root: root)
    }

    @MainActor @Test func aFailedInstallKeepsTheOldWorkingCopy() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio")
        let ws = try installed(from: v1, root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio", lock: "version: 6\n# numpy 2.6\n")
        let launcher = FakeLauncher()
        let boot = Bootstrapper(launcher: launcher)
        launcher.exitStatus = 256
        let ok = await boot.update(configuration: configuration(root, workspace: ws), bundledWorkspace: v2, lockChanged: true)
        #expect(!ok)
        guard case .failed(let why) = boot.phase else { Issue.record("not failed: \(boot.phase)"); return }
        #expect(why.contains("pixi install"))
        #expect(studio(ws) == "old studio")
        #expect(read(ws.appending(path: "pixi.lock")) == "version: 6\n")
        #expect(WorkspaceStamp.read(in: ws) == WorkspaceStamp.read(in: v1))
        // Still out of date, so Retry (or the next launch) tries again.
        #expect(WorkspaceCheck.compare(bundled: v2, installed: ws) == .update(lockChanged: true))
        userDataIsIntact(ws, root: root)
    }

    @MainActor @Test func aRefusedUpdateKeepsTheOldCopyAndSaysWhy() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio")
        let ws = try installed(from: v1, root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio", lock: "version: 6\n# numpy 2.6\n")
        let config = configuration(root, workspace: ws)
        let setupLog = config.paths.logs.appending(path: "setup.log")
        try fm.createDirectory(at: config.paths.logs, withIntermediateDirectories: true)
        try Data(("\n--- 2026-10-01 pixi install\n" + refusalOutput).utf8).write(to: setupLog)
        let launcher = FakeLauncher()
        launcher.exitStatus = 1 << 8
        let boot = Bootstrapper(launcher: launcher)
        let ok = await boot.update(configuration: config, bundledWorkspace: v2, lockChanged: true)
        #expect(!ok)
        #expect(studio(ws) == "old studio")
        #expect(boot.pixiRefusal?.found == "0.79.0")
        #expect(Problem.afterFailedUpdate(refusal: boot.pixiRefusal) == .updateRefused(boot.pixiRefusal!))
    }

    @MainActor @Test func setupInstallsEvenOverAnEnvironmentFromAnEarlierBuild() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        // Setup never finished with v1; this build ships a new lockfile.
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio", lock: "version: 6\n# numpy 2.6\n")
        let launcher = FakeLauncher()
        launcher.exitStatus = 0
        let boot = Bootstrapper(launcher: launcher)
        await boot.run(configuration: configuration(root, workspace: ws), bundledWorkspace: v2)
        #expect(boot.phase == .done)
        #expect(launcher.launched.map(\.arguments) == [["install", "--manifest-path", ws.appending(path: "pixi.toml").path, "--frozen", "-e", "default"]])
        #expect(read(ws.appending(path: "pixi.lock")) == "version: 6\n# numpy 2.6\n")
        // the engine's is marked for the new lockfile; the models' are not, and are installed next
        let source = EngineSource.installed(workspace: ws)
        #expect(source.isInstalled("default"))
        #expect(source.pendingModelEnvironments == EngineSource.adapterEnvironments)
    }

    /// An engine installed by a Bandroom that ran the adapters another way (earlier builds ran them with uv, in folders
    /// inside the app) has only its own environment, and no markers. Its update installs the engine's again (it
    /// cannot tell it was installed to its end), and the models' follow behind the engine: nothing is carried over.
    @MainActor @Test func anEngineWithoutMarkersGetsEveryEnvironment() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        try fm.removeItem(at: ws.appending(path: ".bandroom-setup"))
        for name in EngineSource.adapterEnvironments { try fm.removeItem(at: ws.appending(path: ".pixi/envs/\(name)")) }
        let config = configuration(root, workspace: ws)
        let launcher = FakeLauncher()
        launcher.exitStatus = 0
        let ok = await Bootstrapper(launcher: launcher).update(configuration: config, bundledWorkspace: try bundle(in: root, name: "v2", studio: "fixed studio"),
                                                              lockChanged: false)
        #expect(ok)
        #expect(launcher.launched.map(\.arguments.last) == ["default"])
        launcher.launched.removeAll()
        let models = ModelEnvironments(launcher: launcher)
        await models.install(configuration: config)
        #expect(launcher.launched.map(\.arguments.last) == EngineSource.adapterEnvironments)
        #expect(models.phase == .done && config.source.pendingModelEnvironments.isEmpty)
    }

    /// A model's environment that cannot be installed does not hold up the others: they are installed and usable,
    /// the failed one is named, and Try again installs that one only.
    @MainActor @Test func aModelThatFailsIsNamedAndTheRestAreInstalled() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        try fm.removeItem(at: ws.appending(path: ".bandroom-setup"))
        let config = configuration(root, workspace: ws)
        let launcher = FakeLauncher()
        launcher.exitStatus = 0
        launcher.exitStatusFor = { $0.arguments.last == "separator" ? 1 : nil }
        let models = ModelEnvironments(launcher: launcher)
        await models.install(configuration: config)
        #expect(models.phase == .failed(["separator"], trouble: nil))
        #expect(launcher.launched.map(\.arguments.last) == EngineSource.adapterEnvironments)
        #expect(config.source.pendingModelEnvironments == ["separator"])
        launcher.exitStatusFor = nil
        launcher.launched.removeAll()
        await models.install(configuration: config)
        #expect(launcher.launched.map(\.arguments.last) == ["separator"])
        #expect(models.phase == .done)
    }

    /// A job holds its environment's lock shared while it uses it (run_adapter.py): Bandroom's install of that
    /// environment waits for the job, and holds the lock while pixi runs, so a job that needs it waits for the install
    /// rather than starting a second one. The engine is told where the locks are.
    @MainActor @Test func anInstallAndAJobNeverRunOnTheSameEnvironmentAtOnce() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        try fm.removeItem(at: ws.appending(path: ".bandroom-setup/env-swift-f0"))
        try fm.removeItem(at: ws.appending(path: ".bandroom-setup/env-beat-this"))
        let config = configuration(root, workspace: ws)
        let locks = config.source.environmentLocks
        #expect(config.environment(base: [:])["SCRIBE_ENV_LOCKS"] == locks.path)
        try fm.createDirectory(at: locks, withIntermediateDirectories: true)
        // a job using swift-f0
        let job = open(locks.appending(path: "swift-f0.lock").path, O_RDWR | O_CREAT, 0o644)
        defer { close(job) }
        #expect(flock(job, LOCK_SH | LOCK_NB) == 0)

        let launcher = FakeLauncher()
        let models = ModelEnvironments(launcher: launcher)
        let run = Task { await models.install(configuration: config) }
        try await Task.sleep(for: .milliseconds(800))
        #expect(launcher.launched.isEmpty, "installed under a job that uses it")
        #expect(models.phase == .installing(.init(environment: "swift-f0", index: 1, count: 2)))
        flock(job, LOCK_UN)
        while launcher.launched.isEmpty { try await Task.sleep(for: .milliseconds(50)) }
        // While pixi installs it, a job that needs it cannot have it: it waits.
        #expect(flock(job, LOCK_SH | LOCK_NB) != 0)
        launcher.crash(launcher.nextPid, status: 0)
        while launcher.launched.count < 2 { try await Task.sleep(for: .milliseconds(50)) }
        #expect(flock(job, LOCK_SH | LOCK_NB) == 0)  // swift-f0's install is over
        flock(job, LOCK_UN)
        launcher.crash(launcher.nextPid, status: 0)
        await run.value
        #expect(models.phase == .done)
        #expect(launcher.launched.map(\.arguments.last) == ["swift-f0", "beat-this"])
    }

    /// Quitting while an install waits for a job ends the wait; nothing is installed.
    @MainActor @Test func quittingEndsAWaitForAJob() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        try fm.removeItem(at: ws.appending(path: ".bandroom-setup/env-separator"))
        let config = configuration(root, workspace: ws)
        try fm.createDirectory(at: config.source.environmentLocks, withIntermediateDirectories: true)
        let job = open(config.source.environmentLocks.appending(path: "separator.lock").path, O_RDWR | O_CREAT, 0o644)
        defer { close(job) }
        flock(job, LOCK_SH)
        let launcher = FakeLauncher()
        let models = ModelEnvironments(launcher: launcher)
        let run = Task { await models.install(configuration: config) }
        try await Task.sleep(for: .milliseconds(300))
        models.cancel()
        await run.value
        #expect(models.phase == .idle && launcher.launched.isEmpty)
        #expect(config.source.pendingModelEnvironments == ["separator"])
    }

    /// pixi makes an environment's folder before it has finished filling it: a folder left by an install that
    /// stopped part-way (quit, no connection, a full disk) is installed again; so is every one after a lockfile change.
    @MainActor @Test func aHalfMadeEnvironmentIsInstalledAgain() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let source = EngineSource.installed(workspace: ws)
        #expect(source.pendingModelEnvironments.isEmpty)
        try fm.removeItem(at: ws.appending(path: ".bandroom-setup/env-beat-this"))
        try write("partial", ws.appending(path: ".pixi/envs/beat-this/conda-meta/history"))
        #expect(source.pendingModelEnvironments == ["beat-this"])
        // A quit during its install leaves it unmarked.
        let launcher = FakeLauncher()
        let models = ModelEnvironments(launcher: launcher)
        let run = Task { await models.install(configuration: configuration(root, workspace: ws)) }
        while launcher.launched.isEmpty { await Task.yield() }
        models.cancel(grace: 0)
        await run.value
        #expect(models.phase == .idle && source.pendingModelEnvironments == ["beat-this"])
        // A new lockfile: every one is pending, the engine's own is not taken as installed either.
        try write("version: 6\n# numpy 2.6\n", ws.appending(path: "pixi.lock"))
        #expect(source.pendingModelEnvironments == EngineSource.adapterEnvironments)
        #expect(!source.isInstalled("default"))
    }

    /// The reader of printed music is kept up to date where it was installed, and never installed unasked; its
    /// marker is beside the others, so it outlasts pixi making its environment afresh.
    @MainActor @Test func theReaderIsInstalledAgainOnlyWhereItWas() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let config = configuration(root, workspace: ws)
        #expect(config.source.adapterEnvironmentsToInstall == EngineSource.adapterEnvironments)
        #expect(!config.source.isReaderInstalled)
        try fm.createDirectory(at: config.source.readerEnvironment, withIntermediateDirectories: true)
        try config.source.markReaderInstalled()
        #expect(config.source.isReaderInstalled)
        #expect(config.source.adapterEnvironmentsToInstall == EngineSource.adapterEnvironments + ["homr"])
        #expect(config.source.pendingModelEnvironments.isEmpty)
        try write("version: 6\n# numpy 2.6\n", ws.appending(path: "pixi.lock"))
        #expect(config.source.isReaderInstalled && config.source.pendingModelEnvironments.last == "homr")
        // A checkout runs its adapters in their own projects: its setup installs the engine's environment only.
        let checkout = EngineSource.checkout(ws)
        #expect(checkout.adapterEnvironmentsToInstall.isEmpty && checkout.pendingModelEnvironments.isEmpty)
        let launcher = FakeLauncher()
        launcher.exitStatus = 0
        let paths = BandroomPaths(data: root.appending(path: "data"), logs: root.appending(path: "logs"))
        let dev = EngineConfiguration(source: checkout, pixi: URL(fileURLWithPath: "/usr/bin/true"), paths: paths,
                                      computerName: "Band room", adminToken: "t")
        await Bootstrapper(launcher: launcher).run(configuration: dev, bundledWorkspace: nil)
        #expect(launcher.launched.map(\.arguments.last) == ["default"])
    }

    /// Setup that stops because there is no connection, or no room on the disk, says so (from what pixi wrote),
    /// so the person is told what to do about it; anything else is told by its log.
    @MainActor @Test func setupSaysWhenTheConnectionOrTheDiskStoppedIt() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let config = configuration(root, workspace: ws)
        let log = config.paths.logs.appending(path: "setup.log")
        for (said, trouble) in [("Error: failed to download\n  ├─▶ error sending request for url (https://conda.anaconda.org/)\n  ╰─▶ dns error: failed to lookup address information",
                                 InstallTrouble.network),
                                ("Error: failed to link\n  ╰─▶ No space left on device (os error 28)", .diskFull),
                                ("Error: the lockfile is not up to date", nil)] as [(String, InstallTrouble?)] {
            try write("--- an earlier run\nerror sending request\n--- now pixi install\n\(said)\n", log)
            let launcher = FakeLauncher()
            launcher.exitStatus = 1
            let boot = Bootstrapper(launcher: launcher)
            await boot.run(configuration: config, bundledWorkspace: try bundle(in: root, name: "v2", studio: "fixed studio"))
            guard case .failed = boot.phase else { Issue.record("not failed: \(boot.phase)"); continue }
            #expect(boot.trouble == trouble, "\(said)")
        }
    }

    /// The adapters setup installs are the environments pixi.toml has for them on this Mac: every one but the
    /// engine's, the reader's (installed only when asked for) and the CUDA ones. The owner's comparison script
    /// and the engine's runner name them the same way.
    @Test(.enabled(if: enginesWireIsRead)) func theAdaptersAreThePixiEnvironments() throws {
        let root = try #require(repository())
        let toml = try String(contentsOf: root.appending(path: "pixi.toml"), encoding: .utf8)
        let section = try #require(toml.split(separator: "[environments]", maxSplits: 1).last)
        let names = section.split(whereSeparator: \.isNewline).prefix { !$0.hasPrefix("[") }
            .compactMap { $0.firstMatch(of: /^([a-z0-9-]+)\s*=/)?.output.1 }.map(String.init)
        #expect(!names.isEmpty)
        let expected = names.filter { $0 != "default" && $0 != SheetReader.adapter && !$0.hasSuffix("-cuda") }
        #expect(Set(EngineSource.adapterEnvironments) == Set(expected))
        #expect(names.contains(SheetReader.adapter))
    }

    /// Every environment Bandroom for Mac installs comes from wheels and conda packages: none is built from source
    /// with a compiler or fetched with git, which a Mac without Apple's developer tools has neither of. Pure-Python
    /// sources build without either, and the engine's own packages are folders of the workspace.
    @Test(.enabled(if: enginesWireIsRead)) func theMacsEnvironmentsNeedNoDeveloperTools() throws {
        let root = try #require(repository())
        let lock = try String(contentsOf: root.appending(path: "pixi.lock"), encoding: .utf8)
        let wanted = Set(["default", SheetReader.adapter] + EngineSource.adapterEnvironments)
        let pureSources = ["antlr4-python3-runtime"]
        var env: String?, mac = false, seen = Set<String>(), found: [String] = []
        for line in lock.split(separator: "\n", omittingEmptySubsequences: false) {
            if line.hasPrefix("packages:") { break }  // the environments come first, then every package
            if let m = line.firstMatch(of: /^  ([a-z0-9-]+):$/) { env = String(m.output.1); continue }
            if let m = line.firstMatch(of: /^      ([a-z0-9-]+):$/) { mac = m.output.1.hasPrefix("osx-arm64"); continue }
            guard let env, wanted.contains(env), mac, let m = line.firstMatch(of: /^      - pypi: (\S+)$/) else { continue }
            seen.insert(env)
            let url = String(m.output.1)
            let file = url.split(separator: "/").last.map(String.init) ?? url
            if !url.contains("://") || file.hasSuffix(".whl") || pureSources.contains(where: file.hasPrefix) { continue }
            found.append("\(env): \(url)")
        }
        #expect(seen == wanted)
        #expect(found.isEmpty, "\(found)")
    }

    @MainActor @Test func quittingStopsAnInstallUnderWay() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: try bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio", lock: "version: 6\n# numpy 2.6\n")
        let launcher = FakeLauncher()
        let boot = Bootstrapper(launcher: launcher)
        let update = Task { await boot.update(configuration: configuration(root, workspace: ws), bundledWorkspace: v2, lockChanged: true) }
        while launcher.launched.isEmpty { await Task.yield() }
        boot.cancel()
        #expect(launcher.terminated == [4001])
        #expect(await update.value == false)
        #expect(studio(ws) == "old studio")
        boot.cancel()
        #expect(launcher.terminated == [4001], "nothing left to stop")
    }

    @MainActor @Test func aCopyThatCantBeMadeKeepsTheOldOne() async throws {
        let root = tempDir()
        defer { try? fm.removeItem(at: root) }
        let v1 = try bundle(in: root, name: "v1", studio: "old studio")
        let ws = try installed(from: v1, root: root)
        let boot = Bootstrapper(launcher: FakeLauncher())
        let ok = await boot.update(configuration: configuration(root, workspace: ws), bundledWorkspace: root.appending(path: "missing"),
                                   lockChanged: false)
        #expect(!ok)
        if case .failed = boot.phase {} else { Issue.record("not failed: \(boot.phase)") }
        #expect(studio(ws) == "old studio")
        userDataIsIntact(ws, root: root)
    }

    @Test func healthDecodesTheBuildAndOlderEnginesWithout() throws {
        let old = #"{"status":"ok","version":"0.1.0","device":"mps","auth_required":false,"server_id":"a","server_name":"b"}"#
        #expect(try JSONDecoder().decode(Health.self, from: Data(old.utf8)).build == nil)
        #expect(try JSONDecoder().decode(Health.self, from: Data(old.utf8)).interfaceVersion == nil)
        let new = #"{"status":"ok","version":"0.1.0","build":"c3dc2ad 5faffacca071","device":"mps","auth_required":false,"server_id":"a","server_name":"b","interface_version":\#(Wire.interfaceVersion)}"#
        #expect(try JSONDecoder().decode(Health.self, from: Data(new.utf8)).build == "c3dc2ad 5faffacca071")
        #expect(try JSONDecoder().decode(Health.self, from: Data(new.utf8)).interfaceVersion == Wire.interfaceVersion)
    }

    @Test func theUpdateShowsAsUpdatingAndAFailureNeedsAttention() {
        #expect(DisplayState.resolve(setupPercent: nil, phase: .idle, updating: true, problems: [], jobPercent: nil) == .updating)
        #expect(DisplayState.resolve(setupPercent: nil, phase: .running, updating: false, problems: [.updateFailed], jobPercent: nil)
                == .attention(.updateFailed))
    }

    /// After a failed update the previous workspace is back. It is started only when its environment has the command
    /// this app runs; a start that can only fail would end in the error state, which hides the update's problem and
    /// offers a Try again that starts the same engine again.
    @Test func afterAFailedUpdateThePreviousEngineStartsOnlyWhenItsCommandIsThisApps() throws {
        let root = fm.temporaryDirectory.appending(path: "bandroom-start-\(UUID().uuidString)")
        defer { try? fm.removeItem(at: root) }
        let ws = try installed(from: bundle(in: root, name: "v1", studio: "old studio"), root: root)
        let source = EngineSource.installed(workspace: ws)
        #expect(source.startsAfterUpdate(failed: false))
        #expect(source.startsAfterUpdate(failed: true))  // the environment has `scribe`: the previous engine runs meanwhile

        // An environment made for an engine that was started under another command.
        let bin = ws.appending(path: ".pixi/envs/default/bin")
        try fm.moveItem(at: bin.appending(path: EngineSource.command), to: bin.appending(path: "engine-before"))
        #expect(!source.isEnvironmentReady)
        #expect(!source.startsAfterUpdate(failed: true))
        #expect(source.startsAfterUpdate(failed: false))  // no failure: the start itself reports what is wrong

        // Not started, the supervisor stays at rest and the update's problem is what shows, with its own fix.
        #expect(DisplayState.resolve(setupPercent: nil, phase: .idle, updating: false, problems: [.updateFailed], jobPercent: nil)
                == .attention(.updateFailed))
        // Judged startable and started, it can still exit until the supervisor gives up (an install that stopped
        // after it had written the command). The update's problem still shows: its Try again runs the update,
        // where Error's would only start the same engine again.
        #expect(DisplayState.resolve(setupPercent: nil, phase: .failed(nil), updating: false, problems: [.lowDisk(freeGB: 1), .updateFailed], jobPercent: nil)
                == .attention(.updateFailed))
        #expect(DisplayState.resolve(setupPercent: nil, phase: .failed(.spawn("gone")), updating: false, problems: [.updateFailed], jobPercent: nil)
                == .attention(.updateFailed))
        // Without a failed update, an engine that gave up is the error it was.
        #expect(DisplayState.resolve(setupPercent: nil, phase: .failed(nil), updating: false, problems: [.lowDisk(freeGB: 1)], jobPercent: nil)
                == .error)
    }

    @Test func theShortStampNamesTheCommit() {
        #expect(WorkspaceStamp(stamp: "5faffacca071b90cf438", commit: "0cf2582").short == "0cf2582 · 5faffacca071")
        #expect(WorkspaceStamp(stamp: "5faffacca071b90cf438", commit: "").short == "5faffacca071")
    }
}
