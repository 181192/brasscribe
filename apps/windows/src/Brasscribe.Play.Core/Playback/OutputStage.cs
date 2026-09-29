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
    public const double BandGainDb = 5.0;

    /// <summary>metronome.gain_db.windows: the click's volume, through the band stage.</summary>
    public const double MetronomeGainDb = -1.0;

    /// <summary>The recording's target when there is no arrangement, or it has no pitched note.</summary>
    public const double RecordingFallbackLufs = -16.0;

    /// <summary>The recording's target follows the arrangement's band estimate within these bounds.</summary>
    public const double RecordingMinTargetLufs = -20.0, RecordingMaxTargetLufs = -10.0;
    public const double RecordingMaxBoostDb = 12.0;
    public const double RecordingMaxCutDb = 30.0;

    /// <summary>recording.band_estimate.offset_db: fitted on the golden arrangement, checked on the full-band phrase.</summary>
    public const double BandEstimateOffsetDb = -0.17;

    /// <summary>
    /// dynamics.sampler_velocity.alphatab_lufs: the pitched parts of the full-band phrase through
    /// alphaSynth at each velocity, the L(v) of the band estimate.
    /// </summary>
    public static readonly (int Velocity, double Lufs)[] VelocityLufs =
        [(15, -44.51), (31, -38.20), (47, -34.58), (63, -28.61), (79, -25.39), (95, -23.36), (111, -17.66), (127, -16.49)];

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
    /// The media player's volume for a recording measured at <paramref name="lufs"/>: the cut, as the media player can
    /// only turn down (volume 0–1). A boost is made by <see cref="RecordingBoost"/> instead, and the volume stays at 1.
    /// </summary>
    public static double RecordingVolume(double lufs, double targetLufs = RecordingFallbackLufs) =>
        Math.Min(1, Math.Pow(10, RecordingGainDb(lufs, targetLufs) / 20));
}

/// <summary>
/// A quiet recording brought up to its target: a copy of the decoded recording with the gain and then the output
/// stage's soft limiter (<see cref="OutputStage.Limit"/>), so the boost cannot clip, as the other Play apps apply it
/// on the fly. Windows' media player cannot go above volume 1, so it plays this copy instead.
/// </summary>
public static class RecordingBoost
{
    /// <summary>Boosts smaller than this (dB) are not worth a copy.</summary>
    public const double MinBoostDb = 0.1;

