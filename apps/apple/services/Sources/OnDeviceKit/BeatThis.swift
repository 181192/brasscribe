import Accelerate
import CoreML
import Foundation

/// Beat This! small0 with the Core ML network and the host-side frontend and decoding.
/// Ports `beat_this.preprocessing.LogMelSpect` (torchaudio MelSpectrogram: n_fft 1024,
/// hop 441, 128 slaney-scale mels from 30 Hz to 11 kHz, magnitude, frame-length
/// normalisation, log1p(1000 x)), `split_predict_aggregate` (1500-frame chunks, 6-frame
/// borders, keep_first) and the "minimal" postprocessor, then numbers the beats like
/// `save_beat_tsv` so the result is a `.beats` table.
public enum BeatThis {
    public static let sampleRate = 22_050.0
    static let nFFT = 1024, hop = 441, nMels = 128, fps = 50.0
    static let chunk = 1500, border = 6

    public struct Beats: Sendable, Equatable {
        public var beats: [Double]
        public var downbeats: [Double]
        public var numbers: [Int]

        /// `time<TAB>number` per line, number 1 = downbeat.
        public var tsv: String { zip(beats, numbers).map { "\($0)\t\($1)" }.joined(separator: "\n") + "\n" }
    }

    // MARK: log-mel

    static let melBank: [[Float]] = {
        func hzToMel(_ f: Double) -> Double {
            let fsp = 200.0 / 3, minLogHz = 1000.0, minLogMel = 15.0, logstep = log(6.4) / 27
            return f < minLogHz ? f / fsp : minLogMel + log(f / minLogHz) / logstep
        }
        func melToHz(_ m: Double) -> Double {
            let fsp = 200.0 / 3, minLogHz = 1000.0, minLogMel = 15.0, logstep = log(6.4) / 27
            return m < minLogMel ? fsp * m : minLogHz * exp(logstep * (m - minLogMel))
        }
        let nFreqs = nFFT / 2 + 1
        let freqs = (0..<nFreqs).map { Double($0) * (sampleRate / 2) / Double(nFreqs - 1) }
        let mMin = hzToMel(30), mMax = hzToMel(11_000)
        let fPts = (0..<(nMels + 2)).map { melToHz(mMin + (mMax - mMin) * Double($0) / Double(nMels + 1)) }
        var fb = [[Float]](repeating: [Float](repeating: 0, count: nFreqs), count: nMels)
        for m in 0..<nMels {
            for k in 0..<nFreqs {
                let down = (freqs[k] - fPts[m]) / (fPts[m + 1] - fPts[m])
                let up = (fPts[m + 2] - freqs[k]) / (fPts[m + 2] - fPts[m + 1])
                fb[m][k] = Float(max(0, min(down, up)))
            }
        }
        return fb
    }()

    /// The mel bank transposed to nFreqs x nMels, for the matrix product.
    static let melBankT: [Float] = {
        let nFreqs = nFFT / 2 + 1
        var t = [Float](repeating: 0, count: nFreqs * nMels)
        for m in 0..<nMels { for k in 0..<nFreqs { t[k * nMels + m] = melBank[m][k] } }
        return t
    }()

    /// Log-mel spectrogram, frames x 128 (row-major).
    public static func logMel(_ audio: MonoAudio) throws -> (values: [Float], frames: Int) {
        let x = audio.sampleRate == sampleRate ? audio.samples : try audio.resampled(to: sampleRate).samples
        let pad = nFFT / 2
        guard x.count > pad else { throw OnDeviceError.audio("recording too short for beat tracking") }
        // center=True, reflect padding
        var s = [Float](repeating: 0, count: x.count + 2 * pad)
        for i in 0..<pad { s[pad - 1 - i] = x[i + 1] }
        for i in 0..<x.count { s[pad + i] = x[i] }
        for i in 0..<pad { s[pad + x.count + i] = x[x.count - 2 - i] }
        let frames = 1 + x.count / hop
        // periodic Hann
        let win = (0..<nFFT).map { Float(0.5 - 0.5 * cos(2 * Double.pi * Double($0) / Double(nFFT))) }
        let dft = try vDSP.DiscreteFourierTransform(previous: nil, count: nFFT, direction: .forward,
                                                    transformType: .complexComplex, ofType: Float.self)
        let nFreqs = nFFT / 2 + 1
        let norm = 1 / Float(nFFT).squareRoot()
        // magnitudes, frames x nFreqs
        var mags = [Float](repeating: 0, count: frames * nFreqs)
        var re = [Float](repeating: 0, count: nFFT)
        let zeros = [Float](repeating: 0, count: nFFT)
        var oRe = [Float](repeating: 0, count: nFFT), oIm = [Float](repeating: 0, count: nFFT)
        for f in 0..<frames {
            let base = f * hop
            for i in 0..<nFFT { re[i] = s[base + i] * win[i] }
            dft.transform(inputReal: re, inputImaginary: zeros, outputReal: &oRe, outputImaginary: &oIm)
            for k in 0..<nFreqs { mags[f * nFreqs + k] = (oRe[k] * oRe[k] + oIm[k] * oIm[k]).squareRoot() * norm }
        }
        // mel = mags (frames x nFreqs) * bankT (nFreqs x nMels)
        var out = [Float](repeating: 0, count: frames * nMels)
        vDSP_mmul(mags, 1, melBankT, 1, &out, 1, vDSP_Length(frames), vDSP_Length(nMels), vDSP_Length(nFreqs))
        for i in 0..<out.count { out[i] = log1p(1000 * out[i]) }
        return (out, frames)
    }

