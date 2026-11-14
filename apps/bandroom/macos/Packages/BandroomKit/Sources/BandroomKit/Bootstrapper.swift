import Foundation
import Observation

/// The engine environment (design/shared/server-app.md §5.1 option A). First run: copy the workspace that ships in the app
/// (pixi.toml, pixi.lock and the engine source) into `<data>/envs`, then `pixi install` from the lockfile; a
/// checkout only needs the install. The install always runs: an environment left from an earlier build may not
/// match the lockfile just copied in, and the engine must not install it at launch (it would outlast the health
/// timeout). With an environment that matches, it takes seconds. An installed engine's adapters run through pixi too,
/// each in the environment of its name beside the engine's, so setup installs those next, with the bar moving one
/// share per environment, and no job has to. After an app update: replace that copy with the app's (`WorkspaceSwap`)
/// and install again only when the lockfile changed; a failure puts the old copy back.
@MainActor
@Observable
public final class Bootstrapper {
    public enum Phase: Equatable, Sendable {
        case idle
        case copying
        case installing
        case done
        case failed(String)
    }

    public private(set) var phase: Phase = .idle
    /// The current run replaces an installed copy ("Updating Brasscribe…") rather than making the first one.
    public private(set) var isUpdate = false
    /// Set when the last run failed because pixi refused the workspace (too old for it).
    public private(set) var pixiRefusal: PixiRefusal?
    /// Set when the last run failed and what the install wrote says why: no connection, or a full disk.
    public private(set) var trouble: InstallTrouble?
    /// Set when an update put the new engine in place but an adapter's environment could not be installed with it:
    /// which one, and the log.
    public private(set) var adapterProblem: String?

    @ObservationIgnored private let launcher: ProcessLauncher
    /// The `pixi install` under way. It runs in its own process group, so quitting Bandroom doesn't stop it.
    @ObservationIgnored private var installPid: Int32?

    public init(launcher: ProcessLauncher = PosixLauncher()) {
        self.launcher = launcher
    }

    /// The environment being installed, with its place among the ones this run installs (from 1).
    public struct Step: Equatable, Sendable {
        public let environment: String
        public let index: Int
        public let count: Int
    }

    /// Set while `phase` is `.installing`.
    public private(set) var step: Step?

    /// 0…100 for the brass bar: copying is quick, the installs are the rest, one share each.
    public var percent: Int {
        switch phase {
        case .idle: 0
        case .copying: 5
        case .installing: step.map { 5 + 90 * ($0.index - 1) / max($0.count, 1) } ?? 5
        case .done: 100
        case .failed: 0
        }
    }

    /// An update is under way.
    public var isUpdating: Bool {
        isUpdate && (phase == .copying || phase == .installing)
    }

