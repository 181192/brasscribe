import AVFoundation
import Foundation
import Testing
@testable import OnDeviceKit

/// A stereo float WAV longer than one read chunk: left a ramp, right a constant.
private func stereoFile(frames: Int, sampleRate: Double = 44_100) throws -> URL {
    let url = FileManager.default.temporaryDirectory.appending(path: "stereo-\(UUID().uuidString).wav")
    let fmt = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 2, interleaved: false)!
    let f = try AVAudioFile(forWriting: url, settings: fmt.settings, commonFormat: .pcmFormatFloat32, interleaved: false)
    let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(frames))!
    buf.frameLength = AVAudioFrameCount(frames)
    for i in 0..<frames {
        buf.floatChannelData![0][i] = Float(i % 1000) / 1000
        buf.floatChannelData![1][i] = 0.5
    }
    try f.write(from: buf)
    return url
}

@Suite struct AudioSourceTests {
    @Test func decodesInChunksAndMixesToMono() throws {
        let frames = Int(MonoAudio.chunkFrames) * 2 + 1234
        let url = try stereoFile(frames: frames)
        defer { try? FileManager.default.removeItem(at: url) }
        let a = try MonoAudio.decode(url)
        #expect(a.sampleRate == 44_100)
        #expect(a.samples.count == frames)
        for i in [0, 999, Int(MonoAudio.chunkFrames), frames - 1] {
            #expect(abs(a.samples[i] - (Float(i % 1000) / 1000 + 0.5) / 2) < 1e-6)
        }
    }

    @Test func loadIsDecodeThenResample() throws {
        let url = try stereoFile(frames: 44_100)
        defer { try? FileManager.default.removeItem(at: url) }
        let loaded = try MonoAudio.load(url, sampleRate: 16_000)
        let resampled = try MonoAudio.decode(url).resampled(to: 16_000)
        #expect(loaded.sampleRate == 16_000)
        #expect(loaded.samples.count == 16_000)
        #expect(loaded.samples == resampled.samples)
    }

    @Test func anUnreadableFileIsAnAudioError() throws {
        let url = FileManager.default.temporaryDirectory.appending(path: "not-audio-\(UUID().uuidString).wav")
        try Data("not audio".utf8).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        #expect(throws: OnDeviceError.self) { try MonoAudio.decode(url) }
    }
}
