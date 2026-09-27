import AVFoundation
import OnDeviceKit
import Foundation
import Observation
import ScoreKit
import SwiftUI
import TranscriptionKit
import UniformTypeIdentifiers

/// Something the user brought in, waiting for "What is this?".
struct PendingSource: Identifiable, Hashable {
    var id = UUID()
    var audioURL: URL
    var videoURL: URL?
    var title: String
    /// The file name shown above "What is this?" ("Mikkel.m4a"); nil for a new recording.
    var name: String?
}

enum Route: Hashable {
    case source(PendingSource)
    case transcribe(UUID)
    case review(Piece)
    case output(Piece)
    case score(Piece)
    case problem(Problem)
}

@Observable @MainActor
final class AppModel {
    var pieces: [Piece] = Piece.loadAll() { didSet { rebuildScores() } }
    /// "Your scores": this device's pieces and the computer's latest finished scores.
    private(set) var scores: [ScoreEntry] = ScoreEntry.merge(pieces: Piece.loadAll(), jobs: [])
    private var computerJobs: [CompanionService.Job] = [] { didSet { rebuildScores() } }
    var openingScore: String?
    var renameTarget: ScoreEntry?
    var deleteTarget: ScoreEntry?
    var path: [Route] = []
    var jobs: [UUID: TranscriptionJob] = [:]
    var showSettings = false
    var showFirstRun = false
    var showRecorder = false
    var showCapture = false
    var importing = false

    // Companion settings
    var companionURL: String = ProcessInfo.processInfo.environment["BRASSCRIBE_COMPANION"] ?? UserDefaults.standard.string(forKey: "companionURL") ?? "http://localhost:8765" {
        didSet { UserDefaults.standard.set(companionURL, forKey: "companionURL") }
    }
    var companionToken: String? = UserDefaults.standard.string(forKey: "companionToken") {
        didSet { UserDefaults.standard.set(companionToken, forKey: "companionToken") }
    }

    /// Engine output folder used by the demo service (tests and screenshots set it).
    let fixtureDirectory: URL? = {
        let env = ProcessInfo.processInfo.environment
        if let d = env["BRASSCRIBE_FIXTURES"], FileManager.default.fileExists(atPath: d) { return URL(fileURLWithPath: d) }
        return Bundle.main.url(forResource: "Demo", withExtension: nil)
    }()

    var originalForFixture: URL? {
        let env = ProcessInfo.processInfo.environment
        if let o = env["BRASSCRIBE_ORIGINAL"], FileManager.default.fileExists(atPath: o) { return URL(fileURLWithPath: o) }
        guard let dir = fixtureDirectory else { return nil }
        let guess = dir.deletingLastPathComponent().deletingLastPathComponent().appending(path: "mikkel/mikkel.wav")
        return FileManager.default.fileExists(atPath: guess.path) ? guess : nil
    }

    var videoForFixture: URL? {
        guard let v = ProcessInfo.processInfo.environment["BRASSCRIBE_VIDEO"], FileManager.default.fileExists(atPath: v) else { return nil }
        return URL(fileURLWithPath: v)
    }

    var useDemoService: Bool {
        ProcessInfo.processInfo.arguments.contains("-demo-service") || UserDefaults.standard.bool(forKey: "useDemoService")
    }

    func service() -> TranscriptionService {
        if useDemoService, let dir = fixtureDirectory {
            return FixtureService(directory: dir, stepDelay: ProcessInfo.processInfo.arguments.contains("-fast") ? 0.05 : 0.6)
        }
        return CompanionService(baseURL: URL(string: companionURL) ?? URL(string: "http://localhost:8765")!, token: companionToken)
    }

