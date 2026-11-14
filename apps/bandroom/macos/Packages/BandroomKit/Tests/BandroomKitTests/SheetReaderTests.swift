import Foundation
import Testing
@testable import BandroomKit

/// The reader of printed music (homr, AGPL-3.0) is fetched on this Mac only when it is asked for in Settings: never
/// by setup, never from the app, and by the adapter runner itself, which alone pins its weights.
@MainActor
@Suite struct SheetReaderTests {
    /// An installed engine in a folder of its own: the workspace with its engine command, and the app's adapters.
    private func installed(adapters: Bool = true, engine: Bool = true) throws -> (config: EngineConfiguration, root: URL) {
        let fm = FileManager.default
        let root = tempDir()
        let paths = BandroomPaths(data: root.appending(path: "data"), logs: root.appending(path: "logs"))
        try fm.createDirectory(at: paths.workspace, withIntermediateDirectories: true)
        fm.createFile(atPath: paths.workspace.appending(path: "pixi.toml").path, contents: Data())
        if engine {
            let bin = paths.workspace.appending(path: ".pixi/envs/default/bin")
            try fm.createDirectory(at: bin, withIntermediateDirectories: true)
            fm.createFile(atPath: bin.appending(path: EngineSource.command).path, contents: Data())
        }
        let app = root.appending(path: "Bandroom.app/Contents/Resources/workspace/ml/adapters", directoryHint: .isDirectory)
        if adapters { try fm.createDirectory(at: app.appending(path: SheetReader.adapter), withIntermediateDirectories: true) }
        let config = EngineConfiguration(source: .installed(workspace: paths.workspace, adapters: adapters ? app : nil),
                                         pixi: URL(fileURLWithPath: "/app/bin/pixi"), paths: paths, computerName: "Kari's MacBook",
                                         adminToken: "secret")
        return (config, root)
    }

    /// The runner, as far as the test goes: it makes the adapter's environment, as `uv run` does.
    private func runnerMakesTheEnvironment(_ config: EngineConfiguration) throws {
        try FileManager.default.createDirectory(at: config.source.readerEnvironment, withIntermediateDirectories: true)
    }

    private let base = ["HOME": "/home/test", "PATH": "/nowhere"]

