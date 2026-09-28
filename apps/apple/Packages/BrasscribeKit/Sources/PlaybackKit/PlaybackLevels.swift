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
    /// A whole arrangement played with its dynamics: the Mikkel golden score as Windows plays it.
    public static let bandArrangementLUFS = -11.8
    /// Make-up gain on the band before the limiter, measured for this app's band path.
    public static let bandGainDB = 26.0
    /// The original recording plays at the loudness the band plays the arrangement at
    /// (`bandEstimateLUFS`), clamped to this range; at the fallback without an arrangement.
    public static let recordingFallbackLUFS = -16.0
    public static let recordingMinTargetLUFS = -20.0
    public static let recordingMaxTargetLUFS = -10.0
    /// recording.band_estimate.offset_db: fitted on the golden arrangement, checked on the full-band phrase.
    public static let bandEstimateOffsetDB = -1.2
    /// dynamics.sampler_velocity.alphatab_lufs: (velocity, LUFS of the phrase's pitched parts on alphaSynth).
    public static let velocityLUFS: [(Int, Double)] = [
        (15, -46.63), (31, -40.33), (47, -36.71), (63, -28.36), (79, -24.72), (95, -22.25), (111, -17.04), (127, -15.87),
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
        (1, 8), (3, 15), (5, 19), (10, 27), (15, 33), (31, 47), (47, 55), (63, 65), (79, 77), (87, 81), (95, 89), (111, 99), (127, 101),
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
