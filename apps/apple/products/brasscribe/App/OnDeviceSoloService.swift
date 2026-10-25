import ScribeCore
import Foundation
import OnDeviceKit
import ScoreKit
import TranscriptionKit

/// Transcribes a solo recording entirely on this device: SwiftF0, Basic Pitch and
/// Beat This! run with Core ML (OnDeviceKit), and the shared Rust core notates the solo
/// line (SwiftF0 spine confirmed by Basic Pitch) and arranges it for brass band.
/// MuScriptor has no on-device conversion yet, so Basic Pitch fills its confirmation slot.
struct OnDeviceSoloService: TranscriptionService {
    let store: ModelStore
    var displayName: String { String(localized: "this device") }

    init(store: ModelStore = .shared) { self.store = store }

    func transcribe(_ request: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error> {
        let store = self.store
        return AsyncThrowingStream { continuation in
            let task = Task.detached(priority: .userInitiated) {
                do {
                    let t0 = Date()
                    @Sendable func report(_ stage: StageKind, _ f: Double) {
                        continuation.yield(.progress(.init(stage: stage, fraction: f, etaSeconds: nil, device: "on device")))
                    }
                    report(.preparing, 0)
                    let solo = try await SoloTranscriber(store: store).transcribe(request.audioURL) { step, f in
                        switch step {
                        case .preparing: report(.preparing, 0.05)
                        case .pitch: report(.transcribing, 0.1 + 0.3 * f)
                        case .confirm: report(.transcribing, 0.4 + 0.2 * f)
                        case .beats: report(.findingBeat, 0.6 + 0.2 * f)
                        }
                    }
                    try Task.checkCancellation()
                    report(.arranging, 0.85)
                    let out = try Self.arrange(solo, title: request.title ?? "Solo", output: request.output)
                    let comp = try? Composition.decode(Data(out.compositionJson.utf8))
                    let evidence = comp.map { NoteEvidence.build(composition: $0, models: [
                        .init(model: "swift-f0", name: "SwiftF0", notes: solo.swiftF0.map { .init(onset: $0.onset, offset: $0.offset, pitch: $0.pitch) }),
                        .init(model: "basic-pitch", name: "Basic Pitch", notes: solo.basicPitch.map { .init(onset: $0.onset, offset: $0.offset, pitch: $0.pitch) }),
                    ]) }
                    report(.engraving, 1)
                    print("ON-DEVICE solo \(Int(Date().timeIntervalSince(t0) * 1000)) ms, steps \(solo.seconds.mapValues { Int($0 * 1000) })")
                    continuation.yield(.finished(.init(jobID: "on-device", composition: comp, musicXML: Data(out.musicxml.utf8),
                                                       available: [.musicXML, .composition], evidence: evidence)))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error is CancellationError ? TranscriptionError.cancelled : error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// The core's solo-with-band path with only the solo layer present.
    static func arrange(_ solo: SoloTranscription, title: String, output: OutputChoice) throws -> BandOutput {
        let empty = SoloTranscription.emptyMIDI
        let layers = LayerMidi(soloSwiftf0: solo.swiftF0MIDI, soloMuscriptor: solo.basicPitchMIDI, soloBasicPitch: solo.basicPitchMIDI,
                               bass: empty, orchestra: empty, drums: empty)
        var o = layersSongDefaults()
        o.soloContour = SoloContour(times: solo.contour.times, pitchHz: solo.contour.pitchHz, loudnessDb: solo.contour.loudnessDB,
                                    confidence: solo.contour.confidence)
        switch output.lineup {
        case .fullBand, .minimalBand: o.lineup = output.lineup.coreValue
        // the Output screen never offers the quartet for a solo take
        case .quartet: throw TranscriptionError.needsWholeGroup
        }
        o.difficulty = output.difficulty.rawValue
        o.key = output.keyFifths.map { String($0) }
        // with a seat the take is written for the player's own instrument, in the octave played
        o.seat = output.seat
        o.reads = output.reads
        o.lead = output.seat == nil ? nil : "seat"
        return try arrangeLayersBand(layers: layers, stems: LayerStems(solo: nil, bass: nil, drums: nil, orchestra: nil),
                                     beatsText: solo.beats.tsv, title: title, options: o)
    }

    func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data {
        throw TranscriptionError.artifactUnavailable(kind)
    }
}
