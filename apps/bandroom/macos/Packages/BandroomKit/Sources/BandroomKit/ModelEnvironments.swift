import Foundation
import Observation

/// The models' environments of an installed engine (`EngineSource.adapterEnvironmentsToInstall`), installed behind
/// it: the engine starts once its own environment is there (`Bootstrapper`), and these follow, one `pixi install`
/// each, so no job has to install one. Each that runs to its end is marked installed for the workspace's lockfile;
/// one that fails is skipped and the rest go on, so what was installed can be used, and the failed ones are said
/// together, with Try again. One that stopped part-way (quit, no connection) has no marker and is installed again
/// the next time. One lives as long as the app.
@MainActor
@Observable
public final class ModelEnvironments {
    /// The environment being installed, with its place among the ones this run installs (from 1).
    public struct Step: Equatable, Sendable {
        public let environment: String
        public let index: Int
        public let count: Int

        public init(environment: String, index: Int, count: Int) {
            self.environment = environment; self.index = index; self.count = count
        }
    }

    public enum Phase: Equatable, Sendable {
        case idle
        case installing(Step)
        /// Every one that was pending is installed.
        case done
        /// These could not be installed; `trouble` is what their installs said, when it said.
        case failed([String], trouble: InstallTrouble?)
    }

    public private(set) var phase: Phase = .idle
    @ObservationIgnored public var log: ((String) -> Void)?

    @ObservationIgnored private let launcher: ProcessLauncher
    /// The `pixi install` under way, in its own process group.
    @ObservationIgnored private var pid: Int32?
    @ObservationIgnored private var cancelled = false

    public init(launcher: ProcessLauncher = PosixLauncher()) {
        self.launcher = launcher
    }

    public var isInstalling: Bool {
        if case .installing = phase { true } else { false }
    }

    /// Installs every pending one (`EngineSource.pendingModelEnvironments`), or tries the failed ones again. Never
    /// throws: what went wrong is the phase.
    public func install(configuration: EngineConfiguration, base: [String: String] = ProcessInfo.processInfo.environment) async {
        guard !isInstalling else { return }
        let source = configuration.source
        let pending = source.pendingModelEnvironments
        guard !pending.isEmpty else {
            if case .failed = phase { phase = .done }
            return
        }
        cancelled = false
        var failed: [String] = []
        var trouble: InstallTrouble?
        for (i, name) in pending.enumerated() {
            phase = .installing(Step(environment: name, index: i + 1, count: pending.count))
            // Jobs that use it first finish; one that needs it from now on waits for this install.
            guard let lock = await EnvironmentLock.exclusive(source.environmentLocks.appending(path: "\(name).lock"),
                                                             while: { [weak self] in !(self?.cancelled ?? true) }) else {
                if cancelled { phase = .idle; return }
                log?("models: \(name) could not be locked for its install")
                failed.append(name)
                continue
            }
            defer { lock.release() }
            // A stage that needed it meanwhile may have installed it itself (the engine's envlock.py).
            if source.isInstalled(name) { continue }
            let status: Int32
            let plan: LaunchPlan
            do {
                plan = try configuration.installPlan(base: base, environment: name)
                status = try await withCheckedThrowingContinuation { cont in
                    do {
                        pid = try launcher.launch(plan) { cont.resume(returning: $0) }
                    } catch {
                        cont.resume(throwing: error)
                    }
                }
            } catch {
                pid = nil
                log?("models: \(name) could not be installed: \(error)")
                failed.append(name)
                continue
            }
            pid = nil
            if cancelled { phase = .idle; return }
            if status == 0 {
                do {
                    try source.markInstalled(name)
                    log?("models: \(name) is installed")
                } catch {
                    log?("models: \(name) is installed, but could not be marked so: \(error)")
                }
            } else {
                let said = InstallTrouble.inLatestRun(log: plan.log)
                trouble = said ?? trouble
                log?("models: pixi install -e \(name) stopped with \(ExitStatus.describe(status))\(said.map { " (\($0))" } ?? ""); see \(plan.log.path)")
                failed.append(name)
            }
        }
        phase = failed.isEmpty ? .done : .failed(failed, trouble: trouble)
    }

    /// Stops an install under way (an update replacing the workspace, quitting); what it was installing has no
    /// marker and is installed again next time.
    public func cancel(grace: TimeInterval = 5) {
        guard isInstalling else { return }
        cancelled = true
        guard let pid else { return }  // still waiting for its lock: that wait ends
        self.pid = nil
        launcher.terminate(pid: pid, grace: grace)
    }

    /// Shows a state without installing anything: for the screen catalogue.
    public func show(_ phase: Phase) {
        self.phase = phase
    }
}

/// An exclusive `flock` on an environment's lock file (`EngineSource.environmentLocks`), the one the engine holds
/// shared while a stage uses the environment, or exclusively while it installs it (envlock.py). The kernel drops it
/// when Bandroom ends.
final class EnvironmentLock: @unchecked Sendable {
    private let fd: Int32

    private init(fd: Int32) { self.fd = fd }

    /// Waits until no job holds it and takes it; nil when `going` turns false first, or the file cannot be opened.
    static func exclusive(_ file: URL, while going: @MainActor () -> Bool) async -> EnvironmentLock? {
        try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        let fd = open(file.path, O_RDWR | O_CREAT | O_CLOEXEC, 0o600)
        guard fd >= 0 else { return nil }
        while await going() {
            if flock(fd, LOCK_EX | LOCK_NB) == 0 { return EnvironmentLock(fd: fd) }
            try? await Task.sleep(for: .milliseconds(250))
        }
        close(fd)
        return nil
    }

    func release() {
        flock(fd, LOCK_UN)
        close(fd)
    }
}
