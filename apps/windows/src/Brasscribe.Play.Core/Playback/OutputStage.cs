namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// The loudness every Play app plays at: sounds/playback-levels.json, which the tests check these
/// against (docs/research/12-band-sound.md §11).
/// </summary>
public static class PlaybackLevels
{
    /// <summary>The full-band test phrase lands here (integrated LUFS) through the band stage.</summary>
    public const double BandPhraseLufs = -12.0;

    /// <summary>Make-up gain on the band before the limiter, measured for alphaSynth with the band SoundFont.</summary>
    public const double BandGainDb = 4.0;

    /// <summary>The original recording plays at this integrated loudness: a whole arrangement from the band.</summary>
    public const double RecordingTargetLufs = -16.0;
    public const double RecordingMaxBoostDb = 12.0;
    public const double RecordingMaxCutDb = 30.0;

    /// <summary>The metronome click's peak after the output.</summary>
    public const double MetronomeClickPeakDbfs = -10.0;

    /// <summary>Gain that brings a recording measured at <paramref name="lufs"/> (integrated, whole file) to the target; 0 for silence.</summary>
    public static double RecordingGainDb(double lufs) =>
        double.IsFinite(lufs) ? Math.Clamp(RecordingTargetLufs - lufs, -RecordingMaxCutDb, RecordingMaxBoostDb) : 0;

    /// <summary>
    /// The media player's volume for a recording measured at <paramref name="lufs"/>. Windows' media
    /// player can only turn down (volume 0–1), so a recording quieter than the target keeps its level.
    /// </summary>
    public static double RecordingVolume(double lufs) => Math.Min(1, Math.Pow(10, RecordingGainDb(lufs) / 20));
}

/// <summary>Level-matches the original recording to the band: measured once, as a whole, when it is opened.</summary>
public static class RecordingLevel
{
    /// <summary>
    /// Measures <paramref name="wavPath"/> (the decoded copy of the recording) off the UI thread and
    /// sets the player's volume, so the recording plays at <see cref="PlaybackLevels.RecordingTargetLufs"/>
    /// (or as close as a volume of at most 1 allows). Returns the measured loudness, or null when the
    /// file cannot be read (the volume is then left alone).
    /// </summary>
    public static async Task<double?> ApplyAsync(Services.IOriginalPlayer player, string wavPath)
    {
        double lufs;
        try { lufs = await Task.Run(() => LoudnessMeter.IntegratedWav(wavPath)).ConfigureAwait(true); }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException) { return null; }
        player.Volume = PlaybackLevels.RecordingVolume(lufs);
        return lufs;
    }
}

/// <summary>
/// The output stage: make-up gain, then a memoryless soft limiter, the same curve on every Play app.
/// Linear up to <see cref="Threshold"/>, tanh towards <see cref="Ceiling"/> above it, so nothing
/// ever clips. It has no attack or release: it cannot pump when the music stops or fades, and below
/// the threshold every part keeps its level, so mute and solo keep the balance.
/// </summary>
public static class OutputStage
{
    /// <summary>Where the limiter starts to bend (−1.9 dBFS).</summary>
    public const float Threshold = 0.8f;

    /// <summary>What the limiter never reaches (−0.18 dBFS).</summary>
    public const float Ceiling = 0.98f;

    /// <summary>The band's make-up gain as a factor.</summary>
    public static readonly float BandGain = (float)Math.Pow(10, PlaybackLevels.BandGainDb / 20);

    /// <summary>The limiter curve for one sample (gain already applied).</summary>
    public static float Limit(float x)
    {
        float a = Math.Abs(x);
        if (a <= Threshold) return x;
        const float knee = Ceiling - Threshold;
        return MathF.CopySign(Threshold + knee * MathF.Tanh((a - Threshold) / knee), x);
    }
}