    @Test func theInstallIsTheRunnersOwnSetupRunAsTheEngineRunsIt() throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        let plan = try config.readerInstallPlan(base: base)
        #expect(plan.executable.path == "/app/bin/pixi")
        #expect(plan.arguments == ["run", "--manifest-path", config.source.manifest.path, "--frozen", "-e", "default", "python",
                                   config.source.adaptersFolder.appending(path: "run_adapter.py").path, "--setup", "homr"])
        // The engine's own environment: the weights go to the models folder it reads.
        #expect(plan.environment == config.environment(base: base))
        #expect(plan.environment["SCRIBE_MODELS"] == config.paths.models.path)
        #expect(plan.log.lastPathComponent == "setup.log")
    }

    @Test func theEnvironmentIsWhereTheEngineLooksForIt() throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        // The engine is given the app's adapters, and on a Mac looks for <adapters>/<name>/.venv.
        #expect(config.environment(base: base)["SCRIBE_ADAPTERS"] == config.source.adaptersFolder.path)
        #expect(config.source.readerEnvironment.path == config.source.adaptersFolder.appending(path: "homr/.venv").path)
        // Without adapters of the app's, the engine uses the installed workspace's; a checkout its own.
        let (plain, other) = try installed(adapters: false)
        defer { try? FileManager.default.removeItem(at: other) }
        #expect(plain.environment(base: base)["SCRIBE_ADAPTERS"] == nil)
        #expect(plain.source.adaptersFolder.path == plain.paths.workspace.appending(path: "ml/adapters").path)
        let checkout = EngineSource.checkout(URL(fileURLWithPath: "/src/brasscribe", isDirectory: true))
        #expect(checkout.readerEnvironment.path == "/src/brasscribe/ml/adapters/homr/.venv")
    }

    @Test(.enabled(if: enginesWireIsRead)) func theEngineAndTheRunnerHaveWhatTheInstallAsksFor() throws {
        let root = try #require(repository())
        let engine = try String(contentsOf: root.appending(path: "engine/src/scribe_engine/adapters.py"), encoding: .utf8)
        #expect(engine.contains("(adapters_dir / name / \".venv\").is_dir()"))
        let runner = try String(contentsOf: root.appending(path: "ml/adapters/run_adapter.py"), encoding: .utf8)
        #expect(runner.contains("argv == [\"--setup\", \"homr\"]"))
        #expect(runner.contains("REFUSAL = \"scribe-refusal: \"") && runner.contains("{REFUSAL}weights_missing"))
        #expect(SheetReader.weightsNotFetched == "scribe-refusal: weights_missing")
        #expect(FileManager.default.fileExists(atPath: root.appending(path: "ml/adapters/homr/pyproject.toml").path))
        // The weights are pinned in the runner alone: nothing in Bandroom names an archive of them.
        let pinned = runner.matches(of: /"((?:segnet|encoder|decoder)[\w-]+\.zip)"/).map { String($0.output.1) }
        #expect(pinned.count == 3)
        let sources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "Sources/BandroomKit")
        for file in try FileManager.default.contentsOfDirectory(at: sources, includingPropertiesForKeys: nil) {
            let text = try String(contentsOf: file, encoding: .utf8)
            #expect(!pinned.contains { text.contains($0) }, "\(file.lastPathComponent)")
        }
    }

    @Test func askedForItInstallsAndIsThenThere() async throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        let launcher = FakeLauncher()
        let reader = SheetReaderInstaller(launcher: launcher, freeSpace: { _ in 200_000_000_000 })
        #expect(!config.source.isReaderInstalled)
        #expect(SheetReaderState.resolve(phase: reader.phase, installed: false) == .notInstalled)

        let run = Task { await reader.install(configuration: config, base: base) }
        await settle()
        #expect(reader.phase == .installing)
        #expect(SheetReaderState.resolve(phase: reader.phase, installed: false) == .installing)
        await reader.install(configuration: config, base: base)  // asked again while it runs: nothing more starts
        #expect(launcher.launched.count == 1)
        #expect(launcher.launched[0] == (try config.readerInstallPlan(base: base)))

        try runnerMakesTheEnvironment(config)
        launcher.crash(launcher.nextPid, status: 0)
        await run.value
        #expect(reader.phase == .done)
        #expect(config.source.isReaderInstalled)
        #expect(SheetReaderState.resolve(phase: reader.phase, installed: true) == .installed)
    }

    @Test func anEnvironmentWithoutAFinishedInstallIsNotCalledInstalled() throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        try runnerMakesTheEnvironment(config)  // an install that stopped half way, or one the engine's first job made
        #expect(!config.source.isReaderInstalled)
    }

    @Test func weightsThatCouldNotBeFetchedAreANetworkProblem() async throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        let launcher = FakeLauncher()
        let reader = SheetReaderInstaller(launcher: launcher, freeSpace: { _ in 200_000_000_000 })
        let log = try config.readerInstallPlan(base: base).log
        try FileManager.default.createDirectory(at: log.deletingLastPathComponent(), withIntermediateDirectories: true)
        // An earlier run that failed on the network, then this one, which fails on something else.
        try Data("--- then pixi run\nscribe-refusal: weights_missing\n\n--- now pixi run\nerror: no space left on device\n".utf8).write(to: log)
        launcher.exitStatus = 4 << 8
        await reader.install(configuration: config, base: base)
        guard case .failed(.stopped(let why)) = reader.phase else { Issue.record("\(reader.phase)"); return }
        #expect(why.contains("exit code 4") && why.contains("setup.log"))
        #expect(!config.source.isReaderInstalled)

        try Data("\n--- now pixi run\nurlopen error: no route to the host\nscribe-refusal: weights_missing\n".utf8).write(to: log)
        await reader.install(configuration: config, base: base)
        #expect(reader.phase == .failed(.network))
        #expect(SheetReaderState.resolve(phase: reader.phase, installed: false) == .failed(.network))

        // Try again: the same run once more, and this time it gets there.
        try runnerMakesTheEnvironment(config)
        launcher.exitStatus = 0
        await reader.install(configuration: config, base: base)
        #expect(reader.phase == .done && config.source.isReaderInstalled)
        #expect(launcher.launched.count == 3)
    }

    @Test func tooLittleSpaceOrNoEngineStartsNothing() async throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        let launcher = FakeLauncher()
        let tight = SheetReaderInstaller(launcher: launcher, freeSpace: { _ in 1_200_000_000 })
        await tight.install(configuration: config, base: base)
        #expect(tight.phase == .failed(.notEnoughSpace(neededBytes: SheetReader.neededFreeBytes, freeBytes: 1_200_000_000)))
        #expect(SheetReader.neededFreeBytes > SheetReader.downloadBytes)

        let (noEngine, other) = try installed(engine: false)
        defer { try? FileManager.default.removeItem(at: other) }
        let reader = SheetReaderInstaller(launcher: launcher, freeSpace: { _ in 200_000_000_000 })
        await reader.install(configuration: noEngine, base: base)
        #expect(reader.phase == .failed(.notSetUp))
        #expect(launcher.launched.isEmpty)
    }

    @Test func quittingStopsTheInstallWithoutCallingItAFailure() async throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        let launcher = FakeLauncher()
        let reader = SheetReaderInstaller(launcher: launcher, freeSpace: { _ in 200_000_000_000 })
        let run = Task { await reader.install(configuration: config, base: base) }
        await settle()
        reader.cancel()
        await run.value
        #expect(launcher.terminated == [launcher.nextPid])
        #expect(reader.phase == .idle)
        #expect(!config.source.isReaderInstalled)
    }

    @Test func firstRunSetupNeverAsksForIt() throws {
        let (config, root) = try installed()
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(try config.installPlan(base: base).arguments.last == "default")
        #expect(!ModelComponent.allCases.contains { component in
            if case .models(let folder) = component.home { folder == SheetReader.adapter } else { false }
        })
        #expect(SheetReader.page.absoluteString == "https://github.com/liebharc/homr" && SheetReader.licence == "AGPL-3.0")
    }
}