    /// <summary>
    /// The boosted copy of <paramref name="wavPath"/> for <paramref name="gainDb"/> (rounded to 0.1 dB), next to it;
    /// written once and reused. Throws IOException or InvalidDataException when the file can't be read or written.
    /// </summary>
    public static string Prepare(string wavPath, double gainDb)
    {
        double rounded = Math.Round(gainDb, 1);
        string path = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(wavPath))!,
            $"{Path.GetFileNameWithoutExtension(wavPath)}.boost{rounded.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)}.wav");
        if (File.Exists(path) && File.GetLastWriteTimeUtc(path) >= File.GetLastWriteTimeUtc(wavPath)) return path;
        string temp = path + ".part";
        Render(wavPath, temp, rounded);
        File.Move(temp, path, overwrite: true);
        return path;
    }

    /// <summary>Writes <paramref name="wavPath"/> with <paramref name="gainDb"/> and the soft limiter as a 32-bit float WAV.</summary>
    public static void Render(string wavPath, string outPath, double gainDb)
    {
        float gain = (float)Math.Pow(10, gainDb / 20);
        using var w = new BinaryWriter(File.Create(outPath));
        long dataStart = 0, frames = 0;
        int channels = 0;
        var buffer = new byte[4 * 8192 * 2];
        LoudnessMeter.ReadWav(wavPath, (rate, ch) =>
        {
            channels = ch;
            w.Write("RIFF"u8); w.Write(0); w.Write("WAVE"u8);
            w.Write("fmt "u8); w.Write(16); w.Write((short)3); w.Write((short)ch); w.Write(rate); w.Write(rate * ch * 4); w.Write((short)(ch * 4)); w.Write((short)32);
            w.Write("data"u8); w.Write(0);
            dataStart = w.BaseStream.Position;
        }, samples =>
        {
            if (buffer.Length < samples.Length * 4) buffer = new byte[samples.Length * 4];
            for (int i = 0; i < samples.Length; i++)
                System.Buffers.Binary.BinaryPrimitives.WriteSingleLittleEndian(buffer.AsSpan(i * 4), OutputStage.Limit(samples[i] * gain));
            w.Write(buffer, 0, samples.Length * 4);
            frames += samples.Length;
        });
        long bytes = frames * 4;
        w.Seek(4, SeekOrigin.Begin); w.Write((int)(36 + bytes));
        w.Seek((int)dataStart - 4, SeekOrigin.Begin); w.Write((int)bytes);
    }
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
    private static string? _wav;
    private static double _lufs = double.NegativeInfinity;
    private static double _target = PlaybackLevels.RecordingFallbackLufs;
    private static int _version;
    private static Task _settled = Task.CompletedTask;

    /// <summary>The recording's target for the loaded arrangement (the fallback before one loads).</summary>
    public static double TargetLufs { get { lock (Gate) return _target; } }

    /// <summary>The last level change, done: a boosted copy written and handed to the player.</summary>
    public static Task Settled { get { lock (Gate) return _settled; } }

    /// <summary>
    /// Measures <paramref name="wavPath"/> (the decoded copy of the recording) off the UI thread and levels it, so the
    /// recording plays at <see cref="TargetLufs"/>: a loud one through the player's volume, a quiet one from a boosted
    /// copy (<see cref="RecordingBoost"/>) when the player can play one. Returns the measured loudness, or null when the
    /// file cannot be read (the level is then left alone).
    /// </summary>
    public static async Task<double?> ApplyAsync(Services.IOriginalPlayer player, string wavPath)
    {
        double lufs;
        try { lufs = await Task.Run(() => LoudnessMeter.IntegratedWav(wavPath)).ConfigureAwait(true); }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException) { return null; }
        Task level;
        lock (Gate)
        {
            (_player, _lufs, _wav) = (player, lufs, wavPath);
            _settled = level = LevelAsync(player, wavPath, lufs, _target, ++_version);
        }
        await level.ConfigureAwait(true);
        return lufs;
    }

    /// <summary>
    /// The arrangement now loaded has this band estimate (null: none, or no pitched note). The target
    /// moves to it, and the last measured recording's level follows (see <see cref="Settled"/>). Returns the new target.
    /// </summary>
    public static double SetArrangement(double? bandEstimateLufs)
    {
        double target = PlaybackLevels.RecordingTargetLufs(bandEstimateLufs);
        lock (Gate)
        {
            _target = target;
            if (_player is { } player && _wav is { } wav) _settled = LevelAsync(player, wav, _lufs, target, ++_version);
        }
        return target;
    }

    /// <summary>
    /// Sets the level for a gain: a cut (or no change) is the volume, at once; a boost is a copy written off the UI
    /// thread, then played at volume 1. A newer level that started meanwhile wins.
    /// </summary>
    private static async Task LevelAsync(Services.IOriginalPlayer player, string wav, double lufs, double target, int version)
    {
        double gain = PlaybackLevels.RecordingGainDb(lufs, target);
        if (gain < RecordingBoost.MinBoostDb || !player.CanUseAudio)
        {
            player.UseAudio(null);
            player.Volume = PlaybackLevels.RecordingVolume(lufs, target);
            return;
        }
        string boosted;
        try { boosted = await Task.Run(() => RecordingBoost.Prepare(wav, gain)).ConfigureAwait(true); }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException)
        {
            player.UseAudio(null);
            player.Volume = 1; // as loud as the media player goes
            return;
        }
        lock (Gate) if (version != _version) return;
        player.Volume = 1;
        player.UseAudio(boosted);
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