    public func run(configuration: EngineConfiguration, bundledWorkspace: URL?, base: [String: String] = ProcessInfo.processInfo.environment) async {
        isUpdate = false
        reset()
        do {
            if case .installed(let workspace) = configuration.source {
                phase = .copying
                guard let bundledWorkspace else { throw LaunchFailure.notInstalled("this build has no engine workspace") }
                try await Task.detached { try WorkspaceSwap.install(from: bundledWorkspace, into: workspace).commit() }.value
            }
            phase = .installing
            let names = [configuration.environmentName] + configuration.source.adapterEnvironmentsToInstall
            let failed = try await install(names, configuration, base: base)
            phase = failed.map { .failed(Self.stopped($0)) } ?? .done
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// Replaces the installed workspace with the app's; the engine must be stopped first. Returns whether the new
    /// copy is in place. The engine's environment is installed again when the lockfile changed (or it is missing),
    /// and a failure there puts the old copy back. The adapters' environments come after the new copy is in
    /// place: when the lockfile changed, or one is missing (an engine installed by a Bandroom that ran the adapters
    /// another way has none). One that fails there does not undo the update, whose engine runs; it is said in
    /// `adapterProblem`, a job that needs it installs it, and the next launch tries again (`installAdapters`).
    @discardableResult
    public func update(configuration: EngineConfiguration, bundledWorkspace: URL, lockChanged: Bool,
                       base: [String: String] = ProcessInfo.processInfo.environment) async -> Bool {
        isUpdate = true
        reset()
        let source = configuration.source
        let workspace = source.workspace
        phase = .copying
        do {
            let swap = try await Task.detached { try WorkspaceSwap.install(from: bundledWorkspace, into: workspace) }.value
            let engine = lockChanged || !source.isEnvironmentReady ? [configuration.environmentName] : []
            let adapters = lockChanged || !source.areAdapterEnvironmentsReady ? source.adapterEnvironmentsToInstall : []
            let count = engine.count + adapters.count
            if !engine.isEmpty {
                phase = .installing
                let failed: Installed?
                do {
                    failed = try await install(engine, configuration, base: base, of: count)
                } catch {
                    try? swap.rollback()
                    throw error
                }
                if let failed {
                    try? swap.rollback()
                    phase = .failed(Self.stopped(failed))
                    return false
                }
            }
            do {
                try swap.commit()
            } catch {
                try? swap.rollback()
                throw error
            }
            if !adapters.isEmpty {
                phase = .installing
                await installAdaptersNow(adapters, configuration, base: base, from: engine.count, of: count)
            }
            phase = .done
            return true
        } catch {
            phase = .failed(String(describing: error))
            return false
        }
    }

    /// Installs the adapters' environments that are missing from an installed engine whose workspace is this app's:
    /// the ones an update could not install (no connection then, say). Never fails the engine; what stopped it is
    /// in `adapterProblem`. Returns whether any were missing.
    @discardableResult
    public func installAdapters(configuration: EngineConfiguration,
                                base: [String: String] = ProcessInfo.processInfo.environment) async -> Bool {
        let missing = configuration.source.adapterEnvironmentsToInstall.filter {
            !FileManager.default.fileExists(atPath: configuration.source.environment($0).path)
        }
        guard !missing.isEmpty else { return false }
        isUpdate = true
        reset()
        phase = .installing
        await installAdaptersNow(missing, configuration, base: base, from: 0, of: missing.count)
        phase = .done
        return true
    }

    private func installAdaptersNow(_ names: [String], _ configuration: EngineConfiguration, base: [String: String],
                                    from offset: Int, of count: Int) async {
        do {
            if let failed = try await install(names, configuration, base: base, from: offset, of: count) {
                adapterProblem = Self.stopped(failed)
            }
        } catch {
            adapterProblem = String(describing: error)
        }
    }

    private func reset() {
        pixiRefusal = nil
        trouble = nil
        adapterProblem = nil
    }

    /// Shows a run that stopped, without running one: for the screen catalogue.
    public func showFailed(_ why: String, trouble: InstallTrouble?) {
        phase = .failed(why)
        self.trouble = trouble
    }

    /// Stops a `pixi install` under way (quitting, removing Brasscribe); the run then fails.
    public func cancel(grace: TimeInterval = 5) {
        guard let pid = installPid else { return }
        installPid = nil
        launcher.terminate(pid: pid, grace: grace)
    }

    private typealias Installed = (status: Int32, log: URL, environment: String)

    private static func stopped(_ result: Installed) -> String {
        "pixi install -e \(result.environment) stopped with \(ExitStatus.describe(result.status)); see \(result.log.path)"
    }

    /// `pixi install` for each of `names` in turn, counted from `offset` among `count` for the bar; stops at the
    /// first that fails, and returns it (nil when all were installed). One that is already what the lockfile asks
    /// for takes seconds.
    private func install(_ names: [String], _ configuration: EngineConfiguration, base: [String: String],
                         from offset: Int = 0, of count: Int? = nil) async throws -> Installed? {
        defer { step = nil }
        for (i, name) in names.enumerated() {
            step = Step(environment: name, index: offset + i + 1, count: count ?? names.count)
            let plan = try configuration.installPlan(base: base, environment: name)
            let status: Int32 = try await withCheckedThrowingContinuation { cont in
                do {
                    installPid = try launcher.launch(plan) { cont.resume(returning: $0) }
                } catch {
                    cont.resume(throwing: error)
                }
            }
            installPid = nil
            if status != 0 {
                pixiRefusal = PixiRefusal.inLatestRun(log: plan.log)
                trouble = InstallTrouble.inLatestRun(log: plan.log)
                return (status, plan.log, name)
            }
        }
        return nil
    }
}
