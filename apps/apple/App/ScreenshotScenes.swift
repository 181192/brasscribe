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
                ("Deep Harmony", 1 * day, .fullBand, 0), ("Abide with Me", 2 * day, .minimalBand, 12),
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
            var mikkel = first
            mikkel.output = OutputChoice()
            try? mikkel.save()
            app.refresh()
            app.path = []
        case "source":
            app.startDemo()
        case "transcribing", "transcribing-cancel":
            guard let original = app.originalForFixture ?? app.fixtureDirectory?.appending(path: "brass-band.mp3") else { return }
            let src = PendingSource(audioURL: original, title: "Mikkel", name: original.lastPathComponent)
            let job = TranscriptionJob(source: src, profile: .orchestraWithSoloist, output: OutputChoice(), service: FrozenService())
            app.jobs[job.id] = job
            job.start { _ in }
            app.path = [.transcribe(job.id)]
        case "review", "finish-later":
            if let p = openScore() { app.path = [.review(p)] }
        case "output":
            if let p = openScore() { app.path = [.output(p)] }
        case "score", "part", "export":
            _ = openScore()   // ScoreScreen reads the scene name for the part view and the export sheet
        case "error":
            app.show(.silence)
        default:
            break
        }
    }
}

extension ScreenshotScenes {
    /// The score screens show the states reviewers asked to see: a chip turned on, a
    /// repeat on, and the ad lib tint with the cursor elsewhere.
    @MainActor static func stage(_ m: PracticeModel) {
        switch LaunchOptions.screen {
        case "score":
            m.countIn = true
            m.loopFrom = 11; m.loopTo = 12
            m.setLoop(true)
            m.goToBar(12)
        case "part":
            m.goToBar(8)
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
