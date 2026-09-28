import Foundation

/// The loudness every Play app plays at: sounds/playback-levels.json, which the tests check these
/// against (docs/research/12-band-sound.md §11).
public enum PlaybackLevels {
    /// Soft limiter: linear up to the threshold, tanh towards the ceiling above it.
    public static let limiterThreshold = 0.8
    public static let limiterCeiling = 0.98
    /// The full-band test phrase lands here (integrated LUFS) through the band stage.
    public static let bandPhraseLUFS = -12.0
    /// Make-up gain on the band before the limiter, measured for this app's band path.
    public static let bandGainDB = 26.0
    /// The original recording plays at this integrated loudness: a whole arrangement from the band.
    public static let recordingTargetLUFS = -16.0
    public static let recordingMaxBoostDB = 12.0
    public static let recordingMaxCutDB = 30.0
    /// The metronome click's peak after the output.
    public static let metronomeClickPeakDBFS = -10.0

    /// Gain that brings a recording measured at `lufs` (integrated, whole file) to the target;
    /// 0 for silence.
    public static func recordingGainDB(forLUFS lufs: Double) -> Double {
        guard lufs.isFinite else { return 0 }
        return max(-recordingMaxCutDB, min(recordingMaxBoostDB, recordingTargetLUFS - lufs))
    }
}
