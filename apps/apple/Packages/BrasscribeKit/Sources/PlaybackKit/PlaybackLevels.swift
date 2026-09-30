import Foundation
import ScoreKit

/// The loudness every Play app plays at: sounds/playback-levels.json, which the tests check these
/// against (docs/research/12-band-sound.md §11).
public enum PlaybackLevels {
    /// Soft limiter: linear up to the threshold, tanh towards the ceiling above it.
    public static let limiterThreshold = 0.8
    public static let limiterCeiling = 0.98
    /// The full-band test phrase lands here (integrated LUFS) through the band stage.
    public static let bandPhraseLUFS = -12.0
    /// The full-band phrase as Windows plays it (alphaSynth), and how far Apple's may be from it: Apple's band gain
    /// is fitted on whole arrangements, where its phrase-to-arrangement ratio is 1.9 LU off alphaSynth's
    /// (docs/research/12-band-sound.md §14).
    public static let windowsPhraseLUFS = -12.80
    public static let phraseToleranceLU = 1.1
    /// A whole arrangement played with its dynamics: the Mikkel golden score as Windows plays it.
    public static let bandArrangementLUFS = -14.50
    /// Make-up gain on the band before the limiter: fitted so the golden and Old Hundredth land where Windows plays
    /// them (the largest deviation, the golden's, 1 LU).
    public static let bandGainDB = 29.55
    /// Added to the make-up gain when "Concert hall sound" is off: the hall's share of the band's
    /// loudness, measured on the golden arrangement and Old Hundredth (band.dry_room_gain_db).
    public static let dryRoomGainDB = 6.3
    /// Added to a part's channel gain by its seat (band.apple_seat_trim_db): the environment node's seating (HRTF,
    /// distance) changes the balance against alphaSynth, which plays every part centred.
    public static let appleSeatTrimDB: [String: Double] = [
        "solo-cornets": 0.0, "soprano": 2.9, "repiano": 4.5, "second-cornets": 5.1, "third-cornets": 5.0, "flugel": 1.0,
        "solo-horn": 0.4, "first-horn": 0.3, "second-horn": 0.4, "first-baritone": 1.3, "second-baritone": 1.8, "first-trombone": 3.3,
        "second-trombone": 2.8, "bass-trombone": 1.9, "euphoniums": 0.1, "eb-basses": 3.6, "bb-basses": 3.7, "percussion": 13.8,
    ]
    /// Added to each drum of the kit, by GM key (band.apple_kit_trim_db): AVAudioUnitSampler hardly applies the kit's
    /// zone attenuation, which alphaSynth applies in full, so without it the hi-hats played 16 dB and the ride 28 dB
    /// over alphaSynth's against the kick. Measured drum by drum at every dynamic (sounds/tools/kit_probe.py); a drum
    /// not listed plays at 0.
    public static let appleKitTrimDB: [Int: Double] = [
        35: 3.6, 36: 3.6, 37: -15.9, 38: -6.0, 40: -6.0, 41: -11.9, 42: -16.6, 43: -11.8, 44: -16.6, 45: -5.5, 46: -6.7,
        47: -5.5, 48: -5.5, 49: -11.3, 50: -5.5, 51: -28.2, 52: -24.1, 53: -25.2, 54: -11.9, 55: -21.7, 56: -10.6,
        57: -12.2, 59: -27.7,
    ]

    /// The pop kit (bank 128 program 1) plays MS Basic's own crashes where the band kit has VSCO's
    /// (band.apple_kit_trim_db.pop_kit): its other drums take the band kit's trims.
    public static let applePopKitTrimDB: [Int: Double] = [49: -23.8, 57: -28.3]

    /// A drum's trim in the kit of `program` (0 the band kit, 1 the pop kit).
    public static func kitTrimDB(_ key: Int, program: Int) -> Double? {
        (program == 1 ? applePopKitTrimDB[key] : nil) ?? appleKitTrimDB[key]
    }

