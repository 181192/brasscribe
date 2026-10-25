import CoreML
import Foundation

/// Everything the shared core needs to notate a solo recording, produced on the device.
public struct SoloTranscription: Sendable {
    public var swiftF0: [DetectedNote]
    public var basicPitch: [DetectedNote]
    public var beats: BeatThis.Beats
    public var contour: PitchTrack
    public var seconds: [String: Double]

    /// Standard MIDI files the core's layer arranger reads (seconds at 120 BPM, 480 ticks).
    public var swiftF0MIDI: Data { SoloTranscriber.midi(swiftF0, name: "SwiftF0") }
    public var basicPitchMIDI: Data { SoloTranscriber.midi(basicPitch, name: "Basic Pitch") }
    public static var emptyMIDI: Data { SoloTranscriber.midi([], name: "empty") }
}

/// Recorded solo → SwiftF0 notes (the spine), Basic Pitch notes (confirmation) and beats,
/// all with on-device Core ML models. The engine's solo profile runs the same three tools
/// (plus MuScriptor, which has no on-device conversion yet).
public struct SoloTranscriber: Sendable {
    public let store: ModelStore
    public init(store: ModelStore = .shared) { self.store = store }

    public enum Step: String, Sendable { case preparing, pitch, confirm, beats }

    public func transcribe(_ url: URL, progress: (@Sendable (Step, Double) -> Void)? = nil) async throws -> SoloTranscription {
        var secs: [String: Double] = [:]
        func timed<T>(_ k: String, _ f: () throws -> T) rethrows -> T {
            let t0 = Date(); let r = try f(); secs[k] = Date().timeIntervalSince(t0); return r
        }
        progress?(.preparing, 0)
        let sf0 = try await store.model(.swiftF0)
        let bp = try await store.model(.basicPitch)
        let bt = try await store.model(.beatThis)
        // decoded once; each model gets its own sample rate from the same mono samples
        let mono = try timed("decode") { try MonoAudio.decode(url) }
        let a16 = try timed("resample16k") { try mono.resampled(to: SwiftF0.sampleRate) }
        let a22 = try timed("resample22k") { try mono.resampled(to: BasicPitch.sampleRate) }
        progress?(.pitch, 0.1)
        let track = try timed("swiftf0") { try SwiftF0.detect(a16, model: sf0) }
        let sw = timed("segment") { SwiftF0.segmentNotes(track) }
        progress?(.confirm, 0.4)
        let bpOut = try timed("basicpitch") { try BasicPitch.infer(a22, model: bp) }
        let bpNotes = timed("bpnotes") { BasicPitch.notes(bpOut) }
        progress?(.beats, 0.7)
        let beats = try timed("beatthis") { try BeatThis.track(a22, model: bt) }
        progress?(.beats, 1)
        guard !sw.isEmpty else { throw OnDeviceError.nothingFound("No notes were heard in this recording.") }
        guard beats.beats.count >= 2 else { throw OnDeviceError.nothingFound("No steady beat was found; the recording may be too short.") }
        return SoloTranscription(swiftF0: sw, basicPitch: bpNotes, beats: beats, contour: track, seconds: secs)
    }

    /// Format-0 SMF with the notes in seconds at 120 BPM (480 ticks per beat), like the adapters write.
    public static func midi(_ notes: [DetectedNote], name: String) -> Data {
        let tpq = 480, tempo = 120.0
        func ticks(_ s: Double) -> Int { Int((s * Double(tpq) * tempo / 60).rounded()) }
        var ev: [(Int, Int, [UInt8])] = []
        for n in notes {
            let s = ticks(n.onset), e = max(s + 1, ticks(n.offset))
            ev.append((s, 1, [0x90, UInt8(n.pitch), UInt8(max(1, min(127, n.velocity)))]))
            ev.append((e, 0, [0x80, UInt8(n.pitch), 0]))
        }
        ev.sort { ($0.0, $0.1) < ($1.0, $1.1) }
        func vlq(_ v: Int) -> [UInt8] {
            var v = v; var o: [UInt8] = [UInt8(v & 0x7F)]; v >>= 7
            while v > 0 { o.insert(UInt8(v & 0x7F) | 0x80, at: 0); v >>= 7 }
            return o
        }
        var trk: [UInt8] = [0x00, 0xFF, 0x03] + vlq(name.utf8.count) + Array(name.utf8)
        trk += [0x00, 0xFF, 0x51, 0x03, 0x07, 0xA1, 0x20] // 500000 us per beat
        var last = 0
        for (t, _, b) in ev { trk += vlq(t - last) + b; last = t }
        trk += [0x00, 0xFF, 0x2F, 0x00]
        func be32(_ v: Int) -> [UInt8] { [UInt8(v >> 24 & 0xFF), UInt8(v >> 16 & 0xFF), UInt8(v >> 8 & 0xFF), UInt8(v & 0xFF)] }
        let head: [UInt8] = Array("MThd".utf8) + be32(6) + [0, 0, 0, 1, UInt8(tpq >> 8), UInt8(tpq & 0xFF)]
        return Data(head + Array("MTrk".utf8) + be32(trk.count) + trk)
    }
}
