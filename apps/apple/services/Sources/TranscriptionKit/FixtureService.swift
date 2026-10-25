import Foundation
import ScoreKit

/// Serves a finished transcription from a directory laid out like the engine's output
/// (`composition.json`, `brass-band.musicxml`, `.pdf`, `.mp3`, …), walking through the same
/// progress steps. Used by tests, UI tests, screenshots and offline demos.
public struct FixtureService: TranscriptionService {
    public let directory: URL
    /// Seconds per simulated step (0 for tests).
    public var stepDelay: Double

    public var displayName: String { "Demo" }

    public init(directory: URL, stepDelay: Double = 0.4) {
        self.directory = directory; self.stepDelay = stepDelay
    }

    public var available: Set<ArtifactKind> {
        Set(ArtifactKind.allCases.filter { FileManager.default.fileExists(atPath: directory.appending(path: $0.engineName).path) })
    }

    public func transcribe(_ request: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error> {
        let steps: [StageKind] = [.uploading, .preparing, .separating, .findingBeat, .transcribing, .arranging, .engraving]
        let dir = directory, delay = stepDelay, avail = available
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for (i, s) in steps.enumerated() {
                        let f = Double(i) / Double(steps.count)
                        continuation.yield(.progress(.init(stage: s, stageName: s.rawValue, fraction: f,
                                                           etaSeconds: delay * Double(steps.count - i), device: "fixture")))
                        if delay > 0 { try await Task.sleep(for: .seconds(delay)) }
                        try Task.checkCancellation()
                    }
                    let xml = try Data(contentsOf: dir.appending(path: ArtifactKind.musicXML.engineName))
                    let comp = try? Composition.decode(Data(contentsOf: dir.appending(path: ArtifactKind.composition.engineName)))
                    continuation.yield(.progress(.init(stage: .engraving, fraction: 1, etaSeconds: 0)))
                    continuation.yield(.finished(.init(jobID: "fixture", composition: comp, musicXML: xml, available: avail)))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error is CancellationError ? TranscriptionError.cancelled : error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data {
        let u = directory.appending(path: kind.engineName)
        guard FileManager.default.fileExists(atPath: u.path) else { throw TranscriptionError.artifactUnavailable(kind) }
        return try Data(contentsOf: u)
    }
}
