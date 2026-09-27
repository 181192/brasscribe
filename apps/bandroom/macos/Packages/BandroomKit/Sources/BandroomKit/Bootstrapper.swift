import Foundation
import Observation

/// First-run setup of the engine environment (design/server-app.md §5.1 option A): copy the workspace that
/// ships in the app (pixi.toml, pixi.lock and the engine source) into `<data>/envs`, then `pixi install`
/// from the lockfile. A checkout only needs the install.
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

    @ObservationIgnored private let launcher: ProcessLauncher

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

    public func run(configuration: EngineConfiguration, bundledWorkspace: URL?, base: [String: String] = ProcessInfo.processInfo.environment) async {
        do {
            if case .installed(let workspace, _) = configuration.source {
                phase = .copying
                guard let bundledWorkspace else { throw LaunchFailure.notInstalled("this build has no engine workspace") }
                try Self.syncWorkspace(from: bundledWorkspace, to: workspace)
            }
            if configuration.source.isEnvironmentReady {
                phase = .done
                return
            }
            phase = .installing
            let plan = try configuration.installPlan(base: base)
            let status: Int32 = try await withCheckedThrowingContinuation { cont in
                do {
                    _ = try launcher.launch(plan) { cont.resume(returning: $0) }
                } catch {
                    cont.resume(throwing: error)
                }
            }
            phase = status == 0 ? .done : .failed("pixi install exited with status \(status); see \(plan.log.path)")
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// Copies files that differ (by size and date) so an update fetches only what changed.
    nonisolated static func syncWorkspace(from source: URL, to dest: URL) throws {
        let fm = FileManager.default
        try fm.createDirectory(at: dest, withIntermediateDirectories: true)
        guard let walker = fm.enumerator(at: source, includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey, .contentModificationDateKey]) else { return }
        let base = source.standardizedFileURL.path
        for case let url as URL in walker {
            let rel = String(url.standardizedFileURL.path.dropFirst(base.count + 1))
            let target = dest.appending(path: rel)
            let values = try url.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey, .contentModificationDateKey])
            if values.isDirectory == true {
                try fm.createDirectory(at: target, withIntermediateDirectories: true)
                continue
            }
            if let existing = try? target.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey]),
               existing.fileSize == values.fileSize, existing.contentModificationDate == values.contentModificationDate {
                continue
            }
            try? fm.removeItem(at: target)
            try fm.copyItem(at: url, to: target)
        }
    }
}
