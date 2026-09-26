import AVFoundation
import OnDeviceKit
import Foundation
import Observation
import ScoreKit
import SwiftUI
import TranscriptionKit
import UniformTypeIdentifiers

/// Something the user brought in, waiting for "What is this?".
struct PendingSource: Identifiable, Equatable {
    let id = UUID()
    var audioURL: URL
    var videoURL: URL?
    var title: String
}

enum Route: Hashable {
    case transcribe(UUID)
    case review(Piece)
    case score(Piece)
}

@Observable @MainActor
final class AppModel {
    var pieces: [Piece] = Piece.loadAll()
    var path: [Route] = []
    var pending: PendingSource?
    var jobs: [UUID: TranscriptionJob] = [:]
    var alert: AppAlert?
    var showSettings = false
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
                alert = .message(String(localized: "This is not a score Brasscribe can read."), error.localizedDescription)
            }
            return
        }
        if type?.conforms(to: .xml) == true || ["musicxml", "xml"].contains(url.pathExtension.lowercased()) {
            await openScoreFile(url, title: title)
            return
        }
        let asset = AVURLAsset(url: url)
        if (try? await asset.load(.hasProtectedContent)) == true {
            alert = .drm
            return
        }
        do {
            let local = try copyToInbox(url)
            let hasVideo = !((try? await asset.loadTracks(withMediaType: .video)) ?? []).isEmpty
            if hasVideo {
                let audio = try await MediaTools.extractAudio(from: local)
                pending = PendingSource(audioURL: audio, videoURL: local, title: title)
            } else {
                pending = PendingSource(audioURL: local, title: title)
            }
        } catch {
            alert = .message(String(localized: "Couldn't open this file."), error.localizedDescription)
        }
    }

    func acceptRecording(_ url: URL, title: String) {
        pending = PendingSource(audioURL: url, title: title)
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
            alert = .message(String(localized: "This is not a score Brasscribe can read."), error.localizedDescription)
        }
    }

    /// Start the demo: the golden Mikkel transcription served by the fixture service.
    func startDemo() {
        guard let original = originalForFixture ?? fixtureDirectory?.appending(path: "brass-band.mp3") else {
            alert = .message(String(localized: "The demo recording is not available."), "")
            return
        }
        UserDefaults.standard.set(true, forKey: "useDemoService")
        pending = PendingSource(audioURL: original, videoURL: videoForFixture, title: "Mikkel")
    }

    // MARK: transcription

    func startTranscription(_ src: PendingSource, profile: SourceProfile, output: OutputChoice) {
        let job = TranscriptionJob(source: src, profile: profile, output: output, service: service(for: profile))
        jobs[job.id] = job
        pending = nil
        path.append(.transcribe(job.id))
        job.start { [weak self] result in
            guard let self else { return }
            do {
                let p = try Piece.create(title: src.title, profile: profile, result: result, original: src.audioURL,
                                         video: src.videoURL, fixtureDirectory: self.useDemoService ? self.fixtureDirectory : nil)
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

    func delete(_ p: Piece) {
        p.delete()
        refresh()
    }
}

enum AppAlert: Identifiable, Equatable {
    case drm
    case silence
    case message(String, String)
    var id: String {
        switch self {
        case .drm: return "drm"
        case .silence: return "silence"
        case .message(let a, _): return a
        }
    }
    var title: String {
        switch self {
        case .drm: return String(localized: "This recording is copy-protected")
        case .silence: return String(localized: "Only silence was recorded")
        case .message(let t, _): return t
        }
    }
    var message: String {
        switch self {
        case .drm:
            return String(localized: "Protected (DRM) music and video can't be recorded or imported. Play the piece yourself, or use a file you own without copy protection.")
        case .silence:
            return String(localized: "Nothing was heard. Either nothing was playing, recording permission was refused, or the app plays protected (DRM) audio, which the system does not let anyone record.")
        case .message(_, let m): return m
        }
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
