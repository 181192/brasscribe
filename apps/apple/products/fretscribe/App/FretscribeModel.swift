import Foundation
import Observation
import SwiftUI
import TabKit
import TranscriptionKit
import UniformTypeIdentifiers

/// Something the player brought in, waiting for "What is this?".
struct PendingSource: Identifiable, Hashable {
    var id = UUID()
    var audioURL: URL
    var title: String
    /// The file name shown above "What is this?" ("Riff.m4a"); nil for a new recording.
    var name: String?
}

/// What "What is this?" was answered with: how the computer listens.
enum RecordingKind: String, CaseIterable, Identifiable {
    /// A band or a record: the instrument is picked out of it first.
    case song
    /// The instrument alone.
    case instrument
    var id: String { rawValue }
}

/// Something went wrong, with what to do next. The player's songs are never touched.
enum FretscribeProblem: Hashable {
    case cantOpenFile(String)
    case sheetMusic
    case copyProtected
    case silence
    case tabFailed(String)
    case cantOpenTab(String)
    case needsUpdate(InterfaceMatch.Update)
}

enum Route: Hashable {
    case whatIsThis(PendingSource)
    case transcribing(UUID)
    case check(TabSong)
    case tab(TabSong)
    case problem(FretscribeProblem)
}

/// A row in Your songs: a song on this device, or a finished tab on the paired computer.
struct SongEntry: Identifiable, Hashable {
    enum Location: Hashable { case local(TabSong), computer(jobID: String) }
    var id: String
    var title: String
    var date: Date
    var location: Location
    var toCheck: Int
    var preset: String?
}

/// Fretscribe's state: the computer and the connection to it, the player's instrument, the songs, and where the
/// screens are.
@Observable @MainActor
final class FretscribeModel: PlayHost {
    /// The engine's target this app makes: tab for fretted instruments.
    static let target = "fretted"
    /// The engine's profile for a tab.
    static let profile = "tab"

    var songs: [SongEntry] = []
    private(set) var local: [TabSong] = TabSong.loadAll() { didSet { rebuild() } }
    /// The computer's tabs as it last listed them; empty whenever it is not connected.
    var computerJobs: [CompanionService.Job] = [] { didSet { rebuild() } }
    var path: [Route] = []
    var jobs: [UUID: TabJob] = [:]
    var showSettings = false
    var showRecorder = false
    var showCapture = false
    var showYourInstrument = false
    var importing = false
    var openingSong: String?
    var deleteTarget: SongEntry?

    /// What the player plays: Your instrument, asked on the first run and in Settings.
    var instrument: YourInstrument {
        didSet { if instrument != oldValue { instrumentStore.save(instrument) } }
    }
    @ObservationIgnored private let instrumentStore: YourInstrumentStore

    /// The first run is over once Your instrument was saved.
    var firstRunDone: Bool = UserDefaults.standard.bool(forKey: "fs_first_run_done") {
        didSet { UserDefaults.standard.set(firstRunDone, forKey: "fs_first_run_done") }
    }

    var companionURL: String = ProcessInfo.processInfo.environment["SCRIBE_COMPANION"] ?? UserDefaults.standard.string(forKey: "companionURL") ?? "http://localhost:8765" {
        didSet { UserDefaults.standard.set(companionURL, forKey: "companionURL") }
    }
    var pendingLink: PairingLink?

    /// Practice: the recording under the tab, kept for each song while the app runs and on the device.
    let practice: PracticeModel

    init(defaults: UserDefaults = .standard) {
        instrumentStore = YourInstrumentStore(defaults)
        instrument = YourInstrumentStore(defaults).load()
        let support = URL.applicationSupportDirectory.appending(path: "Fretscribe", directoryHint: .isDirectory)
        practice = PracticeModel(recordings: support.appending(path: "Recordings"), places: support.appending(path: "Practice"))
        if LaunchOptions.reset { firstRunDone = LaunchOptions.skipFirstRun }
        rebuild()
    }