    /// Solos are transcribed on this device when the models are there (or can be fetched);
    /// everything else goes to the paired computer.
    var soloOnDevice: Bool = UserDefaults.standard.object(forKey: "soloOnDevice") as? Bool ?? true {
        didSet { UserDefaults.standard.set(soloOnDevice, forKey: "soloOnDevice") }
    }
    var modelDownloadURL: String = UserDefaults.standard.string(forKey: "modelDownloadURL") ?? "" {
        didSet { UserDefaults.standard.set(modelDownloadURL, forKey: "modelDownloadURL"); ModelStore.shared.remoteBase = URL(string: modelDownloadURL) }
    }

    func service(for profile: SourceProfile) -> TranscriptionService {
        if profile == .solo && soloOnDevice && !useDemoService {
            ModelStore.shared.remoteBase = URL(string: modelDownloadURL)
            if ModelStore.shared.missing.isEmpty || ModelStore.shared.remoteBase != nil { return OnDeviceSoloService() }
        }
        return service()
    }

    func refresh() { pieces = Piece.loadAll() }

    private func rebuildScores() { scores = ScoreEntry.merge(pieces: pieces, jobs: computerJobs) }

    /// Fetch the computer's finished scores; silently keeps the local list when it is not reachable.
    func refreshComputerScores() async {
        guard !useDemoService, let svc = service() as? CompanionService else { computerJobs = []; return }
        if let jobs = try? await svc.jobs() { computerJobs = jobs }
    }

    func open(_ entry: ScoreEntry, review: Bool = false) {
        switch entry.location {
        case .local(let p): path = [review ? .review(p) : .score(p)]
        case .computer(let jobID): Task { await download(jobID: jobID, title: entry.title, profile: entry.profile, review: review) }
        }
    }

    /// Copy a computer score into this device's library, then open it.
    private func download(jobID: String, title: String, profile: SourceProfile?, review: Bool) async {
        guard let svc = service() as? CompanionService else { return }
        openingScore = "job:\(jobID)"
        defer { openingScore = nil }
        do {
            let xml = try await svc.artifact(.musicXML, jobID: jobID)
            let comp = try? Composition.decode(try await svc.artifact(.composition, jobID: jobID))
            let evidence = try? await svc.evidence(jobID: jobID)
            let names = Set(computerJobs.first { $0.id == jobID }?.outputs ?? [])
            let result = TranscriptionResult(jobID: jobID, composition: comp, musicXML: xml,
                                             available: Set(ArtifactKind.allCases.filter { names.contains($0.engineName) }), evidence: evidence)
            let p = try Piece.create(title: title, profile: profile, result: result, original: nil, video: nil, fixtureDirectory: nil)
            refresh()
            path = [review ? .review(p) : .score(p)]
        } catch {
            show(.cantOpenFile(error.localizedDescription))
        }
    }

    func rename(_ entry: ScoreEntry, to title: String) {
        let cleaned = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        switch entry.location {
        case .local(let p): rename(p, to: cleaned)
        case .computer(let jobID):
            Task {
                guard let svc = service() as? CompanionService else { return }
                do { try await svc.rename(jobID: jobID, title: cleaned); await refreshComputerScores() }
                catch { show(.cantOpenFile(error.localizedDescription)) }
            }
        }
    }

    func delete(_ entry: ScoreEntry) {
        switch entry.location {
        case .local(let p): delete(p)
        case .computer(let jobID):
            Task {
                guard let svc = service() as? CompanionService else { return }
                try? await svc.deleteRun(jobID: jobID)
                await refreshComputerScores()
            }
        }
    }

    func rename(_ piece: Piece, to title: String) {
        let cleaned = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, let index = pieces.firstIndex(where: { $0.id == piece.id }) else { return }
        var updated = pieces[index]
        updated.title = cleaned
        do {
            try updated.saveMusicXML(MusicXMLNoteEditor.replacingTitle(in: updated.musicXML(), with: cleaned))
            try updated.save()
            pieces[index] = updated
            if let jobID = updated.remoteJobID, let svc = service() as? CompanionService, !useDemoService {
                Task { try? await svc.rename(jobID: jobID, title: cleaned); await refreshComputerScores() }
            }
        } catch {
            show(.notAScore(error.localizedDescription))
        }
    }

