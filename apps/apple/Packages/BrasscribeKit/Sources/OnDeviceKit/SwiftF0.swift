import CoreML
import Foundation

/// One frame-level pitch track: a frame every 256 samples at 16 kHz (16 ms).
public struct PitchTrack: Sendable {
    public var pitchHz: [Double]
    public var confidence: [Double]
    public var loudnessDB: [Double]
    public var frameSeconds: Double { SwiftF0.frameSeconds }
    public var times: [Double] { (0..<pitchHz.count).map { Double($0) * SwiftF0.frameSeconds } }
}

/// A performed note in seconds and MIDI pitch.
public struct DetectedNote: Sendable, Equatable {
    public var onset: Double
    public var offset: Double
    public var pitch: Int
    public var velocity: Int = 80
}

/// SwiftF0 pitch detection with the Core ML window model, and its note segmentation.
/// Port of `swift_f0.core.SwiftF0.detect` and `swift_f0.music.segment_notes` (the
/// adapter the engine's solo profile uses: `segment_notes(result, pitch_hold_ms=80)`).
public enum SwiftF0 {
    public static let sampleRate = 16_000.0
    public static let hop = 256
    public static let frameSeconds = Double(hop) / sampleRate
    static let fmin: Float = 46.875
    static let fmax: Float = 2093.75
    static let leftFrames = 11, windowFrames = 1875, lookaheadFrames = 10
    static let modelFrames = leftFrames + windowFrames + lookaheadFrames // 1896
    static let silencePeak: Float = 1e-3

    public static func detect(_ audio: MonoAudio, model: MLModel) throws -> PitchTrack {
        let signal = audio.sampleRate == sampleRate ? audio.samples : try audio.resampled(to: sampleRate).samples
        let n = max(1, signal.count / hop)
        var pitch: [Double] = [], conf: [Double] = [], loud: [Double] = []
        var start = 0
        while start < n {
            let end = min(start + windowFrames, n)
            let left = max(0, start - leftFrames)
            let a = left * hop
            let b = end < n ? min(signal.count, (end + lookaheadFrames) * hop) : signal.count
            let window = Array(signal[a..<b])
            let (p, c, l) = try run(window, model: model)
            pitch += p[(start - left)..<(end - left)]
            conf += c[(start - left)..<(end - left)]
            loud += l[(start - left)..<(end - left)]
            start += windowFrames
        }
        return PitchTrack(pitchHz: pitch, confidence: conf, loudnessDB: loud)
    }

    /// One model call on a window of at most 1896 hops, zero-padded to the model's length.
    static func run(_ window: [Float], model: MLModel) throws -> ([Double], [Double], [Double]) {
        let samples = modelFrames * hop
        var padded = window
        if padded.count < samples { padded += [Float](repeating: 0, count: samples - padded.count) }
        let audio = try padded.withUnsafeBufferPointer { try MLMultiArray.float32(shape: [1, samples], values: $0) }
        let fmin = try [Self.fmin].withUnsafeBufferPointer { try MLMultiArray.float32(shape: [1], values: $0) }
        let fmax = try [Self.fmax].withUnsafeBufferPointer { try MLMultiArray.float32(shape: [1], values: $0) }
        let out = try model.prediction(from: MLDictionaryFeatureProvider(dictionary: ["audio": audio, "fmin": fmin, "fmax": fmax]))
        guard let p = out.featureValue(for: "pitch")?.multiArrayValue, let c = out.featureValue(for: "confidence")?.multiArrayValue else {
            throw OnDeviceError.model("SwiftF0 outputs")
        }
        // frames the upstream model would produce for the unpadded window
        let frames = max(1, window.count / hop)
        var pitch = p.floats().prefix(frames).map(Double.init)
        var conf = c.floats().prefix(frames).map(Double.init)
        var power = [Double](repeating: 0, count: frames)
        for i in 0..<frames {
            var peak: Float = 0, pw = 0.0
            let base = i * hop
            for j in 0..<hop where base + j < window.count {
                let x = window[base + j]
                peak = max(peak, abs(x)); pw += Double(x) * Double(x)
            }
            if peak < silencePeak { conf[i] = 0 }
            power[i] = pw
        }
        var loud = [Double](repeating: 0, count: frames)
        for i in 0..<frames {
            let prev = i > 0 ? power[i - 1] : 0
            loud[i] = 20 * log10(max(((prev + power[i]) / 512).squareRoot(), 1e-7))
        }
        if pitch.count < frames { pitch += [Double](repeating: 0, count: frames - pitch.count) }
        if conf.count < frames { conf += [Double](repeating: 0, count: frames - conf.count) }
        return (pitch, conf, loud)
    }

