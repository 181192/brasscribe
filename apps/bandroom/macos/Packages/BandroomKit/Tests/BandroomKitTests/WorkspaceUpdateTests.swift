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
        try write("[workspace]\nname = \"brasscribe\"\n", b.appending(path: "pixi.toml"))
        try write(lock, b.appending(path: "pixi.lock"))
        try write(studio, b.appending(path: "engine/src/brasscribe_engine/static/assets/studio.js"))
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
        try write("#!/bin/sh\n", ws.appending(path: ".pixi/envs/default/bin/brasscribe"))
        try write("keep me", ws.appending(path: "notes.txt"))
        try write("{\"devices\": []}", root.appending(path: "data/companion/devices.json"))
        try write("weights", root.appending(path: "data/models/mega53/model.ckpt"))
        return ws
    }

    private func studio(_ ws: URL) -> String? {
        read(ws.appending(path: "engine/src/brasscribe_engine/static/assets/studio.js"))
    }

    private func userDataIsIntact(_ ws: URL, root: URL) {
        #expect(read(ws.appending(path: ".pixi/envs/default/bin/brasscribe")) == "#!/bin/sh\n")
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
        try write("two", a.appending(path: "engine/src/brasscribe_engine/static/assets/studio.js"))
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
        try write("gone in v2", ws.appending(path: "engine/src/brasscribe_engine/removed.py"))
        let v2 = try bundle(in: root, name: "v2", studio: "fixed studio")

        try WorkspaceSwap.install(from: v2, into: ws).commit()
        #expect(studio(ws) == "fixed studio")
        #expect(!fm.fileExists(atPath: ws.appending(path: "engine/src/brasscribe_engine/removed.py").path))
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
        return EngineConfiguration(source: .installed(workspace: workspace, adapters: nil), pixi: URL(fileURLWithPath: "/usr/bin/true"),
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
        #expect(launcher.launched.map(\.arguments.first) == ["install"])
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
        #expect(launcher.launched.map(\.arguments.first) == ["install"])
        #expect(read(ws.appending(path: "pixi.lock")) == "version: 6\n# numpy 2.6\n")
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
        let new = #"{"status":"ok","version":"0.1.0","build":"c3dc2ad 5faffacca071","device":"mps","auth_required":false,"server_id":"a","server_name":"b"}"#
        #expect(try JSONDecoder().decode(Health.self, from: Data(new.utf8)).build == "c3dc2ad 5faffacca071")
    }

    @Test func theUpdateShowsAsUpdatingAndAFailureNeedsAttention() {
        #expect(DisplayState.resolve(setupPercent: nil, phase: .idle, updating: true, problems: [], jobPercent: nil) == .updating)
        #expect(DisplayState.resolve(setupPercent: nil, phase: .running, updating: false, problems: [.updateFailed], jobPercent: nil)
                == .attention(.updateFailed))
    }

    @Test func theShortStampNamesTheCommit() {
        #expect(WorkspaceStamp(stamp: "5faffacca071b90cf438", commit: "0cf2582").short == "0cf2582 · 5faffacca071")
        #expect(WorkspaceStamp(stamp: "5faffacca071b90cf438", commit: "").short == "5faffacca071")
    }
}
