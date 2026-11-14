import Foundation
import Observation

/// The reader of printed music (homr, AGPL-3.0): what turns a picture or a PDF of sheet music into notes for the
/// engine's `sheet` and `sheet-tab` profiles. It is no part of setup and no part of the app: this Mac fetches it,
/// from where its makers publish it, only when the person asks for it in Settings. The engine offers the two
/// profiles where its environment is (`environment_installed` in the engine's adapters.py), looked for again at
/// every request, so nothing restarts when it arrives.
public enum SheetReader {
    /// The adapter's name: its folder among the adapters, and the folder of its weights under the models folder.
    public static let adapter = "homr"
    public static let licence = "AGPL-3.0"
    /// Its makers' page: what it is, its source and its licence.
    public static let page = URL(string: "https://github.com/liebharc/homr")!
    /// What is fetched, about: the environment from PyPI, and the weights from homr's release on GitHub.
    public static let downloadBytes: Int64 = 475_000_000 + 139_000_000
    /// The free space an install asks for: the download, the copy in the installer's cache, and room to spare.
    public static let neededFreeBytes: Int64 = 2_000_000_000
    /// The line the adapter runner ends on when the weights could not be fetched (run_adapter.py, REFUSAL).
    static let weightsNotFetched = "scribe-refusal: weights_missing"
    /// The line it ends on when the disk filled up while the weights were written.
    static let diskFull = "scribe-refusal: no_space"
    /// Why a failed install failed, if what it wrote says: the runner's own names for a full disk and for weights
    /// it could not fetch, else the installer's words (`InstallTrouble`). Nil when it says neither.
    static func reason(in output: String) -> SheetReaderFailure? {
        switch InstallTrouble.find(in: output, refusals: [diskFull: .diskFull, weightsNotFetched: .network]) {
        case .network: .network
        case .diskFull: .diskFull
        case nil: nil
        }
    }
    /// In a checkout, written into the environment once an install here ran to its end, so it goes when the
    /// environment goes.
    static let marker = ".scribe-reader-installed"
}

extension EngineSource {
    /// The adapters the engine runs: the workspace's own, a checkout's or the installed copy in the data folder.
    public var adaptersFolder: URL {
        workspace.appending(path: "ml/adapters", directoryHint: .isDirectory)
    }

    /// The reader's environment, where the engine looks for it (`environment_installed` in its adapters.py): the
    /// pixi environment of its name in an installed workspace, which an app update leaves in place; in a checkout,
    /// where the adapters run in their own projects, the `.venv` beside the adapter.
    public var readerEnvironment: URL {
        switch self {
        case .checkout: adaptersFolder.appending(path: "\(SheetReader.adapter)/.venv", directoryHint: .isDirectory)
        case .installed: environment(SheetReader.adapter)
        }
    }

    /// The reader is on this Mac: its environment is there and an install here ran to its end (the environment, then
    /// the weights). An installed engine keeps that as the reader's environment marker beside the others, so it
    /// outlasts pixi making the environment afresh, and a lockfile it was not installed for has it brought up to date
    /// with the rest; a checkout keeps it inside the environment.
    public var isReaderInstalled: Bool {
        let fm = FileManager.default
        return switch self {
        case .checkout: fm.fileExists(atPath: readerEnvironment.appending(path: SheetReader.marker).path)
        case .installed:
            fm.fileExists(atPath: setupMarkers.appending(path: "env-\(SheetReader.adapter)").path)
                && fm.fileExists(atPath: readerEnvironment.path)
        }
    }

    /// Records that an install of the reader here ran to its end.
    func markReaderInstalled() throws {
        switch self {
        case .checkout: try Data().write(to: readerEnvironment.appending(path: SheetReader.marker))
        case .installed: try markInstalled(SheetReader.adapter)
        }
    }
}

extension EngineConfiguration {
    /// Installs the reader with the adapter runner itself, run by the engine's Python as the engine runs it
    /// (`run_adapter.py --setup homr`): the runner makes the adapter's environment and fetches its weights, whose
    /// archives, sizes and SHA-256s are pinned there and nowhere else. It picks up where a stopped run left off.
    public func readerInstallPlan(base: [String: String]) throws -> LaunchPlan {
        guard let pixi else { throw LaunchFailure.notInstalled("pixi not found") }
        guard source.isEnvironmentReady else { throw LaunchFailure.notInstalled("no engine at \(source.workspace.path)") }
        return LaunchPlan(executable: pixi,
                          arguments: ["run", "--manifest-path", source.manifest.path, "--frozen", "-e", environmentName,
                                      "python", source.adaptersFolder.appending(path: "run_adapter.py").path, "--setup", SheetReader.adapter],
                          environment: environment(base: base), workingDirectory: source.workspace,
                          log: paths.logs.appending(path: "setup.log"), port: 0)
    }
}