    /// Dynamic-programming note segmentation (swift_f0.music.segment_notes, 80 ms hold).
    public static func segmentNotes(_ r: PitchTrack, pitchHoldMs: Double = 80) -> [DetectedNote] {
        let n = r.pitchHz.count
        guard n > 0 else { return [] }
        var m = [Double](repeating: 0, count: n), w = [Double](repeating: 0, count: n)
        var any = false
        var mus = Set<Double>()
        for t in 0..<n {
            let p = r.pitchHz[t]
            if p.isFinite && p > 0 {
                m[t] = 69 + 12 * log2(p / 440)
                w[t] = r.confidence[t]
                mus.insert((m[t] * 100 + 0.5).rounded(.down) / 100)
                any = true
            }
        }
        guard any else { return [] }
        let level = r.loudnessDB
        // np.pad(level, 4, mode="symmetric")
        func lv(_ i: Int) -> Double {
            if i < 0 { return level[min(n - 1, -i - 1)] }
            if i >= n { return level[max(0, 2 * n - i - 1)] }
            return level[i]
        }
        var q = [Double](repeating: 0, count: n)
        for t in 0..<n {
            var l = -Double.infinity, rr = -Double.infinity
            for j in 0..<5 { l = max(l, lv(t - 4 + j)); rr = max(rr, lv(t + j)) }
            let cc = min(max(w[t], 0.01), 0.99)
            q[t] = -log(cc / (1 - cc)) + max(0, min(l, rr) - level[t] - 10 * log10(2.0))
        }
        let mu = mus.sorted()
        let beta = pitchHoldMs / 1000 / frameSeconds
        var vn = [Double](repeating: .infinity, count: mu.count)
        var noteStart = [Int](repeating: 0, count: mu.count)
        var back = [Int](repeating: 0, count: n + 1)
        var kind = [Int](repeating: -1, count: n + 1)
        var best = 0.0
        for t in 0..<n {
            let start = best + beta
            let mt = m[t], wt = w[t], qt = q[t]
            var j = 0
            var jmin = 0, vmin = Double.infinity
            while j < mu.count {
                if start < vn[j] { noteStart[j] = t; vn[j] = start }
                vn[j] += min(abs(mu[j] - mt), 2.0) * wt + qt
                if vn[j] < vmin { vmin = vn[j]; jmin = j }
                j += 1
            }
            if vmin < best {
                best = vmin
                back[t + 1] = noteStart[jmin]
                kind[t + 1] = jmin
            } else {
                back[t + 1] = t
            }
        }
        var notes: [DetectedNote] = []
        var b = n
        while b > 0 {
            let a = back[b]
            if kind[b] >= 0 {
                let hz = 440 * pow(2, (mu[kind[b]] - 69) / 12)
                let midi = Int((69 + 12 * log2(hz / 440) + 0.5).rounded(.down))
                notes.append(DetectedNote(onset: Double(a) * frameSeconds, offset: Double(b - 1) * frameSeconds + frameSeconds,
                                          pitch: max(0, min(127, midi))))
            }
            b = a
        }
        return notes.reversed()
    }
}