    /// The kit's drums in groups whose trims lie within `kitGroupSpanDB`: each group plays on a sampler of its own at
    /// the group's mean trim (AVAudioUnitSampler has one volume for all its MIDI channels), so a score with a kick,
    /// a snare, hi-hats and a crash loads the kit four times. The group of every key, and each group's trim in dB; a
    /// drum without a trim is in the group of 0 dB.
    public static let kitGroupSpanDB = 2.0

    public struct KitGroups: Sendable {
        public var group: [Int: Int]
        public var trimDB: [Double]
        /// The group a drum plays in.
        public func of(_ key: Int) -> Int { group[key] ?? group[-1]! }
    }

    /// The groups of the kit of `program`.
    public static func kitGroups(program: Int) -> KitGroups {
        var members: [[Double]] = []
        var group: [Int: Int] = [:]
        let keys = appleKitTrimDB.keys.map { ($0, kitTrimDB($0, program: program)!) } + [(-1, 0.0)]
        for (key, t) in keys.sorted(by: { ($0.1, $0.0) > ($1.1, $1.0) }) {
            if let top = members.last?.first, top - t <= kitGroupSpanDB {
                members[members.count - 1].append(t)
            } else {
                members.append([t])
            }
            group[key] = members.count - 1
        }
        return KitGroups(group: group, trimDB: members.map { ($0.reduce(0, +) / Double($0.count) * 10).rounded() / 10 })
    }

    /// The original recording plays at the loudness the band plays the arrangement at
    /// (`bandEstimateLUFS`), clamped to this range; at the fallback without an arrangement.
    public static let recordingFallbackLUFS = -16.0
    public static let recordingMinTargetLUFS = -20.0
    public static let recordingMaxTargetLUFS = -10.0
    /// recording.band_estimate.offset_db: fitted on two arrangements (the golden and Old Hundredth).
    public static let bandEstimateOffsetDB = -3.05
    /// dynamics.sampler_velocity.alphatab_lufs: (velocity, LUFS of the phrase's pitched parts on alphaSynth).
    public static let velocityLUFS: [(Int, Double)] = [
        (15, -43.07), (31, -36.77), (47, -33.15), (63, -29.46), (79, -25.98), (95, -22.30), (111, -18.56), (127, -15.32),
    ]
    public static let recordingMaxBoostDB = 12.0
    public static let recordingMaxCutDB = 30.0
    /// The metronome click's peak after the output.
    public static let metronomeClickPeakDBFS = -10.0

    /// AVAudioUnitSampler's velocity correction (dynamics.sampler_velocity): (score velocity, the
    /// velocity the sampler gets) knots, linear between them. The score velocities are alphaTab's, which
    /// alphaSynth plays at amplitude ∝ velocity; the sampler ignores the SoundFont's velocity modulator
    /// and follows a much steeper curve, so uncorrected the table's pp played 7 dB softer than on
    /// Android and Windows and ff 3.4 dB louder. Measured with the full-band test phrase at one velocity
    /// through both engines, below the limiter: pitched parts matched level for level (within 1 dB from
    /// ppp to fff), percussion matched in shape and anchored at velocity 90, because its seat at the
    /// back leaves it about 8 dB under alphaSynth's at every velocity.
    public static let samplerVelocityPitched: [(Int, Int)] = [
        (1, 9), (3, 12), (5, 16), (10, 23), (15, 28), (31, 40), (47, 49), (63, 60), (79, 72), (87, 81), (95, 90), (111, 109), (127, 127),
    ]
    public static let samplerVelocityPercussion: [(Int, Int)] = [
        (1, 1), (3, 15), (5, 21), (10, 30), (15, 36), (31, 52), (47, 64), (63, 75), (79, 83), (87, 88), (95, 92), (111, 100), (127, 107),
    ]

    /// The velocity to send AVAudioUnitSampler for a score velocity (alphaTab's scale).
    public static func samplerVelocity(_ v: Int, percussion: Bool) -> Int {
        let knots = percussion ? samplerVelocityPercussion : samplerVelocityPitched
        guard let first = knots.first, let last = knots.last else { return v }
        if v <= first.0 { return first.1 }
        if v >= last.0 { return last.1 }
        let i = knots.firstIndex { $0.0 >= v }!
        let (x0, y0) = knots[i - 1], (x1, y1) = knots[i]
        return max(1, min(127, Int((Double(y0) + Double(y1 - y0) * Double(v - x0) / Double(x1 - x0)).rounded())))
    }