    /// Engine credentials: the Keychain, or memory for tests and screenshots (`-reset`).
    static func makeCredentialStore() -> CredentialStore {
        if LaunchOptions.reset || ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil { return InMemoryCredentialStore() }
        return KeychainCredentialStore()
    }

    @ObservationIgnored private(set) lazy var connection: ConnectionMonitor = {
        let m = ConnectionMonitor(store: Self.makeCredentialStore())
        #if os(macOS)
        if let url = URL(string: companionURL), ["localhost", "127.0.0.1", "::1"].contains(url.host() ?? "") { m.localAddress = url }
        #endif
        return m
    }()

    var engineURL: URL {
        (connection.staged ? nil : connection.record?.baseURL) ?? URL(string: companionURL) ?? URL(string: "http://localhost:8765")!
    }

    /// Engine output served from a folder: only tests and screenshots set it (SCRIBE_FIXTURES with `-fixture-service`).
    let fixtureDirectory: URL? = {
        guard let d = ProcessInfo.processInfo.environment["SCRIBE_FIXTURES"], FileManager.default.fileExists(atPath: d) else { return nil }
        return URL(fileURLWithPath: d)
    }()

    var useFixtureService: Bool { fixtureDirectory != nil && LaunchOptions.args.contains("-fixture-service") }

    func service() -> TranscriptionService {
        if useFixtureService, let dir = fixtureDirectory {
            return FixtureService(directory: dir, stepDelay: LaunchOptions.args.contains("-fast") ? 0.05 : 0.6, outputName: "tab")
        }
        return CompanionService(baseURL: engineURL, token: connection.record?.token)
    }

    /// A computer is paired, or Bandroom runs on this Mac.
    var computerPaired: Bool { connection.record != nil || connection.localAddress != nil }

    /// The computer counts as there when it is Connected or still Reconnecting.
    var computerThere: Bool {
        if useFixtureService { return true }
        guard computerPaired else { return false }
        switch connection.state.kind {
        case .connected, .reconnecting: return true
        case .offline, .needsPairing, .mismatch: return false
        }
    }

    // MARK: PlayHost

    /// Fretscribe and Bandroom are downloaded from the repository's latest release.
    let downloads = URL(string: "https://github.com/181192/brasscribe/releases/latest")!

    func pairedWithComputer() async { await refreshComputerSongs() }
    func recorded(_ url: URL, title: String) { ask(PendingSource(audioURL: url, title: title)) }
    func recordedSilence() { show(.silence) }

    // MARK: songs

    func refresh() { local = TabSong.loadAll() }

    private func rebuild() {
        let downloaded = Set(local.compactMap(\.jobID))
        var rows = local.map { s in
            SongEntry(id: s.id.uuidString, title: s.title, date: s.created, location: .local(s), toCheck: s.toCheck, preset: s.preset)
        }
        for j in computerJobs where j.status == "succeeded" && !downloaded.contains(j.id) && j.outputs.contains("tab.musicxml") {
            let date = Date(timeIntervalSince1970: j.created ?? 0)
            rows.append(SongEntry(id: "job:\(j.id)", title: SongTitles.display(j.title ?? "", made: date), date: date,
                                  location: .computer(jobID: j.id), toCheck: 0, preset: nil))
        }
        songs = rows.sorted { $0.date > $1.date }
    }

    @ObservationIgnored private var connectionChanges = 0

    /// The computer's finished tabs; they go when the computer is not there.
    func refreshComputerSongs() async {
        guard !useFixtureService, let svc = service() as? CompanionService else { computerJobs = []; return }
        let asked = connectionChanges
        do {
            let jobs = try await svc.jobs(of: Self.target)
            guard asked == connectionChanges, connection.state.kind == .connected else { return }
            computerJobs = jobs
        } catch {
            let update = refused(error)
            guard asked == connectionChanges else { return }
            if update != nil || connection.state.kind != .connected { computerJobs = [] }
        }
    }

    func connectionChanged() async {
        connectionChanges += 1
        if case .connected = connection.state { await refreshComputerSongs() } else { computerJobs = [] }
    }