    /// Open "What is this?" for a new recording, closing any recorder sheet first.
    func ask(_ src: PendingSource) {
        showRecorder = false
        showCapture = false
        path.append(.source(src))
    }

    /// Show a problem with its way forward. The user's scores are never touched.
    func show(_ p: Problem) {
        showRecorder = false
        showCapture = false
        path.append(.problem(p))
    }

    func open(_ piece: Piece) { path = [.score(piece)] }
    func goHome() { path = [] }

    /// Where the listening happens, for "What is this?" and the transcribing screen.
    func whereItRuns(for profile: SourceProfile?) -> String {
        if let profile, service(for: profile) is OnDeviceSoloService { return String(localized: "On this device. Nothing goes online.") }
        if useDemoService { return String(localized: "The demo runs on this device. Nothing goes online.") }
        #if os(macOS)
        if let host = URL(string: companionURL)?.host, ["localhost", "127.0.0.1"].contains(host) {
            return String(localized: "Made on this Mac. Nothing goes online.")
        }
        #endif
        return String(localized: "On your computer. Nothing goes online.")
    }

    // MARK: sources

    /// Accept an imported or shared file. Video keeps its picture for the synced view;
    /// DRM-protected media is refused with an explanation instead of recording silence.
    func accept(url: URL) async {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let title = url.deletingPathExtension().lastPathComponent
        let type = UTType(filenameExtension: url.pathExtension)
        if url.pathExtension.lowercased() == "json" {
            do {
                let comp = try core.composition(fromJSON: try Data(contentsOf: url))
                try arrangeOnDevice(comp, title: title, lineup: .fullBand, original: nil, video: nil)
            } catch {
                show(.notAScore(error.localizedDescription))
            }
            return
        }
        if type?.conforms(to: .xml) == true || ["musicxml", "xml"].contains(url.pathExtension.lowercased()) {
            await openScoreFile(url, title: title)
            return
        }
        let asset = AVURLAsset(url: url)
        if (try? await asset.load(.hasProtectedContent)) == true {
            show(.copyProtected)
            return
        }
        do {
            let local = try copyToInbox(url)
            let hasVideo = !((try? await asset.loadTracks(withMediaType: .video)) ?? []).isEmpty
            if hasVideo {
                let audio = try await MediaTools.extractAudio(from: local)
                ask(PendingSource(audioURL: audio, videoURL: local, title: title, name: url.lastPathComponent))
            } else {
                ask(PendingSource(audioURL: local, title: title, name: url.lastPathComponent))
            }
        } catch {
            show(.cantOpenFile(error.localizedDescription))
        }
    }

    func acceptRecording(_ url: URL, title: String) {
        ask(PendingSource(audioURL: url, title: title))
    }

