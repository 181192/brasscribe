import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

/// sounds/output-stage-vectors.json: the limiter curve, the recording gain rule and the loudness
/// meter every Play app shares (sounds/playback_levels.py).
func outputStageVectors() -> [String: Any]? {
    guard let r = repoRoot(), let d = try? Data(contentsOf: r.appending(path: "sounds/output-stage-vectors.json")) else { return nil }
    return try? JSONSerialization.jsonObject(with: d) as? [String: Any]
}

private func dB(_ x: Float) -> Double { 20 * log10(Double(max(x, 1e-9))) }

@Suite(.enabled(if: outputStageVectors() != nil)) struct SharedLevelTests {
    let v = outputStageVectors()!

    @Test func constantsMatchPlaybackLevels() throws {
        let levels = try #require(v["levels"] as? [String: Any])
        let lim = try #require(levels["limiter"] as? [String: Any])
        #expect(lim["threshold"] as? Double == PlaybackLevels.limiterThreshold)
        #expect(lim["ceiling"] as? Double == PlaybackLevels.limiterCeiling)
        let band = try #require(levels["band"] as? [String: Any])
        #expect(band["phrase_lufs"] as? Double == PlaybackLevels.bandPhraseLUFS)
        #expect((band["gain_db"] as? [String: Double])?["apple"] == PlaybackLevels.bandGainDB)
        let rec = try #require(levels["recording"] as? [String: Any])
        #expect(rec["target_lufs"] as? Double == PlaybackLevels.recordingTargetLUFS)
        #expect(rec["max_boost_db"] as? Double == PlaybackLevels.recordingMaxBoostDB)
        #expect(rec["max_cut_db"] as? Double == PlaybackLevels.recordingMaxCutDB)
        let met = try #require(levels["metronome"] as? [String: Any])
        #expect(met["click_peak_dbfs"] as? Double == PlaybackLevels.metronomeClickPeakDBFS)
    }

    @Test func limiterMatchesTheSharedCurve() throws {
        let rows = try #require(v["limiter"] as? [[String: Double]])
        #expect(rows.count > 10)
        for r in rows {
            let x = Float(r["in"]!), want = r["out"]!
            #expect(abs(Double(OutputStageKernel.limit(x)) - want) < 1e-6, "limit(\(x))")
        }
    }

    @Test func recordingGainMatchesTheSharedRule() throws {
        let rows = try #require(v["recording_gain"] as? [[String: Any]])
        for r in rows {
            let lufs = (r["lufs"] as? Double) ?? -.infinity
            #expect(abs(PlaybackLevels.recordingGainDB(forLUFS: lufs) - (r["gain_db"] as! Double)) < 1e-6, "\(lufs)")
        }
    }

    @Test func meterMatchesPyloudnorm() throws {
        let cases = try #require(v["loudness"] as? [[String: Any]])
        for c in cases {
            let rate = c["rate"] as! Double, ch = c["channels"] as! Int
            let tones = c["tones"] as! [[Double]], segs = c["segments"] as! [[Double]]
            var x: [Float] = []
            var t0 = 0
            for s in segs {
                let n = Int((s[0] * rate).rounded())
                for i in 0..<n {
                    let t = Double(t0 + i) / rate
                    x.append(Float(tones.reduce(0) { $0 + $1[1] * sin(2 * .pi * $1[0] * t) } * s[1]))
                }
                t0 += n
            }
            var m = LoudnessMeter(sampleRate: rate, channels: ch)
            x.withUnsafeBufferPointer { p in
                // uneven chunks, as a file or a render delivers them
                var i = 0, k = 0
                while i < p.count {
                    let n = min(p.count - i, [1000, 4096, 333][k % 3]); k += 1
                    m.process(Array(repeating: p.baseAddress! + i, count: ch), frames: n)
                    i += n
                }
            }
            let got = m.integratedLUFS
            if let want = c["lufs"] as? Double {
                #expect(abs(got - want) < 0.1, "\(c["name"]!): \(got) vs \(want)")
            } else {
                #expect(got == -.infinity, "\(c["name"]!)")
            }
        }
    }
}

func capturedRecording() -> URL? {
    guard let r = repoRoot() else { return nil }
    let f = r.appending(path: "data/mikkel/captured.wav")
    return FileManager.default.fileExists(atPath: f.path) ? f : nil
}

/// The original recording plays at the band's loudness, whatever level it was recorded at.
@Suite(.serialized, .enabled(if: goldenDir() != nil && capturedRecording() != nil))
struct RecordingLevelTests {
    let score: Score
    let composition: Composition
    let recording: URL

    init() throws {
        let dir = try #require(goldenDir())
        score = try MusicXMLParser.parse(url: dir.appending(path: "brass-band.musicxml"))
        composition = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
        recording = try #require(capturedRecording())
    }