    @discardableResult
    func refused(_ error: Error) -> InterfaceMatch.Update? {
        guard case TranscriptionError.interfaceMismatch(let which) = error else { return nil }
        connection.poke()
        return which
    }

    func open(_ entry: SongEntry) {
        switch entry.location {
        case .local(let s): path = [.tab(s)]
        case .computer(let jobID): Task { await download(jobID: jobID, title: entry.title) }
        }
    }

    /// Copies a tab from the computer into Your songs on this device, then opens it.
    private func download(jobID: String, title: String) async {
        guard let svc = service() as? CompanionService else { return }
        openingSong = "job:\(jobID)"
        defer { openingSong = nil }
        do {
            let xml = try await svc.artifact(.musicXML, jobID: jobID)
            let tab = try? await svc.artifact(.tab, jobID: jobID)
            let song = try TabSong.create(title: title, jobID: jobID, musicXML: xml, tab: tab, recording: nil)
            refresh()
            path = [.tab(song)]
        } catch {
            if let which = refused(error) { show(.needsUpdate(which)) } else { show(.cantOpenTab(error.localizedDescription)) }
        }
    }

    func delete(_ entry: SongEntry) {
        switch entry.location {
        case .local(let s):
            s.delete()
            refresh()
        case .computer(let jobID):
            Task {
                guard let svc = service() as? CompanionService else { return }
                do { try await svc.deleteRun(jobID: jobID) } catch { if let which = refused(error) { show(.needsUpdate(which)) } }
                await refreshComputerSongs()
            }
        }
    }

    // MARK: sources

    func ask(_ src: PendingSource) {
        showRecorder = false
        showCapture = false
        path.append(.whatIsThis(src))
    }

    func show(_ p: FretscribeProblem) {
        showRecorder = false
        showCapture = false
        path.append(.problem(p))
    }

    func goHome() { path = [] }

    /// An opened or shared file: a recording or a video goes to "What is this?"; sheet music is refused with why.
    func accept(url: URL) async {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let ext = url.pathExtension.lowercased()
        if ["musicxml", "xml", "mxl", "gp", "gp5", "gpx"].contains(ext) { show(.sheetMusic); return }
        if let type = UTType(filenameExtension: ext), !type.conforms(to: .audiovisualContent) {
            show(.cantOpenFile(String(localized: "Fretscribe opens recordings and videos.")))
            return
        }
        do {
            let inbox = FileManager.default.temporaryDirectory.appending(path: "Inbox", directoryHint: .isDirectory)
            try FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
            let local = inbox.appending(path: UUID().uuidString + "." + url.pathExtension)
            try FileManager.default.copyItem(at: url, to: local)
            ask(PendingSource(audioURL: local, title: url.deletingPathExtension().lastPathComponent, name: url.lastPathComponent))
        } catch {
            show(.cantOpenFile(error.localizedDescription))
        }
    }

    // MARK: writing down the notes

    /// The options a tab is written with: the player's instrument and tuning, what they read, and what "What is this?"
    /// was answered with.
    nonisolated static func fields(instrument: YourInstrument, recording: RecordingKind) -> [EngineField] {
        let o = instrument.valid().jobOptions()
        return [EngineField("instrument", o.instrument), EngineField("tuning", o.tuning), EngineField("layout", o.layout),
                EngineField("recording", recording.rawValue)]
    }

    func startTranscription(_ src: PendingSource, recording: RecordingKind) {
        let request = TranscriptionRequest(audioURL: src.audioURL, profile: Self.profile, title: src.title,
                                           fields: Self.fields(instrument: instrument, recording: recording))
        let job = TabJob(source: src, recording: recording, request: request, service: service())
        job.onRefused = { [weak self] in self?.connection.poke() }
        jobs[job.id] = job
        if case .whatIsThis = path.last { path[path.count - 1] = .transcribing(job.id) } else { path.append(.transcribing(job.id)) }
        let svc = job.service
        job.start { [weak self] result in
            guard let self else { return }
            let tab = try? await svc.artifact(.tab, jobID: result.jobID)
            do {
                let song = try TabSong.create(title: src.title, jobID: self.useFixtureService ? nil : result.jobID,
                                              musicXML: result.musicXML, tab: tab, recording: src.audioURL)
                self.refresh()
                if let i = self.path.firstIndex(of: .transcribing(job.id)) { self.path[i] = .check(song) } else { self.path.append(.check(song)) }
                self.jobs[job.id] = nil
            } catch {
                job.failure = error.localizedDescription
            }
        }
    }

