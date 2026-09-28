import Foundation
import ScoreKit
import TranscriptionKit

/// Opens one key screen directly (`-screen <name>`), for the screenshots in docs/screenshots
/// and the side-by-side check against design/mockups.
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
