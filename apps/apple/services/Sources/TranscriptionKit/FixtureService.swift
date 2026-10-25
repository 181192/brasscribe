import Foundation
import ScoreKit

/// Serves a finished transcription from a directory laid out like the engine's output
/// (`composition.json`, the target's `.musicxml`, `.pdf`, `.mp3`, …), walking through the same
/// progress steps. Used by tests, UI tests, screenshots and offline demos.
public struct FixtureService: TranscriptionService {
    public let directory: URL
    /// Seconds per simulated step (0 for tests).
    public var stepDelay: Double

    public var displayName: String { "Demo" }

    /// The output's own name (`tab`, for `tab.musicxml` among the other layouts beside it); nil takes the first file of
    /// each kind.
    public var outputName: String?

    public init(directory: URL, stepDelay: Double = 0.4, outputName: String? = nil) {
        self.directory = directory; self.stepDelay = stepDelay; self.outputName = outputName
    }

    public var available: Set<ArtifactKind> { Set(ArtifactKind.allCases.filter { file(of: $0) != nil }) }

    /// The file of [kind] in the directory: the one of the output's own name, else the first by name.
    public func file(of kind: ArtifactKind) -> URL? {
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []).filter { kind.isOutput($0) }.sorted()
        let own = outputName.map { "\($0).\(kind.fileExtension)" }
        return (names.first { $0 == own } ?? names.first).map { directory.appending(path: $0) }
    }

    public func transcribe(_ request: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error> {
        let steps: [StageKind] = [.uploading, .preparing, .separating, .findingBeat, .transcribing, .arranging, .engraving]
        let delay = stepDelay, avail = available, xmlFile = file(of: .musicXML), compFile = file(of: .composition)
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
                    guard let xmlFile else { throw TranscriptionError.artifactUnavailable(.musicXML) }
                    let xml = try Data(contentsOf: xmlFile)
                    let comp = compFile.flatMap { try? Composition.decode(Data(contentsOf: $0)) }
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
        guard let u = file(of: kind) else { throw TranscriptionError.artifactUnavailable(kind) }
        return try Data(contentsOf: u)
    }
}
