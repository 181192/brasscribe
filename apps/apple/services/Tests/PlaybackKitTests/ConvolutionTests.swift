import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

/// The partitioned convolver reproduces direct convolution: an IR of two taps gives the
/// input delayed and scaled, after the 512-sample block latency.
@Test func convolverMatchesDirectConvolution() {
    let k = ConvolutionKernel()
    var ir = [Float](repeating: 0, count: 3000)
    ir[100] = 1; ir[2500] = -0.5          // spans several partitions
    k.setIR([ir, ir], sampleRate: 44_100)
    k.prepare(sampleRate: 44_100, channels: 2, maxFrames: 4096)
    let n = 8192
    let x = (0..<n).map { i in Float(sin(Double(i) * 0.05)) * (i < 4000 ? 1 : 0) }
    var out0 = [Float](repeating: 0, count: n), out1 = [Float](repeating: 0, count: n)
    let abl = AudioBufferList.allocate(maximumBuffers: 2)
    var pos = 0
    while pos < n {
        let frames = min(700, n - pos)      // not a multiple of the block
        k.resetInput(frames: frames)
        let inList = UnsafeMutableAudioBufferListPointer(k.inputList)
        for c in 0..<2 { let p = inList[c].mData!.assumingMemoryBound(to: Float.self); for i in 0..<frames { p[i] = x[pos + i] } }
        out0.withUnsafeMutableBufferPointer { o0 in out1.withUnsafeMutableBufferPointer { o1 in
            abl[0] = AudioBuffer(mNumberChannels: 1, mDataByteSize: UInt32(frames * 4), mData: UnsafeMutableRawPointer(o0.baseAddress! + pos))
            abl[1] = AudioBuffer(mNumberChannels: 1, mDataByteSize: UInt32(frames * 4), mData: UnsafeMutableRawPointer(o1.baseAddress! + pos))
            k.process(frames: frames, output: abl)
        }}
        pos += frames
    }
    let lat = ConvolutionKernel.block
    var maxErr: Float = 0
    for i in 0..<(n - lat) {
        var ref: Float = 0
        if i - 100 >= 0 { ref += x[i - 100] }
        if i - 2500 >= 0 { ref -= 0.5 * x[i - 2500] }
        maxErr = max(maxErr, abs(out0[i + lat] - ref))
    }
    print("CONV max error \(maxErr)")
    #expect(maxErr < 1e-4)
}

func roomIR() -> URL? {
    guard let r = repoRoot() else { return nil }
    let u = r.appending(path: "data/sounds/built/rooms/central-hall.wav")
    return FileManager.default.fileExists(atPath: u.path) ? u : nil
}

/// With the OpenAIR hall the reverberant energy sits +4.5 dB over the direct sound at the
/// audience seat, the calibration of the sound reference (sounds/render.py).
@Test(.enabled(if: roomIR() != nil && goldenDir() != nil)) func roomReverbIsCalibrated() throws {
    let score = try MusicXMLParser.parse(url: try #require(goldenDir()).appending(path: "brass-band.musicxml"))
    let e = try PlaybackEngine(score: score, soundBank: .locate(bundle: .main), roomIR: roomIR(), offlineFormat: PlaybackEngine.offlineFormat())
    #expect(e.usesRoomIR)
    let from = Double(score.measures[40].startTick) / Double(Score.ticksPerQuarter)
    e.roomOn = false
    let dry = try e.renderScore(fromBeat: from, beats: 16)
    e.roomOn = true
    let wetAndDry = try e.renderScore(fromBeat: from, beats: 16)
    var ed = 0.0, ew = 0.0
    let n = Int(min(dry.frameLength, wetAndDry.frameLength))
    for c in 0..<2 {
        let d = dry.floatChannelData![c], m = wetAndDry.floatChannelData![c]
        for i in 0..<n { ed += Double(d[i] * d[i]); let w = m[i] - d[i]; ew += Double(w * w) }
    }
    let ratio = 10 * log10(ew / max(ed, 1e-20))
    print("ROOM wet-to-direct \(String(format: "%.2f", ratio)) dB (target \(PlaybackEngine.wetToDirectDB))")
    #expect(abs(ratio - PlaybackEngine.wetToDirectDB) < 1.5)
}