    func engine(_ url: URL) throws -> PlaybackEngine {
        try PlaybackEngine(score: score, tempoMap: composition.tempoMap, originalURL: url,
                           soundBank: .locate(bundle: .main), roomIR: nil, offlineFormat: PlaybackEngine.offlineFormat())
    }

    /// A copy of the recording's first `seconds`, mono (the left channel) or stereo, `gainDB` louder or softer.
    func variant(seconds: Double, mono: Bool, gainDB: Double) throws -> URL {
        let src = try AVAudioFile(forReading: recording)
        let n = AVAudioFrameCount(seconds * src.processingFormat.sampleRate)
        let buf = try #require(AVAudioPCMBuffer(pcmFormat: src.processingFormat, frameCapacity: n))
        try src.read(into: buf, frameCount: n)
        let fmt = try #require(AVAudioFormat(standardFormatWithSampleRate: src.processingFormat.sampleRate, channels: mono ? 1 : 2))
        let out = try #require(AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: n))
        out.frameLength = buf.frameLength
        let g = Float(pow(10, gainDB / 20))
        for c in 0..<Int(fmt.channelCount) {
            for i in 0..<Int(buf.frameLength) { out.floatChannelData![c][i] = buf.floatChannelData![c][i] * g }
        }
        let url = FileManager.default.temporaryDirectory.appending(path: "rec-\(UUID().uuidString).caf")
        let f = try AVAudioFile(forWriting: url, settings: fmt.settings)
        try f.write(from: out)
        return url
    }

    @Test func loudnessIsMeasuredQuickly() throws {
        let t0 = Date()
        let lufs = try LoudnessMeter.integrated(url: recording)
        let secs = Date().timeIntervalSince(t0)
        print("LEVELS captured.wav \(lufs) LUFS, measured in \(secs) s")
        #expect(lufs > -30 && lufs < -5)
    }

    /// The whole recording through the engine lands on the target.
    @Test func recordingPlaysAtTheTarget() throws {
        let e = try engine(recording)
        let file = try #require(e.originalLUFS)
        let f = try #require(e.originalFile)
        let buf = try e.renderOriginal(fromBeat: 0, seconds: Double(f.length) / f.processingFormat.sampleRate)
        let lufs = LoudnessMeter.integrated(buf)
        print("LEVELS recording file \(file) LUFS, gain \(e.originalGainDB) dB, played \(lufs) LUFS, peak \(dB(buf.peak)) dBFS")
        #expect(abs(lufs - PlaybackLevels.recordingTargetLUFS) < 0.5)
        #expect(buf.peak <= OutputStageKernel.ceiling)
    }

    /// Quiet, loud and mono recordings all play at the target, and the limiter catches the boost.
    @Test(arguments: [(-8.0, false), (8.0, false), (-6.0, true), (6.0, true)])
    func anyRecordingPlaysAtTheTarget(gainDB: Double, mono: Bool) throws {
        let url = try variant(seconds: 60, mono: mono, gainDB: gainDB)
        defer { try? FileManager.default.removeItem(at: url) }
        let e = try engine(url)
        let buf = try e.renderOriginal(fromBeat: 0, seconds: 60)
        let lufs = LoudnessMeter.integrated(buf)
        print("LEVELS variant \(gainDB) dB mono \(mono): file \(e.originalLUFS ?? .nan) LUFS, gain \(e.originalGainDB) dB, played \(lufs) LUFS, peak \(dB(buf.peak)) dBFS")
        #expect(abs(lufs - PlaybackLevels.recordingTargetLUFS) < 0.5, "a mono file plays from both speakers at full level")
        #expect(buf.peak <= OutputStageKernel.ceiling)
    }

    /// A very quiet recording gets the capped boost, no more.
    @Test func boostIsCapped() throws {
        let url = try variant(seconds: 30, mono: false, gainDB: -20)
        defer { try? FileManager.default.removeItem(at: url) }
        let e = try engine(url)
        let file = try #require(e.originalLUFS)
        #expect(e.originalGainDB == PlaybackLevels.recordingMaxBoostDB)
        let lufs = LoudnessMeter.integrated(try e.renderOriginal(fromBeat: 0, seconds: 30))
        #expect(abs(lufs - (file + PlaybackLevels.recordingMaxBoostDB)) < 0.5)
    }

    /// A whole arrangement from the band sits where the recording does.
    @Test func bandArrangementMatchesTheRecordingTarget() throws {
        let e = try engine(recording)
        let buf = try e.renderScore(fromBeat: 0, beats: Double(score.endTick) / Double(Score.ticksPerQuarter))
        let lufs = LoudnessMeter.integrated(buf)
        print("LEVELS golden arrangement \(lufs) LUFS, peak \(dB(buf.peak)) dBFS")
        #expect(abs(lufs - PlaybackLevels.recordingTargetLUFS) < 1.5)
        #expect(buf.peak <= OutputStageKernel.ceiling)
    }
}
