import Accelerate
import CoreML
import Foundation

/// Basic Pitch with the batch-1 Core ML model and the upstream note decoding.
/// Port of `basic_pitch.inference.run_inference` (windowing and unwrap) and
/// `basic_pitch.note_creation.output_to_notes_polyphonic` with the CLI defaults the engine
/// uses: onset 0.5, frame 0.3, minimum length 127.7 ms (11 frames), inferred onsets, melodia.
public enum BasicPitch {
    public static let sampleRate = 22_050.0
    static let fftHop = 256
    static let windowSamples = 22_050 * 2 - 256          // 43844
    static let overlapFrames = 30
    static let overlapSamples = 30 * 256
    static let hopSamples = windowSamples - overlapSamples
    static let fps = 22_050 / 256                          // 86 (integer, as upstream)
    static let annotFrames = fps * 2                       // 172
    static let midiOffset = 21
    static let maxFreqIdx = 87

    public struct Output: Sendable {
        public var frames: [[Float]]   // time x 88
        public var onsets: [[Float]]
    }

    public static func infer(_ audio: MonoAudio, model: MLModel) throws -> Output {
        let sig = audio.sampleRate == sampleRate ? audio.samples : try audio.resampled(to: sampleRate).samples
        let original = sig.count
        let padded = [Float](repeating: 0, count: overlapSamples / 2) + sig
        var notes: [[Float]] = [], onsets: [[Float]] = []
        var i = 0
        let olap = overlapFrames / 2
        while i < padded.count {
            var window = Array(padded[i..<min(i + windowSamples, padded.count)])
            if window.count < windowSamples { window += [Float](repeating: 0, count: windowSamples - window.count) }
            let x = try window.withUnsafeBufferPointer { try MLMultiArray.float32(shape: [1, windowSamples, 1], values: $0) }
            let out = try model.prediction(from: MLDictionaryFeatureProvider(dictionary: ["input_2": x]))
            guard let note = out.featureValue(for: "Identity_1")?.multiArrayValue,
                  let onset = out.featureValue(for: "Identity_2")?.multiArrayValue else { throw OnDeviceError.model("Basic Pitch outputs") }
            let nf = note.floats(), of = onset.floats()
            let t = note.shape[1].intValue
            for r in olap..<(t - olap) {
                notes.append(Array(nf[(r * 88)..<(r * 88 + 88)]))
                onsets.append(Array(of[(r * 88)..<(r * 88 + 88)]))
            }
            i += hopSamples
        }
        let keep = Int((Double(original) * Double(fps) / sampleRate).rounded(.down))
        if notes.count > keep { notes.removeLast(notes.count - keep); onsets.removeLast(onsets.count - keep) }
        return Output(frames: notes, onsets: onsets)
    }

    /// `model_frames_to_time`: frame times with the per-window offset correction.
    static func frameTime(_ f: Int) -> Double {
        let windowOffset = (Double(fftHop) / sampleRate) * (Double(annotFrames) - Double(windowSamples) / Double(fftHop)) + 0.0018
        return Double(f * fftHop) / sampleRate - windowOffset * (Double(f) / Double(annotFrames)).rounded(.down)
    }

    public static func notes(_ o: Output, onsetThresh: Float = 0.5, frameThresh: Float = 0.3, minNoteLen: Int = 11,
                             energyTol: Int = 11) -> [DetectedNote] {
        let n = o.frames.count
        guard n > 2 else { return [] }
        let frames = o.frames
        var onsets = o.onsets
        // inferred onsets from frame differences
        var diff = [[Float]](repeating: [Float](repeating: 0, count: 88), count: n)
        var maxDiff: Float = 0, maxOnset: Float = 0
        for t in 0..<n {
            for f in 0..<88 {
                let d1 = frames[t][f] - (t >= 1 ? frames[t - 1][f] : 0)
                let d2 = frames[t][f] - (t >= 2 ? frames[t - 2][f] : 0)
                var d = min(d1, d2)
                if d < 0 || t < 2 { d = 0 }
                diff[t][f] = d
                maxDiff = max(maxDiff, d)
                maxOnset = max(maxOnset, onsets[t][f])
            }
        }
        for t in 0..<n {
            for f in 0..<88 {
                let d = maxDiff > 0 ? maxOnset * diff[t][f] / maxDiff : .nan
                // np.max with a NaN yields NaN, which then never passes the threshold
                onsets[t][f] = d.isNaN ? .nan : max(onsets[t][f], d)
            }
        }
        // peaks along time (scipy.signal.argrelmax, order 1)
        var starts: [(Int, Int)] = []
        for t in 1..<(n - 1) {
            for f in 0..<88 {
                let v = onsets[t][f]
                if v > onsets[t - 1][f] && v > onsets[t + 1][f] && v >= onsetThresh { starts.append((t, f)) }
            }
        }
        // flat time x 88 energy, so the melodia step can use a vectorised argmax
        var remaining = [Float](repeating: 0, count: n * 88)
        for t in 0..<n { for f in 0..<88 { remaining[t * 88 + f] = frames[t][f] } }
        var events: [(Int, Int, Int, Float)] = []
        func clear(_ t: Int, _ f: Int) {
            remaining[t * 88 + f] = 0
            if f < maxFreqIdx { remaining[t * 88 + f + 1] = 0 }
            if f > 0 { remaining[t * 88 + f - 1] = 0 }
        }
        for (s, f) in starts.reversed() {
            if s >= n - 1 { continue }
            var i = s + 1, k = 0
            while i < n - 1 && k < energyTol {
                if remaining[i * 88 + f] < frameThresh { k += 1 } else { k = 0 }
                i += 1
            }
            i -= k
            if i - s <= minNoteLen { continue }
            for t in s..<i { clear(t, f) }
            var amp: Float = 0
            for t in s..<i { amp += frames[t][f] }
            events.append((s, i, f + midiOffset, amp / Float(i - s)))
        }
        // melodia trick
        while true {
            var best: Float = 0
            var at: vDSP_Length = 0
            vDSP_maxvi(remaining, 1, &best, &at, vDSP_Length(remaining.count))
            if best <= frameThresh { break }
            let bt = Int(at) / 88, bf = Int(at) % 88
            remaining[Int(at)] = 0
            var i = bt + 1, k = 0
            while i < n - 1 && k < energyTol {
                if remaining[i * 88 + bf] < frameThresh { k += 1 } else { k = 0 }
                clear(i, bf)
                i += 1
            }
            let iEnd = i - 1 - k
            i = bt - 1; k = 0
            while i > 0 && k < energyTol {
                if remaining[i * 88 + bf] < frameThresh { k += 1 } else { k = 0 }
                clear(i, bf)
                i -= 1
            }
            let iStart = i + 1 + k
            if iEnd - iStart <= minNoteLen { continue }
            var amp: Float = 0
            for t in iStart..<iEnd { amp += frames[t][bf] }
            events.append((iStart, iEnd, bf + midiOffset, amp / Float(iEnd - iStart)))
        }
        return events.map { DetectedNote(onset: frameTime($0.0), offset: frameTime($0.1), pitch: $0.2,
                                         velocity: max(1, min(127, Int(($0.3 * 127).rounded())))) }
            .sorted { ($0.onset, $0.pitch) < ($1.onset, $1.pitch) }
    }
}
