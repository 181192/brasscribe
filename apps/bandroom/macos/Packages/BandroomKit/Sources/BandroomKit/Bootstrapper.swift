import Foundation
import Observation

/// The engine environment (design/server-app.md §5.1 option A). First run: copy the workspace that ships in the app
/// (pixi.toml, pixi.lock and the engine source) into `<data>/envs`, then `pixi install` from the lockfile; a
/// checkout only needs the install. The install always runs: an environment left from an earlier build may not
/// match the lockfile just copied in, and the engine must not install it at launch (it would outlast the health
/// timeout). With an environment that matches, it takes seconds. After an app update: replace that copy with the app's (`WorkspaceSwap`) and
/// install again only when the lockfile changed; a failure puts the old copy back.
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

    /// An update is under way.
    public var isUpdating: Bool {
        isUpdate && (phase == .copying || phase == .installing)
    }

    public func run(configuration: EngineConfiguration, bundledWorkspace: URL?, base: [String: String] = ProcessInfo.processInfo.environment) async {
        isUpdate = false
        do {
            if case .installed(let workspace, _) = configuration.source {
                phase = .copying
                guard let bundledWorkspace else { throw LaunchFailure.notInstalled("this build has no engine workspace") }
                try await Task.detached { try WorkspaceSwap.install(from: bundledWorkspace, into: workspace).commit() }.value
            }
            phase = .installing
            let (status, log) = try await install(configuration, base: base)
            phase = status == 0 ? .done : .failed("pixi install exited with status \(status); see \(log.path)")
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// Replaces the installed workspace with the app's; the engine must be stopped first. Returns whether the new
    /// copy is in place. On failure the old copy is back as it was, and `phase` says why.
    @discardableResult
    public func update(configuration: EngineConfiguration, bundledWorkspace: URL, lockChanged: Bool,
                       base: [String: String] = ProcessInfo.processInfo.environment) async -> Bool {
        isUpdate = true
        let workspace = configuration.source.workspace
        phase = .copying
        do {
            let swap = try await Task.detached { try WorkspaceSwap.install(from: bundledWorkspace, into: workspace) }.value
            if lockChanged || !configuration.source.isEnvironmentReady {
                phase = .installing
                let result: (status: Int32, log: URL)
                do {
                    result = try await install(configuration, base: base)
                } catch {
                    try? swap.rollback()
                    throw error
                }
                if result.status != 0 {
                    try? swap.rollback()
                    phase = .failed("pixi install exited with status \(result.status); see \(result.log.path)")
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

    /// Stops a `pixi install` under way (quitting, removing Brasscribe); the run then fails.
    public func cancel(grace: TimeInterval = 5) {
        guard let pid = installPid else { return }
        installPid = nil
        launcher.terminate(pid: pid, grace: grace)
    }

    private func install(_ configuration: EngineConfiguration, base: [String: String]) async throws -> (status: Int32, log: URL) {
        let plan = try configuration.installPlan(base: base)
        let status: Int32 = try await withCheckedThrowingContinuation { cont in
            do {
                installPid = try launcher.launch(plan) { cont.resume(returning: $0) }
            } catch {
                cont.resume(throwing: error)
            }
        }
        installPid = nil
        return (status, plan.log)
    }
}
