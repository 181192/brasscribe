import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

private func dB(_ x: Float) -> Double { 20 * log10(Double(max(x, 1e-9))) }

/// The score's dynamics play at alphaSynth's levels on AVAudioUnitSampler (playback-levels.json
/// dynamics.sampler_velocity).
@Test func samplerVelocityFollowsTheKnots() {
    for percussion in [false, true] {
        let knots = percussion ? PlaybackLevels.samplerVelocityPercussion : PlaybackLevels.samplerVelocityPitched
        for (v, want) in knots { #expect(PlaybackLevels.samplerVelocity(v, percussion: percussion) == want) }
        var last = 0
        for v in 1...127 {
            let s = PlaybackLevels.samplerVelocity(v, percussion: percussion)
            #expect((1...127).contains(s) && s >= last, "monotonic at \(v)")
            last = s
        }
    }
    // linear between knots: halfway from mp (63 → 60) to mf (79 → 72)
    #expect(PlaybackLevels.samplerVelocity(71, percussion: false) == 66)
}

extension Phrase {
    init(notes: [String: [(Double, Double, UInt8, UInt8)]], names: [String]) { self.notes = notes; self.names = names }

    /// The same phrase with every note at one velocity.
    func at(velocity v: Int) -> Phrase { Phrase(notes: notes.mapValues { $0.map { ($0.0, $0.1, $0.2, UInt8(v)) } }, names: names) }

    /// The phrase as the engine's sequence plays it: every velocity through the sampler remap.
    var remapped: Phrase {
        var out = notes
        for (name, list) in notes {
            out[name] = list.map { ($0.0, $0.1, $0.2, UInt8(PlaybackLevels.samplerVelocity(Int($0.3), percussion: name == "Percussion"))) }
        }
        return Phrase(notes: out, names: names)
    }
}

/// The full-band phrase's pitched parts at each dynamic, under the band gain so nothing reaches the
/// limiter, against the same phrase through alphaSynth 12 dB under its gain
/// (dynamics.sampler_velocity.alphatab_lufs).
@Suite(.serialized, .tags(.slow), .enabled(if: bandPhrase() != nil && bandSoundFont() != nil && outputStageVectors() != nil))
struct DynamicsLevelTests {
    let phrase: Phrase
    let score: Score
    let reference: [String: Double]

    init() throws {
        phrase = try Phrase(try #require(bandPhrase()))
        score = try phrase.score()
        let levels = try #require(outputStageVectors()?["levels"] as? [String: Any])
        let sampler = try #require((levels["dynamics"] as? [String: Any])?["sampler_velocity"] as? [String: Any])
        reference = try #require(sampler["alphatab_lufs"] as? [String: Double])
    }

    func pitchedLUFS(velocity v: Int) throws -> Double {
        withTheBand(); var bank = SoundBank.locate(bundle: .main)
        withTheBand(); bank.band = try #require(BandSounds.locateBand(in: BandSounds.candidates(bundle: .main), files: ["brasscribe-band-16bit.sf2"]).0)
        let e = try PlaybackEngine(score: score, soundBank: bank, roomIR: nil, offlineFormat: PlaybackEngine.offlineFormat())
        // 18 dB down, so even the uncorrected ff stays under the limiter; the reference is 12 dB down
        e.outputGainDB = PlaybackLevels.bandGainDB - 18
        let buf = try phrase.at(velocity: v).render(e, score: score, only: Set(phrase.names.filter { $0 != "Percussion" }))
        #expect(buf.peak < OutputStageKernel.threshold, "below the limiter")
        return LoudnessMeter.integrated(buf) + 6
    }

    /// The sampler's own curve, for fitting dynamics.sampler_velocity.apple_pitched after a sound pack change:
    /// the phrase's pitched parts at raw sampler velocities, on the scale of `alphatab_lufs`.
    /// Runs only when SCRIBE_KNOTS=1.
    @Test(.enabled(if: ProcessInfo.processInfo.environment["SCRIBE_KNOTS"] == "1")) func samplerCurve() throws {
        for v in stride(from: 1, through: 127, by: 2) {
            print(String(format: "SAMPLER %d %.2f", v, try pitchedLUFS(velocity: v)))
        }
    }

    /// Each part of the full-band phrase alone at velocity 80, hall off, for comparing the part balance
    /// with alphaSynth's (RenderHarnessTests.Measure_part_balance in the Windows tests). Runs only when
    /// SCRIBE_KNOTS=1.
    @Test(.enabled(if: ProcessInfo.processInfo.environment["SCRIBE_KNOTS"] == "1")) func partBalance() throws {
        withTheBand(); var bank = SoundBank.locate(bundle: .main)
        withTheBand(); bank.band = try #require(BandSounds.locateBand(in: BandSounds.candidates(bundle: .main), files: ["brasscribe-band-16bit.sf2"]).0)
        for name in phrase.names {
            let e = try PlaybackEngine(score: score, soundBank: bank, roomIR: nil, offlineFormat: PlaybackEngine.offlineFormat())
            e.roomOn = false
            e.outputGainDB = PlaybackLevels.bandGainDB - 18
            let buf = try phrase.at(velocity: 80).render(e, score: score, only: [name])
            print(String(format: "BALANCE %@\t%.2f", name, LoudnessMeter.integrated(buf)))
        }
    }

    /// The remap keeps the band calibration: the full-band phrase, played at the velocities the
    /// sequence would send, still lands on the shared phrase target.
    @Test func remappedPhraseStaysOnTheTarget() throws {
        withTheBand(); var bank = SoundBank.locate(bundle: .main)
        withTheBand(); bank.band = try #require(BandSounds.locateBand(in: BandSounds.candidates(bundle: .main), files: ["brasscribe-band-16bit.sf2"]).0)
        let e = try PlaybackEngine(score: score, soundBank: bank, roomIR: nil, offlineFormat: PlaybackEngine.offlineFormat())
        let buf = try phrase.remapped.render(e, score: score)
        let lufs = LoudnessMeter.integrated(buf)
        print("LEVELS remapped full band phrase \(lufs) LUFS, peak \(dB(buf.peak)) dBFS")
        #expect(abs(lufs - PlaybackLevels.windowsPhraseLUFS) < PlaybackLevels.playerToleranceLU, "where Windows plays the phrase")
        #expect(buf.peak <= OutputStageKernel.ceiling)
        // without the hall: the dry room gain keeps the level (band.dry_room_gain_db)
        let dry = try PlaybackEngine(score: score, soundBank: bank, roomIR: nil, offlineFormat: PlaybackEngine.offlineFormat())
        dry.roomOn = false
        let dryLUFS = LoudnessMeter.integrated(try phrase.remapped.render(dry, score: score))
        print("LEVELS remapped full band phrase, hall off \(dryLUFS) LUFS")
        #expect(abs(dryLUFS - lufs) < 0.6)
    }

    /// Each dynamic lands within 1.5 dB of alphaSynth's level, and pp, mf and ff sit where they do
    /// there relative to f, within 2 dB.
    @Test func dynamicsMatchAlphaSynth() throws {
        let marks = ["pp", "p", "mp", "mf", "f", "ff"]
        var got: [String: Double] = [:]
        for m in marks {
            let v = Dynamics.velocity(mark: m)
            let want = try #require(reference["\(v)"])
            let raw = try pitchedLUFS(velocity: v)
            let lufs = try pitchedLUFS(velocity: PlaybackLevels.samplerVelocity(v, percussion: false))
            got[m] = lufs
            print(String(format: "DYNAMICS %@ velocity %d: alphaSynth %.2f, sampler uncorrected %.2f (%+.2f), corrected %.2f (%+.2f) LUFS",
                         m, v, want, raw, raw - want, lufs, lufs - want))
            // What was measured, the limit and the system are all said: the sampler that plays is the system's own
            // and differs between versions of macOS, so a new runner image can move a level with no change here.
            #expect(abs(lufs - want) < 1.5,
                    "\(m): \(String(format: "%.2f", lufs)) LUFS against alphaSynth's \(String(format: "%.2f", want)) (\(String(format: "%+.2f", lufs - want)) dB, 1.5 allowed) on macOS \(ProcessInfo.processInfo.operatingSystemVersionString)")
        }
        let f = try #require(got["f"]), fRef = try #require(reference["\(Dynamics.velocity(mark: "f"))"])
        for m in ["pp", "mf", "ff"] {
            let rel = got[m]! - f, relRef = reference["\(Dynamics.velocity(mark: m))"]! - fRef
            #expect(abs(rel - relRef) < 2, "\(m) relative to f: \(rel) vs \(relRef)")
        }
    }
}

/// A whole arrangement played with its dynamics lands where Windows plays it, within the tolerance the shared
/// levels give an app's own player. Old Hundredth is in git, so this runs wherever the band SoundFont is (CI
/// fetches it); the golden is on the machines that have `data/golden`.
@Suite(.serialized, .tags(.slow), .enabled(if: bandSoundFont() != nil)) struct ArrangementLevelTests {
    private func level(of dir: URL, _ name: String, hall: Bool = true) throws -> Double {
        let score = try MusicXMLParser.parse(url: dir.appending(path: "brass-band.musicxml"))
        let composition = try Composition.decode(Data(contentsOf: dir.appending(path: "composition.json")))
        withTheBand()
        let e = try PlaybackEngine(score: score, tempoMap: composition.tempoMap, soundBank: .locate(bundle: .main), roomIR: nil,
                                   offlineFormat: PlaybackEngine.offlineFormat())
        e.roomOn = hall
        let buf = try e.renderScore(fromBeat: 0, beats: Double(score.endTick) / Double(Score.ticksPerQuarter))
        let lufs = LoudnessMeter.integrated(buf)
        print("LEVELS \(name) arrangement\(hall ? "" : ", hall off") \(lufs) LUFS, peak \(dB(buf.peak)) dBFS, \(ProcessInfo.processInfo.operatingSystemVersionString)")
        #expect(buf.peak <= OutputStageKernel.ceiling)
        return lufs
    }

    /// Where Apple itself plays Old Hundredth, on the Mac that runs this for every pull request (macOS 26). The
    /// line the test prints shows a level on the move before it is far enough to fail.
    ///
    /// Another Mac can read differently for the same code and sounds, because the players are the system's own
    /// (AVAudioUnitSampler, AVAudioEnvironmentNode) and change with the system: macOS 27.0 reads 0.26 LU higher
    /// with the hall (−15.62) and 1.3 LU higher without it (−14.02 against −15.34). The render format is fixed
    /// (44.1 kHz stereo, offline), so it is not the device. Hence 0.5 LU and not less.
    ///
    /// Moved only on purpose, together with `band.gain_db.apple`, after measuring Windows again
    /// (docs/shared/dev/release.md §10).
    static let appleOldHundredthLUFS = -15.88
    static let appleDriftLU = 0.5

    @Test func oldHundredthMatchesTheOtherAppsAndHoldsItsOwnLevel() throws {
        let dir = try #require(repoRoot()).appending(path: "apps/fixtures/old-hundredth")
        let lufs = try level(of: dir, "Old Hundredth")
        // Against Windows: different synths, so the players' shared tolerance.
        #expect(abs(lufs - PlaybackLevels.oldHundredthLUFS) <= PlaybackLevels.playerToleranceLU)
        // Against Apple itself: a change to the gain, the limiter, the velocity curve or the seats shows here.
        #expect(abs(lufs - Self.appleOldHundredthLUFS) <= Self.appleDriftLU,
                "Apple plays Old Hundredth at \(lufs) LUFS; it was \(Self.appleOldHundredthLUFS)")
        _ = try level(of: dir, "Old Hundredth", hall: false)  // printed, for the record: it varies most between systems
    }

    @Test(.enabled(if: goldenDir() != nil)) func goldenArrangementMatchesTheOtherApps() throws {
        let lufs = try level(of: try #require(goldenDir()), "golden")
        #expect(abs(lufs - PlaybackLevels.bandArrangementLUFS) <= PlaybackLevels.playerToleranceLU)
    }
}
