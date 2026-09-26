import AVFoundation
import Foundation

public enum OnDeviceError: Error, CustomStringConvertible, Equatable {
    case audio(String)
    case modelMissing(String)
    case model(String)
    case nothingFound(String)

    public var description: String {
        switch self {
        case .audio(let s): return "audio: \(s)"
        case .modelMissing(let s): return "model not downloaded: \(s)"
        case .model(let s): return "model: \(s)"
        case .nothingFound(let s): return s
        }
    }
}

/// Mono float audio at a fixed sample rate.
public struct MonoAudio: Sendable {
    public let samples: [Float]
    public let sampleRate: Double
    public var duration: Double { Double(samples.count) / sampleRate }

    public init(samples: [Float], sampleRate: Double) { self.samples = samples; self.sampleRate = sampleRate }

    /// Decode any file AVFoundation reads, mix to mono and resample with AVAudioConverter
    /// (mastering-quality sample-rate conversion).
    public static func load(_ url: URL, sampleRate: Double) throws -> MonoAudio {
        let file: AVAudioFile
        do { file = try AVAudioFile(forReading: url) } catch { throw OnDeviceError.audio("\(url.lastPathComponent): \(error.localizedDescription)") }
        let inFormat = file.processingFormat
        guard let inBuf = AVAudioPCMBuffer(pcmFormat: inFormat, frameCapacity: AVAudioFrameCount(file.length)) else {
            throw OnDeviceError.audio("buffer")
        }
        try file.read(into: inBuf)
        // mix to mono at the source rate
        let n = Int(inBuf.frameLength)
        var mono = [Float](repeating: 0, count: n)
        let ch = Int(inFormat.channelCount)
        if let d = inBuf.floatChannelData {
            for c in 0..<ch { for i in 0..<n { mono[i] += d[c][i] } }
            if ch > 1 { let s = 1 / Float(ch); for i in 0..<n { mono[i] *= s } }
        }
        return try MonoAudio(samples: mono, sampleRate: inFormat.sampleRate).resampled(to: sampleRate)
    }

    public func resampled(to rate: Double) throws -> MonoAudio {
        if rate == sampleRate { return self }
        let src = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false)!
        let dst = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: rate, channels: 1, interleaved: false)!
        guard let conv = AVAudioConverter(from: src, to: dst),
              let inBuf = AVAudioPCMBuffer(pcmFormat: src, frameCapacity: AVAudioFrameCount(samples.count)) else {
            throw OnDeviceError.audio("converter")
        }
        conv.sampleRateConverterQuality = AVAudioQuality.max.rawValue
        conv.sampleRateConverterAlgorithm = AVSampleRateConverterAlgorithm_Mastering
        inBuf.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { inBuf.floatChannelData![0].update(from: $0.baseAddress!, count: samples.count) }
        let outCap = AVAudioFrameCount(Double(samples.count) * rate / sampleRate + 4096)
        guard let outBuf = AVAudioPCMBuffer(pcmFormat: dst, frameCapacity: outCap) else { throw OnDeviceError.audio("buffer") }
        var fed = false
        var err: NSError?
        let status = conv.convert(to: outBuf, error: &err) { _, st in
            if fed { st.pointee = .endOfStream; return nil }
            fed = true; st.pointee = .haveData; return inBuf
        }
        if status == .error { throw OnDeviceError.audio(err?.localizedDescription ?? "convert") }
        let expected = Int((Double(samples.count) * rate / sampleRate).rounded())
        let got = Int(outBuf.frameLength)
        var out = Array(UnsafeBufferPointer(start: outBuf.floatChannelData![0], count: got))
        if out.count > expected { out.removeLast(out.count - expected) } else if out.count < expected { out += [Float](repeating: 0, count: expected - out.count) }
        return MonoAudio(samples: out, sampleRate: rate)
    }
}