/// Why the reader was not installed, each with its own words in Settings.
public enum SheetReaderFailure: Error, Equatable, Sendable {
    /// There is no engine to install it with yet.
    case notSetUp
    case notEnoughSpace(neededBytes: Int64, freeBytes: Int64)
    /// The environment or the weights could not be fetched: no network, or one that stalled.
    case network
    /// The disk filled up during the install.
    case diskFull
    /// The install stopped on something else; the details are in the setup log.
    case stopped(String)
}

/// What Settings shows of the reader: whether it is on this Mac, and how an install asked for here is going.
public enum SheetReaderState: Equatable, Sendable {
    case notInstalled
    case installing
    case installed
    case failed(SheetReaderFailure)

    /// An install under way or one that stopped is what is shown; otherwise what is on the disk.
    public static func resolve(phase: SheetReaderInstaller.Phase, installed: Bool) -> SheetReaderState {
        switch phase {
        case .installing: .installing
        case .failed(let why): installed ? .installed : .failed(why)
        case .idle, .done: installed ? .installed : .notInstalled
        }
    }
}

/// Installs the reader when it is asked for. One of these lives as long as the app, so closing Settings does not
/// lose an install under way.
@MainActor
@Observable
public final class SheetReaderInstaller {
    public enum Phase: Equatable, Sendable {
        case idle
        case installing
        case done
        case failed(SheetReaderFailure)
    }

    public private(set) var phase: Phase = .idle
    @ObservationIgnored public var log: ((String) -> Void)?

    @ObservationIgnored private let launcher: ProcessLauncher
    @ObservationIgnored private let freeSpace: @Sendable (URL) -> Int64
    /// The install under way. It runs in its own process group, so quitting Bandroom doesn't stop it by itself.
    @ObservationIgnored private var pid: Int32?
    @ObservationIgnored private var cancelled = false

    public init(launcher: ProcessLauncher = PosixLauncher(),
                freeSpace: @escaping @Sendable (URL) -> Int64 = { HostSampler.diskFree($0) }) {
        self.launcher = launcher
        self.freeSpace = freeSpace
    }

    public var isInstalling: Bool { phase == .installing }

    /// Installs it, or tries again. Never throws: what went wrong is the phase, with Try again beside it.
    public func install(configuration: EngineConfiguration, base: [String: String] = ProcessInfo.processInfo.environment) async {
        guard !isInstalling else { return }
        let plan: LaunchPlan
        do {
            plan = try configuration.readerInstallPlan(base: base)
        } catch {
            phase = .failed(.notSetUp)
            return
        }
        let free = freeSpace(configuration.paths.data)
        guard free >= SheetReader.neededFreeBytes else {
            phase = .failed(.notEnoughSpace(neededBytes: SheetReader.neededFreeBytes, freeBytes: free))
            return
        }
        phase = .installing
        cancelled = false
        log?("reader: installing the reader of printed music: \(plan.executable.path) \(plan.arguments.joined(separator: " "))")
        let status: Int32
        do {
            status = try await withCheckedThrowingContinuation { cont in
                do {
                    pid = try launcher.launch(plan) { cont.resume(returning: $0) }
                } catch {
                    cont.resume(throwing: error)
                }
            }
        } catch {
            pid = nil
            log?("reader: the install could not be started: \(error)")
            phase = .failed(.stopped(String(describing: error)))
            return
        }
        pid = nil
        guard !cancelled else { phase = .idle; return }
        guard status == 0 else {
            let why = SheetReader.reason(in: LatestRun.text(log: plan.log))
            log?("reader: the install stopped with \(ExitStatus.describe(status))\(why.map { " (\($0))" } ?? ""); see \(plan.log.path)")
            phase = .failed(why ?? .stopped("\(ExitStatus.describe(status)); see \(plan.log.path)"))
            return
        }
        do {
            try configuration.source.markReaderInstalled()
        } catch {
            log?("reader: its environment is not where the engine looks for it: \(error)")
            phase = .failed(.stopped(String(describing: error)))
            return
        }
        log?("reader: the reader of printed music is installed")
        phase = .done
    }

    /// Stops an install under way (quitting, removing Brasscribe); it is not installed then, and not failed either.
    public func cancel(grace: TimeInterval = 5) {
        guard let pid else { return }
        self.pid = nil
        cancelled = true
        launcher.terminate(pid: pid, grace: grace)
    }
}
