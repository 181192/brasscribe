import Foundation

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
    /// The original recording plays at this integrated loudness: a whole arrangement from the band.
    public static let recordingTargetLUFS = -16.0
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

    /// Gain that brings a recording measured at `lufs` (integrated, whole file) to the target;
    /// 0 for silence.
    public static func recordingGainDB(forLUFS lufs: Double) -> Double {
        guard lufs.isFinite else { return 0 }
        return max(-recordingMaxCutDB, min(recordingMaxBoostDB, recordingTargetLUFS - lufs))
    }
}
