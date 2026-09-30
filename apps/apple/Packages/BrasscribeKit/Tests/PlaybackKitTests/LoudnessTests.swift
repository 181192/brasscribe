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
        #expect(band["arrangement_lufs"] as? Double == PlaybackLevels.bandArrangementLUFS)
        var trims = try #require(band["apple_seat_trim_db"] as? [String: Any])
        trims["about"] = nil
        #expect(trims as? [String: Double] == PlaybackLevels.appleSeatTrimDB)
        var kit = try #require(band["apple_kit_trim_db"] as? [String: Any])
        let pop = try #require(kit.removeValue(forKey: "pop_kit") as? [String: Double])
        kit["about"] = nil
        #expect((kit as? [String: Double]).map { Dictionary(uniqueKeysWithValues: $0.map { (Int($0.key)!, $0.value) }) } == PlaybackLevels.appleKitTrimDB)
        #expect(Dictionary(uniqueKeysWithValues: pop.map { (Int($0.key)!, $0.value) }) == PlaybackLevels.applePopKitTrimDB)
        #expect((band["dry_room_gain_db"] as? [String: Any])?["apple"] as? Double == PlaybackLevels.dryRoomGainDB)
        let sampler = try #require((levels["dynamics"] as? [String: Any])?["sampler_velocity"] as? [String: Any])
        #expect((sampler["apple_pitched"] as? [[Int]])?.map { [$0[0], $0[1]] } == PlaybackLevels.samplerVelocityPitched.map { [$0.0, $0.1] })
        #expect((sampler["apple_percussion"] as? [[Int]])?.map { [$0[0], $0[1]] } == PlaybackLevels.samplerVelocityPercussion.map { [$0.0, $0.1] })
        let rec = try #require(levels["recording"] as? [String: Any])
        #expect(rec["fallback_lufs"] as? Double == PlaybackLevels.recordingFallbackLUFS)
        #expect(rec["min_target_lufs"] as? Double == PlaybackLevels.recordingMinTargetLUFS)
        #expect(rec["max_target_lufs"] as? Double == PlaybackLevels.recordingMaxTargetLUFS)
        #expect((rec["band_estimate"] as? [String: Any])?["offset_db"] as? Double == PlaybackLevels.bandEstimateOffsetDB)
        let knots = try #require(sampler["alphatab_lufs"] as? [String: Double])
        let fromJSON: [String] = knots.map { (Int($0.key)!, $0.value) }.sorted { $0.0 < $1.0 }.map { "\($0.0) \($0.1)" }
        let inCode: [String] = PlaybackLevels.velocityLUFS.map { "\($0.0) \($0.1)" }
        #expect(fromJSON == inCode)
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

    @Test func recordingGainForATargetMatchesTheSharedRule() throws {
        let rows = try #require(v["recording_gain_for_target"] as? [[String: Any]])
        #expect(rows.count > 5)
        for r in rows {
            let lufs = (r["lufs"] as? Double) ?? -.infinity, target = r["target_lufs"] as! Double
            #expect(abs(PlaybackLevels.recordingGainDB(forLUFS: lufs, target: target) - (r["gain_db"] as! Double)) < 1e-6, "\(lufs) to \(target)")
        }
    }

    @Test func bandEstimateMatchesTheSharedRule() throws {
        let cases = try #require(v["band_estimate"] as? [[String: Any]])
        #expect(cases.count > 10)
        for c in cases {
            let notes = (c["notes"] as! [[Double]]).map { PlaybackLevels.EstimateNote(start: $0[0], end: $0[1], velocity: $0[2]) }
            let name = c["name"] as! String
            let e = PlaybackLevels.bandEstimateLUFS(notes)
            if let want = c["estimate_lufs"] as? Double {
                #expect(abs((e ?? .nan) - want) < 1e-6, "\(name)")
            } else {
                #expect(e == nil, "\(name)")
            }
            #expect(abs(PlaybackLevels.recordingTargetLUFS(forEstimate: e) - (c["target_lufs"] as! Double)) < 1e-6, "\(name)")
        }
    }

    /// The same estimate from the notes ScoreKit reads from each score.
    @Test func bandEstimateFromTheScoreModel() throws {
        let scores = try #require(v["band_estimate_scores"] as? [[String: Any]])
        let root = try #require(repoRoot())
        #expect(scores.count == 2)
        for c in scores {
            let path = c["path"] as! String
            let score = try MusicXMLParser.parse(url: root.appending(path: path))
            let notes = PlaybackLevels.estimateNotes(score)
            let e = try #require(PlaybackLevels.bandEstimateLUFS(notes))
            print("LEVELS band estimate \(path): \(notes.count) notes, \(e) LUFS")
            #expect(abs(e - (c["estimate_lufs"] as! Double)) < 0.01, "\(path)")
            #expect(abs(PlaybackLevels.recordingTargetLUFS(for: score) - (c["target_lufs"] as! Double)) < 0.01, "\(path)")
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
@Suite(.serialized, .tags(.slow), .enabled(if: goldenDir() != nil && capturedRecording() != nil))
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

    /// The golden arrangement's recording target is its band estimate: what Windows measures it at.
    @Test func goldenTargetIsTheBandsLoudness() throws {
        let target = PlaybackLevels.recordingTargetLUFS(for: score)
        print("LEVELS golden recording target \(target) LUFS")
        // the offset is fitted on two arrangements: the golden's estimate is 0.22 LU under what Windows measures
        #expect(abs(target - PlaybackLevels.bandArrangementLUFS) < 0.25)
        // sounds/playback_levels.py --calibrate with the sounds-2026.09.30 pack: -14.72, against -14.50 measured.
        #expect(abs(target - (-14.72)) < 0.01)
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
        #expect(abs(lufs - e.recordingTargetLUFS) < 0.5)
        #expect(buf.peak <= OutputStageKernel.ceiling)
    }

    /// Quiet, loud and mono recordings all play at the target (or as close as the boost cap allows),
    /// and the limiter catches the boost.
    @Test(arguments: [(-8.0, false), (8.0, false), (-6.0, true), (6.0, true)])
    func anyRecordingPlaysAtTheTarget(gainDB: Double, mono: Bool) throws {
        let url = try variant(seconds: 60, mono: mono, gainDB: gainDB)
        defer { try? FileManager.default.removeItem(at: url) }
        let e = try engine(url)
        let buf = try e.renderOriginal(fromBeat: 0, seconds: 60)
        let lufs = LoudnessMeter.integrated(buf)
        print("LEVELS variant \(gainDB) dB mono \(mono): file \(e.originalLUFS ?? .nan) LUFS, gain \(e.originalGainDB) dB, played \(lufs) LUFS, peak \(dB(buf.peak)) dBFS")
        // at the target, unless the +12 dB cap stops a quiet file short of it
        let file = try #require(e.originalLUFS)
        let want = file + PlaybackLevels.recordingGainDB(forLUFS: file, target: e.recordingTargetLUFS)
        #expect(abs(lufs - want) < 0.5, "a mono file plays from both speakers at full level")
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
}