    private func copyToInbox(_ url: URL) throws -> URL {
        let inbox = FileManager.default.temporaryDirectory.appending(path: "Inbox", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
        let dst = inbox.appending(path: UUID().uuidString + "." + url.pathExtension)
        try FileManager.default.copyItem(at: url, to: dst)
        return dst
    }

    private func openScoreFile(_ url: URL, title: String) async {
        do {
            let xml = try Data(contentsOf: url)
            _ = try MusicXMLParser.parse(xml)
            let result = TranscriptionResult(jobID: "import", composition: nil, musicXML: xml, available: [.musicXML])
            let p = try Piece.create(title: title, profile: nil, result: result, original: nil, video: nil, fixtureDirectory: nil)
            refresh()
            path.append(.score(p))
        } catch {
            show(.notAScore(error.localizedDescription))
        }
    }

    /// Start the demo: the golden Mikkel transcription served by the fixture service.
    func startDemo() {
        guard let original = originalForFixture ?? fixtureDirectory?.appending(path: "brass-band.mp3") else {
            show(.demoMissing)
            return
        }
        UserDefaults.standard.set(true, forKey: "useDemoService")
        ask(PendingSource(audioURL: original, videoURL: videoForFixture, title: "Mikkel", name: original.lastPathComponent))
    }

    // MARK: transcription

    func startTranscription(_ src: PendingSource, profile: SourceProfile, output: OutputChoice) {
        let job = TranscriptionJob(source: src, profile: profile, output: output, service: service(for: profile))
        jobs[job.id] = job
        // the transcribing screen takes the place of "What is this?"
        if case .source = path.last { path[path.count - 1] = .transcribe(job.id) } else { path.append(.transcribe(job.id)) }
        job.start { [weak self] result in
            guard let self else { return }
            do {
                let p = try Piece.create(title: src.title, profile: profile, result: result, original: src.audioURL,
                                         video: src.videoURL, fixtureDirectory: self.useDemoService ? self.fixtureDirectory : nil,
                                         output: output)
                self.refresh()
                if let i = self.path.firstIndex(of: .transcribe(job.id)) { self.path[i] = .review(p) } else { self.path.append(.review(p)) }
                self.jobs[job.id] = nil
            } catch {
                job.failure = error.localizedDescription
            }
        }
    }

    let core: CoreBridge = RustCoreBridge()

    /// Arrange a Composition with the shared core on this device (no computer needed) and open it.
    func arrangeOnDevice(_ comp: Composition, title: String, lineup: Lineup, original: URL?, video: URL?) throws {
        guard let xml = try core.arrange(comp, lineup: lineup, difficulty: .faithful, keyFifths: nil) else { return }
        let result = TranscriptionResult(jobID: "on-device", composition: comp, musicXML: xml, available: [.musicXML, .composition])
        let p = try Piece.create(title: title, profile: nil, result: result, original: original, video: video, fixtureDirectory: nil)
        refresh()
        path.append(.score(p))
    }

    /// Arrange a piece again on this device for another band, difficulty or key, and open it.
    /// The engine's PDF and braille no longer match, so those are made on this device too.
    func rearrange(_ piece: Piece, composition comp: Composition, output: OutputChoice, open andOpen: Bool = true) throws {
        guard let xml = try core.arrange(comp, lineup: output.lineup, difficulty: output.difficulty, keyFifths: output.keyFifths) else {
            throw TranscriptionError.artifactUnavailable(.musicXML)
        }
        try xml.write(to: piece.scoreURL)
        var p = piece
        p.output = output
        p.fixtureDirectory = nil
        p.remoteArtifacts = [.musicXML, .composition]
        if let score = try? MusicXMLParser.parse(xml) {
            p.bars = score.measures.count
            p.toCheck = ReviewList.items(score: score, uncertainty: UncertaintyIndex(composition: comp)).count
        }
        try p.save()
        refresh()
        if andOpen { open(p) }
    }

    func delete(_ p: Piece) {
        p.delete()
        refresh()
    }
}

/// A running transcription with plain-language progress.
@Observable @MainActor
final class TranscriptionJob: Identifiable {
    let id = UUID()
    let source: PendingSource
    let profile: SourceProfile
    let output: OutputChoice
    let service: TranscriptionService
    var progress = TranscriptionProgress(stage: .uploading, fraction: 0, etaSeconds: nil)
    var failure: String?
    var cancelled = false
    private var task: Task<Void, Never>?

    init(source: PendingSource, profile: SourceProfile, output: OutputChoice, service: TranscriptionService) {
        self.source = source; self.profile = profile; self.output = output; self.service = service
    }

    func start(onDone: @escaping @MainActor (TranscriptionResult) -> Void) {
        let req = TranscriptionRequest(audioURL: source.audioURL, profile: profile, title: source.title, output: output)
        let service = self.service
        task = Task { [weak self] in
            do {
                for try await ev in service.transcribe(req) {
                    switch ev {
                    case .progress(let p): self?.progress = p
                    case .finished(let r): onDone(r)
                    }
                }
            } catch {
                guard let self else { return }
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
