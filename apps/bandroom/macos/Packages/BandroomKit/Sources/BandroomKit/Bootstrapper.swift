import Foundation
import Observation

/// The engine environment (design/shared/server-app.md §5.1 option A). First run: copy the workspace that ships in the app
/// (pixi.toml, pixi.lock and the engine source) into `<data>/envs`, then `pixi install` from the lockfile; a
/// checkout only needs the install. The install always runs: an environment left from an earlier build may not
/// match the lockfile just copied in, and the engine must not install it at launch (it would outlast the health
/// timeout). With an environment that matches, it takes seconds. After an app update: replace that copy with the app's
/// (`WorkspaceSwap`) and install again only when the lockfile changed; a failure puts the old copy back. Only the
/// engine's own environment is installed here: the engine can start once it is there, and the models'
/// environments are installed behind it (`ModelEnvironments`).
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

    @ObservationIgnored private let launcher: ProcessLauncher
    /// The `pixi install` under way. It runs in its own process group, so quitting Bandroom doesn't stop it.
    @ObservationIgnored private var installPid: Int32?

    public init(launcher: ProcessLauncher = PosixLauncher()) {
        self.launcher = launcher
    }

    /// 0…100 for the brass bar: copying is quick, the install is most of it.
    public var percent: Int {
        switch phase {
        case .idle: 0
        case .copying: 5
        case .installing: 30
        case .done: 100
        case .failed: 0
        }
    }

    /// A copy or an install is under way.
    public var isInstalling: Bool {
        phase == .copying || phase == .installing
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
            let failed = try await installEngine(configuration, base: base)
            phase = failed.map { .failed(Self.stopped($0)) } ?? .done
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// Replaces the installed workspace with the app's; the engine must be stopped first. Returns whether the new
    /// copy is in place. The engine's environment is installed again when the lockfile changed, or it is not there
    /// (or was not installed to its end), and a failure there puts the old copy back.
    @discardableResult
    public func update(configuration: EngineConfiguration, bundledWorkspace: URL, lockChanged: Bool,
                       base: [String: String] = ProcessInfo.processInfo.environment) async -> Bool {
        isUpdate = true
        reset()
        let source = configuration.source
        phase = .copying
        do {
            let swap = try await Task.detached { try WorkspaceSwap.install(from: bundledWorkspace, into: source.workspace) }.value
            if lockChanged || !source.isEnvironmentReady || !source.isInstalled(configuration.environmentName) {
                phase = .installing
                let failed: Installed?
                do {
                    failed = try await installEngine(configuration, base: base)
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
            phase = .done
            return true
        } catch {
            phase = .failed(String(describing: error))
            return false
        }
    }

    private func reset() {
        pixiRefusal = nil
        trouble = nil
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

    /// `pixi install` of the engine's environment, marked installed for this lockfile when it ran to its end;
    /// returns what stopped it, nil when it did not.
    private func installEngine(_ configuration: EngineConfiguration, base: [String: String]) async throws -> Installed? {
        let name = configuration.environmentName
        let plan = try configuration.installPlan(base: base, environment: name)
        let status: Int32 = try await withCheckedThrowingContinuation { cont in
            do {
                installPid = try launcher.launch(plan) { cont.resume(returning: $0) }
            } catch {
                cont.resume(throwing: error)
            }
        }
        installPid = nil
        guard status == 0 else {
            pixiRefusal = PixiRefusal.inLatestRun(log: plan.log)
            trouble = InstallTrouble.inLatestRun(log: plan.log)
            return (status, plan.log, name)
        }
        if case .installed = configuration.source { try? configuration.source.markInstalled(name) }
        return nil
    }
}
