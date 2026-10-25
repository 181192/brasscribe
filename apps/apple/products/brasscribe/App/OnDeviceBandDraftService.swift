import AVFoundation
import ScribeCore
import Foundation
import OnDeviceKit
import ScoreKit
import TranscriptionKit

/// A recording longer than this device's free memory can hold for a band draft.
struct DraftTooLong: Error, CustomStringConvertible {
    var seconds: Double
    var maxSeconds: Double
    var description: String { "recording \(Int(seconds)) s, room for \(Int(maxSeconds)) s" }
}

/// Makes a quick draft of a whole band's recording on this device, without the computer: Basic
/// Pitch on the mix and Beat This! small0 with Core ML (OnDeviceKit), then the shared Rust core's
/// song arranger, as the engine's brass-band profile does with muscriptor=false. MuScriptor has no
/// on-device conversion yet, so Basic Pitch fills the melody, bass and harmony slots. The band,
/// seat and tune go to the arranger; difficulty and key are applied afterwards by arranging the
/// Composition again, as they are for any score.
struct OnDeviceBandDraftService: TranscriptionService {
    let store: ModelStore
    /// Free memory in bytes, read when a draft starts (tests pass their own).
    var available: @Sendable () -> Int = { OnDeviceBudget.available }
    var displayName: String { String(localized: "this device") }

    init(store: ModelStore = .shared, available: @escaping @Sendable () -> Int = { OnDeviceBudget.available }) {
        self.store = store
        self.available = available
    }

    func transcribe(_ request: TranscriptionRequest) -> AsyncThrowingStream<TranscriptionEvent, Error> {
        let store = self.store, available = self.available
        return AsyncThrowingStream { continuation in
            let task = Task.detached(priority: .userInitiated) {
                do {
                    let t0 = Date()
                    @Sendable func report(_ stage: StageKind, _ f: Double) {
                        continuation.yield(.progress(.init(stage: stage, fraction: f, etaSeconds: nil, device: "on device")))
                    }
                    report(.preparing, 0)
                    let seconds = Self.duration(of: request.audioURL)
                    let room = OnDeviceBudget.maxSeconds(available: available())
                    if let seconds, seconds > room { throw DraftTooLong(seconds: seconds, maxSeconds: room) }
                    let band = try await BandTranscriber(store: store).transcribe(request.audioURL) { step, f in
                        switch step {
                        case .preparing: report(.preparing, 0.05)
                        case .notes: report(.transcribing, 0.1 + 0.5 * f)
                        case .beats: report(.findingBeat, 0.6 + 0.2 * f)
                        }
                    }
                    try Task.checkCancellation()
                    report(.arranging, 0.85)
                    let out = try Self.arrange(band, title: request.title ?? "Band", output: request.output)
                    let comp = try? Composition.decode(Data(out.compositionJson.utf8))
                    let evidence = comp.map { NoteEvidence.build(composition: $0, models: [
                        .init(model: "basic-pitch", name: "Basic Pitch", notes: band.basicPitch.map { .init(onset: $0.onset, offset: $0.offset, pitch: $0.pitch) }),
                    ]) }
                    report(.engraving, 1)
                    print("ON-DEVICE band draft \(Int(Date().timeIntervalSince(t0) * 1000)) ms, steps \(band.seconds.mapValues { Int($0 * 1000) })")
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

    /// The core's song arranger with Basic Pitch in every slot and no melody support (the notes are the
    /// same with it; only one model votes).
    static func arrange(_ band: BandTranscription, title: String, output: OutputChoice) throws -> SongOutput {
        let bp = band.basicPitchMIDI
        return try arrangeSongWith(melody: bp, melodySupport: nil, bass: bp, harmony: [bp], beatsText: band.beats.tsv,
                                   title: title, options: options(output))
    }

    /// The engine's made_lineup for a band take: the full band is made as the small band; seat, clef and
    /// who plays the tune as chosen.
    static func options(_ output: OutputChoice) -> SongArrangeOptions {
        SongArrangeOptions(lineup: output.lineup == .quartet ? "quartet" : "minimal", seat: output.seat,
                           reads: output.seat == nil ? nil : output.reads, lead: output.seat == nil ? nil : output.lead)
    }

    /// The recording's length from its header, without decoding it.
    static func duration(of url: URL) -> Double? {
        guard let f = try? AVAudioFile(forReading: url), f.fileFormat.sampleRate > 0 else { return nil }
        return Double(f.length) / f.fileFormat.sampleRate
    }

    func artifact(_ kind: ArtifactKind, jobID: String) async throws -> Data {
        throw TranscriptionError.artifactUnavailable(kind)
    }
}