    func retry(_ job: TabJob) { startTranscription(job.source, recording: job.recording) }

    func backToSource(_ job: TabJob) {
        if let i = path.firstIndex(of: .transcribing(job.id)) { path[i] = .whatIsThis(job.source) } else { goHome() }
        jobs[job.id] = nil
    }

    /// Where the notes are written down, for "What is this?" and the transcribing screen.
    func whereItRuns() -> String {
        #if os(macOS)
        if let host = engineURL.host(), ["localhost", "127.0.0.1"].contains(host) {
            return String(localized: "Bandroom on this Mac writes down the notes. The recording is not sent online.")
        }
        #endif
        return String(localized: "Bandroom on your computer writes down the notes. The recording is not sent online.")
    }
}

/// A tab being written down on the computer, with plain-language progress.
@Observable @MainActor
final class TabJob: Identifiable {
    let id = UUID()
    let source: PendingSource
    let recording: RecordingKind
    let request: TranscriptionRequest
    let service: TranscriptionService
    var progress = TranscriptionProgress(stage: .uploading, fraction: 0, etaSeconds: nil)
    var failure: String?
    var needsUpdate: InterfaceMatch.Update?
    var cancelled = false
    private var task: Task<Void, Never>?
    var onRefused: (@MainActor () -> Void)?

    init(source: PendingSource, recording: RecordingKind, request: TranscriptionRequest, service: TranscriptionService) {
        self.source = source; self.recording = recording; self.request = request; self.service = service
    }

    func start(onDone: @escaping @MainActor (TranscriptionResult) async -> Void) {
        let service = self.service, req = request
        task = Task { [weak self] in
            do {
                for try await ev in service.transcribe(req) {
                    switch ev {
                    case .progress(let p): self?.progress = p
                    case .finished(let r): await onDone(r)
                    }
                }
            } catch {
                guard let self else { return }
                if case TranscriptionError.notPaired = error { self.onRefused?() }
                if case TranscriptionError.interfaceMismatch(let which) = error { self.needsUpdate = which; self.onRefused?() }
                if case TranscriptionError.cancelled = error { self.cancelled = true } else if !Task.isCancelled {
                    self.failure = error.localizedDescription
                }
            }
        }
    }

    func cancel() {
        task?.cancel()
        cancelled = true
    }
}

/// Song titles people can tell apart.
enum SongTitles {
    /// The given title, or "Recording, <date>" when it's empty or only a timestamp ("20260815_155324").
    static func display(_ title: String, made: Date) -> String {
        let t = title.trimmingCharacters(in: .whitespaces)
        guard t.isEmpty || t.range(of: #"^[0-9][0-9 _.:T-]{5,}$"#, options: .regularExpression) != nil else { return t }
        return RecordingTitles.recording(at: made)
    }
}

/// What a launch was asked for: by tests, screenshots and the screen catalogue.
enum LaunchOptions {
    static let args = ProcessInfo.processInfo.arguments
    /// Nothing from earlier runs: no pairing, the first run again unless `-skip-first-run`.
    static var reset: Bool { args.contains("-reset") }
    static var skipFirstRun: Bool { args.contains("-skip-first-run") }
    /// `-appearance light|dark`
    static var colorScheme: ColorScheme? {
        guard let i = args.firstIndex(of: "-appearance"), i + 1 < args.count else { return nil }
        return args[i + 1] == "dark" ? .dark : .light
    }
}