    /// Gain that brings a recording measured at `lufs` (integrated, whole file) to `target`
    /// (the fallback target when not given); 0 for silence.
    public static func recordingGainDB(forLUFS lufs: Double, target: Double = recordingFallbackLUFS) -> Double {
        guard lufs.isFinite else { return 0 }
        return max(-recordingMaxCutDB, min(recordingMaxBoostDB, target - lufs))
    }

    /// A pitched note for `bandEstimateLUFS`: start and end in quarter notes, the velocity it plays at.
    public struct EstimateNote: Sendable, Equatable {
        public var start: Double
        public var end: Double
        public var velocity: Double
        public init(start: Double, end: Double, velocity: Double) {
            self.start = start
            self.end = end
            self.velocity = velocity
        }
    }

    /// L(v) of the band estimate: `velocityLUFS`, linear between its knots, falling 20·log10(v/lowest)
    /// below the lowest knot and flat above the highest.
    public static func velocityLoudness(_ v: Double) -> Double {
        let first = velocityLUFS[0], last = velocityLUFS[velocityLUFS.count - 1]
        if v <= Double(first.0) { return first.1 + 20 * log10(max(v, 1e-9) / Double(first.0)) }
        for (a, b) in zip(velocityLUFS, velocityLUFS.dropFirst()) where v <= Double(b.0) {
            return a.1 + (b.1 - a.1) * (v - Double(a.0)) / Double(b.0 - a.0)
        }
        return last.1
    }

    /// Estimated integrated LUFS of the band playing an arrangement (recording.band_estimate):
    /// offset + 10·log10(Σ d·10^(L(v)/10) / U) over the pitched notes, U the time in which at least
    /// one of them sounds. Nil without a note of positive length.
    public static func bandEstimateLUFS(_ notes: [EstimateNote]) -> Double? {
        let ns = notes.filter { $0.end > $0.start }
        guard !ns.isEmpty else { return nil }
        let energy = ns.reduce(0.0) { $0 + ($1.end - $1.start) * pow(10, velocityLoudness($1.velocity) / 10) }
        var union = 0.0, end = -Double.infinity
        for n in ns.sorted(by: { ($0.start, $0.end) < ($1.start, $1.end) }) where n.end > end {
            union += n.end - max(n.start, end)
            end = n.end
        }
        return bandEstimateOffsetDB + 10 * log10(energy / union)
    }

    /// The recording's target for an arrangement's band estimate: clamped, the fallback without one.
    public static func recordingTargetLUFS(forEstimate estimate: Double?) -> Double {
        guard let e = estimate, e.isFinite else { return recordingFallbackLUFS }
        return max(recordingMinTargetLUFS, min(recordingMaxTargetLUFS, e))
    }
}

extension PlaybackLevels {
    /// The notes of `score` the band estimate reads: every pitched note of the parts that are not
    /// percussion, in quarter notes, at the velocity the score's dynamics give it (before
    /// `samplerVelocity`). Grace notes are not in the score model; a tied note may stay split, which
    /// does not change the estimate.
    public static func estimateNotes(_ score: Score) -> [EstimateNote] {
        let q = Double(Score.ticksPerQuarter)
        return score.parts.filter { !$0.isPercussion }.flatMap { part in
            part.notes.compactMap { n -> EstimateNote? in
                guard n.midiPitch != nil, !n.isRest, n.durTicks > 0 else { return nil }
                return EstimateNote(start: Double(n.startTick) / q, end: Double(n.endTick) / q, velocity: Double(n.velocity))
            }
        }
    }

    /// The recording's target for `score`: its band estimate, clamped.
    public static func recordingTargetLUFS(for score: Score) -> Double {
        recordingTargetLUFS(forEstimate: bandEstimateLUFS(estimateNotes(score)))
    }
}
