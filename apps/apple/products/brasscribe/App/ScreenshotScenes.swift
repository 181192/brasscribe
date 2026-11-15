import Foundation
import ImageIO
import ScoreKit
import UniformTypeIdentifiers
import TranscriptionKit

/// Opens one key screen directly (`-screen <name>`), for the screenshots in docs/screenshots
/// and the side-by-side check against design/brands/brasscribe/mockups.
enum ScreenshotScenes {
    @MainActor static func open(_ name: String, app: AppModel, openScore: () -> Piece?) {
        switch name {
        case "home-full":
            // a lived-in library: named scores, an imported file, a timestamp-named file and a microphone take
            guard let first = openScore() else { return }
            let day: TimeInterval = 86_400
            let library: [(String, TimeInterval, Lineup, Int?)] = [
                ("Deep Harmony", 1 * day, .fullBand, 0), ("Abide with Me", 2 * day, .minimalBand, 12), ("Crimond", 3 * day, .quartet, 0),
                ("20260815_155324", 5 * day, .fullBand, nil), ("", 8 * day, .minimalBand, 4), ("Floral Dance", 12 * day, .fullBand, 0),
            ]
            for (title, ago, lineup, toCheck) in library {
                guard var p = try? Piece.create(title: title.isEmpty ? ScoreTitles.recording(at: Date().addingTimeInterval(-ago)) : title,
                                                profile: .brassBand, result: TranscriptionResult(jobID: "fixture", composition: first.loadComposition(),
                                                musicXML: (try? Data(contentsOf: first.scoreURL)) ?? Data(), available: [.musicXML]),
                                                original: nil, video: nil, fixtureDirectory: nil, output: OutputChoice(lineup: lineup)) else { continue }
                p.created = Date().addingTimeInterval(-ago)
                if let toCheck { p.toCheck = toCheck }
                try? p.save()
            }
            var fixture = first
            fixture.output = OutputChoice()
            try? fixture.save()
            app.refresh()
            app.path = []
        case "source-draft":
            // Brass band with no computer: the draft line (the scene's device counts as having the listening files)
            app.assumeModelsReady = true
            app.ask(PendingSource(audioURL: app.originalForFixture ?? sceneRecording, title: "Band practice", name: "Band practice.m4a"))
        case "score-draft":
            guard var p = openScore() else { return }
            p.draft = true
            try? p.save()
            app.refresh()
            app.path = [.score(p)]
        case "source":
            // a file name only: the scenes never read the recording
            app.ask(PendingSource(audioURL: app.originalForFixture ?? sceneRecording, title: "Band practice", name: "Band practice.m4a"))
        case "transcribing", "transcribing-cancel":
            let src = PendingSource(audioURL: app.originalForFixture ?? sceneRecording, title: fixtureTitle(app), name: nil)
            let job = TranscriptionJob(source: src, profile: .orchestraWithSoloist, output: OutputChoice(), service: FrozenService())
            app.jobs[job.id] = job
            job.start { _ in }
            app.path = [.transcribe(job.id)]
        case "review", "review-listening", "finish-later":
            if let p = openScore() { app.path = [.review(p)] }
        case "output":
            if let p = openScore() { app.path = [.output(p)] }
        case "score", "part", "export", "stand", "stand-hidden", "stand-hint", "stand-locked", "stand-all":
            _ = openScore()   // ScoreScreen reads the scene name for the part view and the export sheet
        case "part-small":
            // the small band: a seat without its own part there gets the notice
            guard let p = openScore(), let comp = p.loadComposition() else { return }
            _ = try? app.rearrange(p, composition: comp, output: OutputChoice(lineup: .minimalBand))
        case "pages", "pages-unread":
            // three pages of printed music in hand; then a read that found no notes on them
            app.pageList.clear()
            app.path = [.pages]
            Task {
                for _ in 1...3 { if let page = scenePage() { await app.pageList.add(photo: page) } }
                guard name == "pages-unread" else { return }
                let job = PagesJob(request: TranscriptionRequest(pages: app.pageList.pages.map(\.url), profile: AppModel.sheetProfile),
                                   service: FrozenService())
                job.error = TranscriptionError.jobFailed("read: StageFailed: read: no notes were found on the page")
                app.pageJobs[job.id] = job
                app.path.append(.readingPages(job.id))
            }
        case "error":
            app.show(.silence)
        case "settings":
            app.showSettings = true
        default:
            break
        }
    }
}

extension ScreenshotScenes {
    /// Where a scene's recording would be; nothing is there.
    static var sceneRecording: URL { FileManager.default.temporaryDirectory.appending(path: "Band practice.m4a") }

    /// A page of printed music for the scenes: a white sheet with six staves, as a JPEG.
    static func scenePage() -> Data? {
        guard let ctx = CGContext(data: nil, width: 600, height: 800, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
        ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: 600, height: 800))
        ctx.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1))
        for staff in 0..<6 { for line in 0..<5 { ctx.fill(CGRect(x: 40, y: 700 - staff * 110 - line * 12, width: 520, height: 2)) } }
        guard let image = ctx.makeImage() else { return nil }
        let data = NSMutableData()
        guard let out = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(out, image, nil)
        return CGImageDestinationFinalize(out) ? data as Data : nil
    }

    /// The fixture score's title ("Old Hundredth").
    @MainActor static func fixtureTitle(_ app: AppModel) -> String {
        guard let dir = app.fixtureDirectory, let data = try? Data(contentsOf: dir.appending(path: "composition.json")),
              let comp = try? Composition.decode(data) else { return "Old Hundredth" }
        return comp.title
    }

    /// The score screens show the states reviewers asked to see: a chip turned on, a
    /// repeat on, and the ad lib tint with the cursor elsewhere.
    /// The stand's states: the controls shown, hidden, or with the rotation locked.
    @MainActor static func stageStand(_ m: PracticeModel) {
        guard let stand = m.stand else { return }
        switch LaunchOptions.screen {
        case "stand-hidden": stand.layerShown = false
        case "stand-hint": stand.layerShown = false; stand.showHint = true
        case "stand-all": m.setOnlyMine(false)
        case "stand-locked": stand.rotationLocked = true
        default: break
        }
    }

    @MainActor static func stage(_ m: PracticeModel) {
        switch LaunchOptions.screen {
        case "score":
            m.countIn = true
            m.loopFrom = 8; m.loopTo = 9
            m.setLoop(true)
            m.goToBar(9)
        case "part":
            m.goToBar(8)
        case "stand", "stand-hidden", "stand-hint", "stand-locked", "stand-all":
            m.goToBar(4)
        default:
            break
        }
    }
}

/// A transcription that stays at "Writing down the notes", 62 %.
struct FrozenService: TranscriptionService {
    var displayName: String { "Brasscribe" }
    func transcribe(_ request: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error> {
        AsyncThrowingStream { c in c.yield(.progress(TranscriptionProgress(stage: .transcribing, fraction: 0.62, etaSeconds: 130))) }
    }
    func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data { throw TranscriptionError.artifactUnavailable(kind) }
}
