import AVFoundation
import Foundation

/// Integrated loudness (ITU-R BS.1770 / EBU R128) of audio fed in chunks: K-weighting, 400 ms
/// blocks with 75 % overlap, the −70 LUFS absolute gate and the −10 LU relative gate. The filters
/// are pyloudnorm's, so the numbers match `sounds/` (sounds/output-stage-vectors.json).
public struct LoudnessMeter {
    private struct Biquad {
        var b0, b1, b2, a1, a2: Double
        var z1 = 0.0, z2 = 0.0
        mutating func run(_ x: Double) -> Double {
            let y = b0 * x + z1
            z1 = b1 * x - a1 * y + z2
            z2 = b2 * x - a2 * y
            return y
        }
    }

    private var filters: [(Biquad, Biquad)]
    private let subBlock: Int
    private var subEnergy: [Double] = []   // Σ over channels of the 100 ms sum of squares
    private var acc = 0.0
    private var accCount = 0

    public init(sampleRate: Double, channels: Int) {
        func shelf() -> Biquad {
            let g = 4.0, q = 1 / 2.0.squareRoot(), fc = 1500.0
            let a = pow(10, g / 40), w = 2 * Double.pi * fc / sampleRate, al = sin(w) / (2 * q), c = cos(w), s = a.squareRoot()
            let a0 = (a + 1) - (a - 1) * c + 2 * s * al
            return Biquad(b0: a * ((a + 1) + (a - 1) * c + 2 * s * al) / a0, b1: -2 * a * ((a - 1) + (a + 1) * c) / a0,
                          b2: a * ((a + 1) + (a - 1) * c - 2 * s * al) / a0,
                          a1: 2 * ((a - 1) - (a + 1) * c) / a0, a2: ((a + 1) - (a - 1) * c - 2 * s * al) / a0)
        }
        func highpass() -> Biquad {
            let q = 0.5, fc = 38.0
            let w = 2 * Double.pi * fc / sampleRate, al = sin(w) / (2 * q), c = cos(w), a0 = 1 + al
            return Biquad(b0: (1 + c) / 2 / a0, b1: -(1 + c) / a0, b2: (1 + c) / 2 / a0, a1: -2 * c / a0, a2: (1 - al) / a0)
        }
        filters = (0..<max(1, channels)).map { _ in (shelf(), highpass()) }
        subBlock = max(1, Int((sampleRate * 0.1).rounded()))
    }

    /// Feed `frames` frames of deinterleaved channel data (the channel count given at init).
    public mutating func process(_ channels: [UnsafePointer<Float>], frames: Int) {
        var i = 0
        while i < frames {
            let n = min(frames - i, subBlock - accCount)
            for (c, p) in channels.enumerated() where c < filters.count {
                var (f1, f2) = filters[c]
                var s = 0.0
                for k in i..<(i + n) { let y = f2.run(f1.run(Double(p[k]))); s += y * y }
                filters[c] = (f1, f2)
                acc += s
            }
            accCount += n
            i += n
            if accCount == subBlock { subEnergy.append(acc); acc = 0; accCount = 0 }
        }
    }

    /// Integrated loudness in LUFS; −∞ for silence or less than 400 ms of audio.
    public var integratedLUFS: Double {
        guard subEnergy.count >= 4 else { return -.infinity }
        let n = Double(subBlock * 4)
        var blocks: [Double] = []
        blocks.reserveCapacity(subEnergy.count - 3)
        for j in 0...(subEnergy.count - 4) {
            blocks.append((subEnergy[j] + subEnergy[j + 1] + subEnergy[j + 2] + subEnergy[j + 3]) / n)
        }
        func lufs(_ z: Double) -> Double { -0.691 + 10 * log10(z) }
        let absGated = blocks.filter { $0 > 0 && lufs($0) > -70 }
        guard !absGated.isEmpty else { return -.infinity }
        let rel = lufs(absGated.reduce(0, +) / Double(absGated.count)) - 10
        let gated = absGated.filter { lufs($0) > rel }
        return lufs(gated.reduce(0, +) / Double(gated.count))
    }

    /// Integrated loudness of a buffer.
    public static func integrated(_ buf: AVAudioPCMBuffer) -> Double {
        guard let d = buf.floatChannelData else { return -.infinity }
        let ch = Int(buf.format.channelCount)
        var m = LoudnessMeter(sampleRate: buf.format.sampleRate, channels: ch)
        m.process((0..<ch).map { UnsafePointer(d[$0]) }, frames: Int(buf.frameLength))
        return m.integratedLUFS
    }

    /// Integrated loudness of an audio file, read in chunks. `monoAsDualMono`: a mono file measured
    /// as the same signal in both channels (+3 dB), the way it plays from two speakers.
    public static func integrated(url: URL, monoAsDualMono: Bool = false) throws -> Double {
        let f = try AVAudioFile(forReading: url)
        let fmt = f.processingFormat
        let ch = Int(fmt.channelCount)
        guard let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: 65_536) else { return -.infinity }
        var m = LoudnessMeter(sampleRate: fmt.sampleRate, channels: ch)
        while f.framePosition < f.length {
            try f.read(into: buf)
            if buf.frameLength == 0 { break }
            guard let d = buf.floatChannelData else { break }
            m.process((0..<ch).map { UnsafePointer(d[$0]) }, frames: Int(buf.frameLength))
        }
        let dual = monoAsDualMono && ch == 1 ? 10 * log10(2.0) : 0
        return m.integratedLUFS + dual
    }
}