    // MARK: network

    public static func logits(_ spect: [Float], frames: Int, model: MLModel) throws -> (beat: [Float], downbeat: [Float]) {
        var starts = Array(stride(from: -border, to: frames - border, by: chunk - 2 * border))
        if frames > chunk - 2 * border { starts[starts.count - 1] = frames - (chunk - border) }
        var beat = [Float](repeating: -1000, count: frames), down = [Float](repeating: -1000, count: frames)
        // keep_first: later chunks are written first, earlier ones overwrite
        for start in starts.reversed() {
            var input = [Float](repeating: 0, count: chunk * nMels)
            for r in 0..<chunk {
                let src = start + r
                guard src >= 0 && src < frames else { continue }
                for m in 0..<nMels { input[r * nMels + m] = spect[src * nMels + m] }
            }
            let x = try input.withUnsafeBufferPointer { try MLMultiArray.float32(shape: [1, chunk, nMels], values: $0) }
            let o = try model.prediction(from: MLDictionaryFeatureProvider(dictionary: ["spect": x]))
            guard let b = o.featureValue(for: "beat")?.multiArrayValue?.floats(),
                  let d = o.featureValue(for: "downbeat")?.multiArrayValue?.floats() else { throw OnDeviceError.model("Beat This outputs") }
            for r in border..<(chunk - border) {
                let t = start + r
                guard t >= 0 && t < frames else { continue }
                beat[t] = b[r]; down[t] = d[r]
            }
        }
        return (beat, down)
    }

    // MARK: decoding

    static func peaks(_ logits: [Float]) -> [Double] {
        let n = logits.count
        var frames: [Int] = []
        for t in 0..<n {
            var mx = -Float.infinity
            for j in max(0, t - 3)...min(n - 1, t + 3) { mx = max(mx, logits[j]) }
            if logits[t] == mx && logits[t] > 0 { frames.append(t) }
        }
        // deduplicate_peaks(width=1): runs of adjacent frames become their running mean
        var out: [Double] = []
        guard var p = frames.first.map(Double.init) else { return [] }
        var c = 1.0
        for f in frames.dropFirst() {
            if Double(f) - p <= 1 { c += 1; p += (Double(f) - p) / c } else { out.append(p); p = Double(f); c = 1 }
        }
        out.append(p)
        return out
    }

    public static func decode(beat: [Float], downbeat: [Float]) -> Beats {
        let bt = peaks(beat).map { $0 / fps }
        var dt = peaks(downbeat).map { $0 / fps }
        if !bt.isEmpty {
            dt = dt.map { d in bt.min { abs($0 - d) < abs($1 - d) }! }
        }
        dt = Array(Set(dt)).sorted()
        return Beats(beats: bt, downbeats: dt, numbers: numbers(beats: bt, downbeats: dt))
    }

    /// `beat_this.utils.infer_beat_numbers`.
    static func numbers(beats: [Double], downbeats: [Double]) -> [Int] {
        var startCounter = 1
        if downbeats.count >= 2 {
            let first = beats.firstIndex { $0 >= downbeats[0] } ?? beats.count
            let second = beats.firstIndex { $0 >= downbeats[1] } ?? beats.count
            let inFirst = second - first
            if first < inFirst { startCounter = inFirst - first }
        }
        var out: [Int] = []
        var counter = startCounter
        var di = 0
        for b in beats {
            if di < downbeats.count && b == downbeats[di] { counter = 1; di += 1 } else { counter += 1 }
            out.append(counter)
        }
        return out
    }

    public static func track(_ audio: MonoAudio, model: MLModel) throws -> Beats {
        let (spect, frames) = try logMel(audio)
        let (b, d) = try logits(spect, frames: frames, model: model)
        return decode(beat: b, downbeat: d)
    }
}
