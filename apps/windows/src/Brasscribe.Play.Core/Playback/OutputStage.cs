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

    /// <summary>The recording's target when there is no arrangement, or it has no pitched note.</summary>
    public const double RecordingFallbackLufs = -16.0;

    /// <summary>The recording's target follows the arrangement's band estimate within these bounds.</summary>
    public const double RecordingMinTargetLufs = -20.0, RecordingMaxTargetLufs = -10.0;
    public const double RecordingMaxBoostDb = 12.0;
    public const double RecordingMaxCutDb = 30.0;

    /// <summary>recording.band_estimate.offset_db: fitted on the golden arrangement, checked on the full-band phrase.</summary>
    public const double BandEstimateOffsetDb = -1.2;

    /// <summary>
    /// dynamics.sampler_velocity.alphatab_lufs: the pitched parts of the full-band phrase through
    /// alphaSynth at each velocity, the L(v) of the band estimate.
    /// </summary>
    public static readonly (int Velocity, double Lufs)[] VelocityLufs =
        [(15, -46.63), (31, -40.33), (47, -36.71), (63, -28.36), (79, -24.72), (95, -22.25), (111, -17.04), (127, -15.87)];

    /// <summary>dynamics.velocity: each mark's velocity by MusicXML element name (alphaTab's rules).</summary>
    public static readonly IReadOnlyDictionary<string, int> DynamicsVelocity = new Dictionary<string, int>
    {
        ["pppppp"] = 3, ["ppppp"] = 5, ["pppp"] = 10, ["ppp"] = 15, ["pp"] = 31, ["p"] = 47, ["mp"] = 63, ["mf"] = 79,
        ["f"] = 95, ["ff"] = 111, ["fff"] = 127, ["ffff"] = 127, ["fffff"] = 127, ["ffffff"] = 127,
        ["sf"] = 111, ["sfz"] = 111, ["fz"] = 111, ["sfp"] = 111, ["sfpp"] = 111, ["sfzp"] = 111,
        ["fp"] = 95, ["rf"] = 95, ["rfz"] = 95, ["sffz"] = 95, ["pf"] = 87, ["n"] = 1,
    };

    /// <summary>The metronome click's peak after the output.</summary>
    public const double MetronomeClickPeakDbfs = -10.0;

    /// <summary>L(v): the table, linear between its knots, 20·log10(v/lowest) under the lowest, flat over the highest.</summary>
    public static double VelocityLoudness(double v)
    {
        var k = VelocityLufs;
        if (v <= k[0].Velocity) return k[0].Lufs + 20 * Math.Log10(Math.Max(v, 1e-9) / k[0].Velocity);
        for (int i = 1; i < k.Length; i++)
            if (v <= k[i].Velocity)
                return k[i - 1].Lufs + (k[i].Lufs - k[i - 1].Lufs) * (v - k[i - 1].Velocity) / (k[i].Velocity - k[i - 1].Velocity);
        return k[^1].Lufs;
    }

    /// <summary>
    /// Estimated integrated loudness of the band playing an arrangement (recording.band_estimate):
    /// offset + 10·log10(Σ d·10^(L(v)/10) / U) over its pitched notes (start and end in quarter notes,
    /// velocity as played), U the time in which any of them sounds. Null without notes.
    /// </summary>
    public static double? BandEstimateLufs(IEnumerable<(double Start, double End, double Velocity)> notes)
    {
        var ns = notes.Where(n => n.End > n.Start).OrderBy(n => n.Start).ToList();
        if (ns.Count == 0) return null;
        double energy = 0, union = 0, end = double.NegativeInfinity;
        foreach (var (a, b, v) in ns)
        {
            energy += (b - a) * Math.Pow(10, VelocityLoudness(v) / 10);
            if (b > end) { union += b - Math.Max(a, end); end = b; }
        }
        return BandEstimateOffsetDb + 10 * Math.Log10(energy / union);
    }

    /// <summary>The recording's target for an arrangement's band estimate, clamped; the fallback without one.</summary>
    public static double RecordingTargetLufs(double? estimate) =>
        estimate is { } e && double.IsFinite(e) ? Math.Clamp(e, RecordingMinTargetLufs, RecordingMaxTargetLufs) : RecordingFallbackLufs;

    /// <summary>Gain that brings a recording measured at <paramref name="lufs"/> (integrated, whole file) to <paramref name="targetLufs"/>; 0 for silence.</summary>
    public static double RecordingGainDb(double lufs, double targetLufs = RecordingFallbackLufs) =>
        double.IsFinite(lufs) ? Math.Clamp(targetLufs - lufs, -RecordingMaxCutDb, RecordingMaxBoostDb) : 0;

    /// <summary>
    /// The media player's volume for a recording measured at <paramref name="lufs"/>. Windows' media
    /// player can only turn down (volume 0–1), so a recording quieter than the target keeps its level.
    /// </summary>
    public static double RecordingVolume(double lufs, double targetLufs = RecordingFallbackLufs) =>
        Math.Min(1, Math.Pow(10, RecordingGainDb(lufs, targetLufs) / 20));
}

/// <summary>
/// Level-matches the original recording to the band: the recording is measured once, as a whole,
/// when it is opened, and plays at the loudness the band plays the loaded arrangement at
/// (<see cref="PlaybackLevels.BandEstimateLufs"/>). The score player reports each arrangement it
/// loads (<see cref="SetArrangement"/>); the last measured recording's volume follows, in either order.
/// </summary>
public static class RecordingLevel
{
    private static readonly object Gate = new();
    private static Services.IOriginalPlayer? _player;
    private static double _lufs = double.NegativeInfinity;
    private static double _target = PlaybackLevels.RecordingFallbackLufs;

    /// <summary>The recording's target for the loaded arrangement (the fallback before one loads).</summary>
    public static double TargetLufs { get { lock (Gate) return _target; } }

    /// <summary>
    /// Measures <paramref name="wavPath"/> (the decoded copy of the recording) off the UI thread and
    /// sets the player's volume, so the recording plays at <see cref="TargetLufs"/> (or as close as a
    /// volume of at most 1 allows). Returns the measured loudness, or null when the file cannot be
    /// read (the volume is then left alone).
    /// </summary>
    public static async Task<double?> ApplyAsync(Services.IOriginalPlayer player, string wavPath)
    {
        double lufs;
        try { lufs = await Task.Run(() => LoudnessMeter.IntegratedWav(wavPath)).ConfigureAwait(true); }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException) { return null; }
        double target;
        lock (Gate)
        {
            (_player, _lufs) = (player, lufs);
            target = _target;
        }
        player.Volume = PlaybackLevels.RecordingVolume(lufs, target);
        return lufs;
    }

    /// <summary>
    /// The arrangement now loaded has this band estimate (null: none, or no pitched note). The target
    /// moves to it, and the last measured recording's volume follows. Returns the new target.
    /// </summary>
    public static double SetArrangement(double? bandEstimateLufs)
    {
        Services.IOriginalPlayer? player;
        double lufs, target = PlaybackLevels.RecordingTargetLufs(bandEstimateLufs);
        lock (Gate)
        {
            _target = target;
            (player, lufs) = (_player, _lufs);
        }
        if (player is not null) player.Volume = PlaybackLevels.RecordingVolume(lufs, target);
        return target;
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
