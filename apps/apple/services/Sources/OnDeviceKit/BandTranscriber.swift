import CoreML
import Foundation
#if os(iOS)
import os
#endif

/// What the shared core's song arranger needs for a band draft, produced on the device.
public struct BandTranscription: Sendable {
    public var basicPitch: [DetectedNote]
    public var beats: BeatThis.Beats
    public var seconds: [String: Double]

    /// Basic Pitch's notes as the Standard MIDI file the core reads (seconds at 120 BPM, 480 ticks).
    public var basicPitchMIDI: Data { SoloTranscriber.midi(basicPitch, name: "Basic Pitch") }
}

/// A whole band's recording → Basic Pitch notes on the mix and Beat This! small0 beats, with the
/// on-device Core ML models. It is the engine's brass-band profile with muscriptor=false: Basic
/// Pitch fills every MuScriptor slot there, which is the draft the core then arranges.
public struct BandTranscriber: Sendable {
    public let store: ModelStore
    public init(store: ModelStore = .shared) { self.store = store }

    public enum Step: String, Sendable { case preparing, notes, beats }

    public func transcribe(_ url: URL, progress: (@Sendable (Step, Double) -> Void)? = nil) async throws -> BandTranscription {
        var secs: [String: Double] = [:]
        func timed<T>(_ k: String, _ f: () throws -> T) rethrows -> T {
            let t0 = Date(); let r = try f(); secs[k] = Date().timeIntervalSince(t0); return r
        }
        progress?(.preparing, 0)
        let bp = try await store.model(.basicPitch)
        let bt = try await store.model(.beatThis)
        try Task.checkCancellation()
        // Basic Pitch and Beat This both read 22.05 kHz: decoded and resampled once
        let a22 = try timed("decode") { try MonoAudio.decode(url).resampled(to: BasicPitch.sampleRate) }
        try Task.checkCancellation()
        progress?(.notes, 0.1)
        let bpOut = try timed("basicpitch") { try BasicPitch.infer(a22, model: bp) }
        try Task.checkCancellation()
        let notes = timed("bpnotes") { BasicPitch.notes(bpOut) }
        try Task.checkCancellation()
        progress?(.beats, 0.6)
        let beats = try timed("beatthis") { try BeatThis.track(a22, model: bt) }
        progress?(.beats, 1)
        guard !notes.isEmpty else { throw OnDeviceError.nothingFound("No notes were heard in this recording.") }
        guard beats.beats.count >= 2 else { throw OnDeviceError.nothingFound("No steady beat was found; the recording may be too short.") }
        return BandTranscription(basicPitch: notes, beats: beats, seconds: secs)
    }
}

/// How long a recording the device can write down as a band draft with the memory it has free.
///
/// Per second of audio the draft holds the decoded mono samples (up to 48 kHz float), the 22.05 kHz
/// copy the models read, Basic Pitch's note and onset frames (86 frames of 88 floats each, kept as
/// arrays of rows plus a flat copy while notes are read) and Beat This!'s magnitude and log-mel
/// frames (50 frames of 513 and 128 floats). That is about 0.5 MB; the estimate doubles it for
/// Core ML's own buffers and the arranger. The models themselves need about 350 MB whatever the
/// length (measured model memory: Basic Pitch 115 MB, Beat This 201 MB).
public enum OnDeviceBudget {
    public static let bytesPerSecond = 1_000_000
    public static let fixedBytes = 350_000_000

    /// The longest recording, in seconds, that fits in `available` bytes (0 when not even the models fit).
    public static func maxSeconds(available: Int) -> Double {
        max(0, Double(available - fixedBytes) / Double(bytesPerSecond))
    }

    public static func fits(seconds: Double, available: Int) -> Bool { seconds <= maxSeconds(available: available) }

    /// Memory this process may still use: what the system allows it on iOS, else (the Mac, which has
    /// no per-app limit, and the simulator, where the call answers 0) a quarter of the machine's memory.
    public static var available: Int {
        #if os(iOS)
        let left = Int(os_proc_available_memory())
        if left > 0 { return left }
        #endif
        return Int(ProcessInfo.processInfo.physicalMemory / 4)
    }
}
