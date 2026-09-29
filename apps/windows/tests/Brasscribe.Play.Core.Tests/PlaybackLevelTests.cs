using System.Text.Json;
using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Playback loudness (sounds/playback-levels.json): the shared limiter curve, recording gain rule
/// and loudness meter (sounds/output-stage-vectors.json), and the band, metronome and recording
/// levels the Windows player lands on.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class PlaybackLevelTests(ITestOutputHelper log)
{
    private static string? Mapping => TestPaths.RepoFile("sounds/mapping.json");
    private static string? Vectors => TestPaths.RepoFile("sounds/output-stage-vectors.json");
    private const string BandSf2 = "data/sounds/band/brasscribe-band-16bit.sf2"; // what the app bundles
    private static string NoGoldenPlayer => TestPaths.Missing($"{BandSf2}, {TestPaths.GoldenMusicXml} or sounds/mapping.json");

    private static double Db(double x) => 20 * Math.Log10(Math.Max(x, 1e-9));

    private static float Peak(float[] x) => x.Length == 0 ? 0 : x.Max(Math.Abs);

    /// <summary>The full-band test phrase through one synth with the app's channel plan and balance.</summary>
    private static float[]? RenderBandPhrase()
    {
        var sf2Path = TestPaths.RepoFile(BandSf2);
        var phrases = TestPaths.RepoFile("data/sounds/phrases/phrases.json");
        if (sf2Path is null || phrases is null || Mapping is null) return null;
        var band = BandSoundFont.Load(Mapping);
        using var doc = JsonDocument.Parse(File.ReadAllText(phrases));
        var parts = doc.RootElement.GetProperty("band").EnumerateObject().ToList();
        var plan = ChannelPlan.ForPlayback(parts.Select((b, i) =>
        {
            var s = band.For(b.Name)!;
            return new ChannelPlan.Part(i, s.Percussion, s.Program, s.GainDb);
        }).ToList());
        var gains = new Dictionary<int, double>();
        var rows = new List<(int, int, int, JsonElement)>();
        for (int i = 0; i < parts.Count; i++)
        {
            var s = band.For(parts[i].Name)!;
            gains[plan[i]] = Math.Pow(10, s.GainDb / 20);
            rows.Add((plan[i], s.Percussion ? 0 : s.Program, s.Bank, parts[i].Value.GetProperty("notes")));
        }
        return PartSoundTests.Render(File.ReadAllBytes(sf2Path), PartSoundTests.Phrase(rows), rows.Max(r => PartSoundTests.End(r.Item4)) + 2.0, gains);
    }

    [SkippableFact]
    public void Constants_match_playback_levels()
    {
        Skip.If(Vectors is null, TestPaths.Missing("sounds/output-stage-vectors.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        var levels = doc.RootElement.GetProperty("levels");
        Assert.Equal(OutputStage.Threshold, levels.GetProperty("limiter").GetProperty("threshold").GetDouble(), 6);
        Assert.Equal(OutputStage.Ceiling, levels.GetProperty("limiter").GetProperty("ceiling").GetDouble(), 6);
        var band = levels.GetProperty("band");
        Assert.Equal(PlaybackLevels.BandPhraseLufs, band.GetProperty("phrase_lufs").GetDouble());
        Assert.Equal(PlaybackLevels.BandGainDb, band.GetProperty("gain_db").GetProperty("windows").GetDouble());
        var rec = levels.GetProperty("recording");
        Assert.Equal(PlaybackLevels.RecordingFallbackLufs, rec.GetProperty("fallback_lufs").GetDouble());
        Assert.Equal(PlaybackLevels.RecordingMinTargetLufs, rec.GetProperty("min_target_lufs").GetDouble());
        Assert.Equal(PlaybackLevels.RecordingMaxTargetLufs, rec.GetProperty("max_target_lufs").GetDouble());
        Assert.Equal(PlaybackLevels.RecordingMaxBoostDb, rec.GetProperty("max_boost_db").GetDouble());
        Assert.Equal(PlaybackLevels.RecordingMaxCutDb, rec.GetProperty("max_cut_db").GetDouble());
        Assert.Equal(PlaybackLevels.BandEstimateOffsetDb, rec.GetProperty("band_estimate").GetProperty("offset_db").GetDouble());
        var table = levels.GetProperty("dynamics").GetProperty("sampler_velocity").GetProperty("alphatab_lufs").EnumerateObject()
            .Select(p => (int.Parse(p.Name), p.Value.GetDouble())).OrderBy(p => p.Item1).ToArray();
        Assert.Equal(table, PlaybackLevels.VelocityLufs.Select(k => (k.Velocity, k.Lufs)).ToArray());
        var velocity = levels.GetProperty("dynamics").GetProperty("velocity").EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetInt32());
        Assert.Equal(velocity.OrderBy(p => p.Key), PlaybackLevels.DynamicsVelocity.OrderBy(p => p.Key));
        // Every mark alphaTab reads has a velocity in the table.
        foreach (var d in Enum.GetNames<AlphaTab.Model.DynamicValue>()) Assert.True(velocity.ContainsKey(d.ToLowerInvariant()), d);
        Assert.Equal(PlaybackLevels.MetronomeClickPeakDbfs, levels.GetProperty("metronome").GetProperty("click_peak_dbfs").GetDouble());
    }

    private static double? NullableDouble(JsonElement e) => e.ValueKind == JsonValueKind.Null ? null : e.GetDouble();

    [SkippableFact]
    public void Band_estimate_and_recording_target_match_the_shared_rule()
    {
        Skip.If(Vectors is null, TestPaths.Missing("sounds/output-stage-vectors.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        int n = 0;
        foreach (var c in doc.RootElement.GetProperty("band_estimate").EnumerateArray())
        {
            var notes = c.GetProperty("notes").EnumerateArray()
                .Select(x => (x[0].GetDouble(), x[1].GetDouble(), x[2].GetDouble())).ToList();
            string name = c.GetProperty("name").GetString()!;
            double? estimate = PlaybackLevels.BandEstimateLufs(notes);
            if (NullableDouble(c.GetProperty("estimate_lufs")) is { } want) Assert.True(Math.Abs(want - estimate!.Value) < 1e-6, $"{name}: {estimate}");
            else Assert.Null(estimate);
            Assert.True(Math.Abs(c.GetProperty("target_lufs").GetDouble() - PlaybackLevels.RecordingTargetLufs(estimate)) < 1e-6, name);
            n++;
        }
        Assert.True(n > 10);
        foreach (var v in doc.RootElement.GetProperty("recording_gain_for_target").EnumerateArray())
        {
            double lufs = NullableDouble(v.GetProperty("lufs")) ?? double.NegativeInfinity;
            Assert.Equal(v.GetProperty("gain_db").GetDouble(), PlaybackLevels.RecordingGainDb(lufs, v.GetProperty("target_lufs").GetDouble()), 6);
        }
    }

    /// <summary>alphaTab's own notes of each vector score (and of the golden, when present) give the shared estimate.</summary>
    [SkippableFact]
    public void Band_estimate_from_alphaTabs_notes_matches_the_shared_scores()
    {
        Skip.If(Vectors is null, TestPaths.Missing("sounds/output-stage-vectors.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        var wrong = new List<string>();
        foreach (var c in doc.RootElement.GetProperty("band_estimate_scores").EnumerateArray())
        {
            string path = c.GetProperty("path").GetString()!;
            var (estimate, notes) = Estimate(TestPaths.RepoFile(path)!);
            double want = c.GetProperty("estimate_lufs").GetDouble();
            log.WriteLine($"{path}: {notes} pitched notes, estimate {estimate:0.000} (shared {want:0.000})");
            if (notes != c.GetProperty("pitched_notes").GetInt32() || Math.Abs(want - estimate!.Value) >= 0.01) wrong.Add(path);
        }
        if (TestPaths.RepoFile(TestPaths.GoldenMusicXml) is { } golden)
        {
            var (estimate, notes) = Estimate(golden);
            log.WriteLine($"golden: {notes} pitched notes, estimate {estimate:0.000}");
            // sounds/playback_levels.py --calibrate: -14.60, against the -14.44 Golden_arrangement_plays_at_the_recording_target measures
            if (Math.Abs(estimate!.Value + 14.60) > 0.1) wrong.Add("golden");
        }
        Assert.Empty(wrong);
    }

    private static (double? Estimate, int Notes) Estimate(string musicXml)
    {
        var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        try
        {
            player.LoadScore(File.ReadAllBytes(musicXml));
            var notes = AlphaTabScorePlayer.PitchedNotes(player.Score!);
            Assert.Equal(PlaybackLevels.BandEstimateLufs(notes), player.BandEstimateLufs);
            // The velocities are the ones alphaTab's MIDI generator plays (a grace note plays at its
            // main note's mark, so compare the velocities used, not note by note).
            var pitchedTracks = player.Tracks.Where(t => !t.IsPercussion).Select(t => t.Index).ToHashSet();
            var played = player.PlaybackMidi!.Events.OfType<AlphaTab.Midi.NoteOnEvent>()
                .Where(on => on.NoteVelocity > 0 && pitchedTracks.Contains((int)on.Track)).Select(on => (double)on.NoteVelocity).ToHashSet();
            Assert.Equal(played.Order(), notes.Select(n => n.Velocity).Distinct().Order());
            return (player.BandEstimateLufs, notes.Count(n => n.End > n.Start));
        }
        finally { player.Dispose(); RecordingLevel.SetArrangement(null); }
    }

    /// <summary>A score load moves the recording's target, and the recording measured before follows it.</summary>
    [Fact]
    public async Task Recording_follows_the_arrangement_loaded_before_or_after_it()
    {
        var dir = Directory.CreateTempSubdirectory();
        try
        {
            string loud = Path.Combine(dir.FullName, "loud.wav");
            WriteWav(loud, Enumerable.Range(0, 44100 * 3).SelectMany(i => Enumerable.Repeat((float)(0.5 * Math.Sin(2 * Math.PI * 1000 * i / 44100.0)), 2)).ToArray(), 2, pcm16: true);
            var a = new ScriptedOriginal();
            RecordingLevel.SetArrangement(-11.0);
            double lufs = (await RecordingLevel.ApplyAsync(a, loud))!.Value;
            Assert.Equal(-11.0, lufs + 20 * Math.Log10(a.Volume), 1);
            RecordingLevel.SetArrangement(-19.0);
            Assert.Equal(-19.0, lufs + 20 * Math.Log10(a.Volume), 1);
            Assert.Equal(-10.0, RecordingLevel.SetArrangement(-4.0)); // clamped
            Assert.Equal(-10.0, lufs + 20 * Math.Log10(a.Volume), 1);
            Assert.Equal(PlaybackLevels.RecordingFallbackLufs, RecordingLevel.SetArrangement(null));
            Assert.Equal(PlaybackLevels.RecordingFallbackLufs, lufs + 20 * Math.Log10(a.Volume), 1);
        }
        finally { RecordingLevel.SetArrangement(null); dir.Delete(true); }
    }

    [SkippableFact]
    public void Limiter_matches_the_shared_curve()
    {
        Skip.If(Vectors is null, TestPaths.Missing("sounds/output-stage-vectors.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        int n = 0;
        foreach (var v in doc.RootElement.GetProperty("limiter").EnumerateArray())
        {
            float x = (float)v.GetProperty("in").GetDouble();
            Assert.Equal(v.GetProperty("out").GetDouble(), OutputStage.Limit(x), 6);
            n++;
        }
        Assert.True(n > 10);
        // monotonic and memoryless: it cannot pump or invert
        float last = 0;
        for (int i = 0; i <= 400; i++) { float y = OutputStage.Limit(i / 100f); Assert.True(y >= last); last = y; }
    }

    [SkippableFact]
    public void Recording_gain_matches_the_shared_rule()
    {
        Skip.If(Vectors is null, TestPaths.Missing("sounds/output-stage-vectors.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        foreach (var v in doc.RootElement.GetProperty("recording_gain").EnumerateArray())
        {
            double lufs = v.GetProperty("lufs").ValueKind == JsonValueKind.Null ? double.NegativeInfinity : v.GetProperty("lufs").GetDouble();
            Assert.Equal(v.GetProperty("gain_db").GetDouble(), PlaybackLevels.RecordingGainDb(lufs), 6);
        }
        // MediaPlayer can only turn down: the volume is the gain, capped at 1
        Assert.Equal(1.0, PlaybackLevels.RecordingVolume(-30));
        Assert.Equal(Math.Pow(10, -6.0 / 20), PlaybackLevels.RecordingVolume(-10), 6);
    }

    [SkippableFact]
    public void Meter_matches_pyloudnorm()
    {
        Skip.If(Vectors is null, TestPaths.Missing("sounds/output-stage-vectors.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        foreach (var c in doc.RootElement.GetProperty("loudness").EnumerateArray())
        {
            double rate = c.GetProperty("rate").GetDouble();
            int ch = c.GetProperty("channels").GetInt32();
            var tones = c.GetProperty("tones").EnumerateArray().Select(t => (F: t[0].GetDouble(), A: t[1].GetDouble())).ToList();
            var x = new List<float>();
            int t0 = 0;
            foreach (var seg in c.GetProperty("segments").EnumerateArray())
            {
                int n = (int)Math.Round(seg[0].GetDouble() * rate);
                double scale = seg[1].GetDouble();
                for (int i = 0; i < n; i++)
                {
                    double t = (t0 + i) / rate;
                    float v = (float)(tones.Sum(p => p.A * Math.Sin(2 * Math.PI * p.F * t)) * scale);
                    for (int k = 0; k < ch; k++) x.Add(v);
                }
                t0 += n;
            }
            var m = new LoudnessMeter(rate, ch);
            var all = x.ToArray();
            for (int at = 0, k = 0; at < all.Length; k++)
            {
                int frames = new[] { 1000, 4096, 333 }[k % 3];
                int len = Math.Min(all.Length - at, frames * ch);
                m.ProcessInterleaved(all.AsSpan(at, len));
                at += len;
            }
            var want = c.GetProperty("lufs");
            if (want.ValueKind == JsonValueKind.Null) Assert.Equal(double.NegativeInfinity, m.IntegratedLufs);
            else Assert.True(Math.Abs(m.IntegratedLufs - want.GetDouble()) < 0.1, $"{c.GetProperty("name")}: {m.IntegratedLufs} vs {want}");
        }
    }

    [Fact]
    public void Wav_loudness_reads_16_bit_and_float_mono_and_stereo()
    {
        var dir = Directory.CreateTempSubdirectory();
        try
        {
            var tone = Enumerable.Range(0, 44100 * 3).Select(i => (float)(0.1 * Math.Sin(2 * Math.PI * 1000 * i / 44100.0))).ToArray();
            string mono = Path.Combine(dir.FullName, "mono.wav"), stereo = Path.Combine(dir.FullName, "stereo.wav");
            WriteWav(mono, tone, 1, pcm16: true);
            WriteWav(stereo, tone.SelectMany(v => new[] { v, v }).ToArray(), 2, pcm16: false);
            // a 1 kHz tone at −20 dBFS in both channels is −20 LUFS; mono counts as dual mono
            Assert.InRange(LoudnessMeter.IntegratedWav(stereo), -20.2, -19.9);
            Assert.InRange(LoudnessMeter.IntegratedWav(mono), -20.2, -19.9);
        }
        finally { dir.Delete(true); }
    }

    /// <summary>A loud recording is turned down to the target; with a player that can't play a boosted copy, a quiet one plays at full volume.</summary>
    [Fact]
    public async Task Recording_volume_is_set_from_its_measured_loudness()
    {
        var dir = Directory.CreateTempSubdirectory();
        try
        {
            string loud = Path.Combine(dir.FullName, "loud.wav"), quiet = Path.Combine(dir.FullName, "quiet.wav");
            // 1 kHz in both channels: amplitude 0.5 is about −6 LUFS, 0.02 about −34 LUFS
            WriteWav(loud, Enumerable.Range(0, 44100 * 3).SelectMany(i => Enumerable.Repeat((float)(0.5 * Math.Sin(2 * Math.PI * 1000 * i / 44100.0)), 2)).ToArray(), 2, pcm16: true);
            WriteWav(quiet, Enumerable.Range(0, 44100 * 3).Select(i => (float)(0.02 * Math.Sin(2 * Math.PI * 1000 * i / 44100.0))).ToArray(), 1, pcm16: true);
            var a = new ScriptedOriginal();
            double? lufs = await RecordingLevel.ApplyAsync(a, loud);
            Assert.NotNull(lufs);
            Assert.Equal(RecordingLevel.TargetLufs, lufs!.Value + 20 * Math.Log10(a.Volume), 1);
            var b = new ScriptedOriginal();
            Assert.NotNull(await RecordingLevel.ApplyAsync(b, quiet));
            Assert.Equal(1.0, b.Volume);
            var c = new ScriptedOriginal();
            Assert.Null(await RecordingLevel.ApplyAsync(c, Path.Combine(dir.FullName, "missing.wav")));
            Assert.Equal(1.0, c.Volume);
        }
        finally { dir.Delete(true); }
    }

    /// <summary>A player that can play its audio from another file, as Windows' media player does for a boost.</summary>
    private sealed class BoostingOriginal : Brasscribe.Play.Core.Services.IOriginalPlayer
    {
        public bool HasMedia => true;
        public bool HasVideo => false;
        public void Open(string path, bool hasVideo) { }
        public void PlayRange(TimeSpan start, TimeSpan end, bool loop) { }
        public void Play() { }
        public void Pause() { }
        public void Stop() { }
        public bool IsPlaying => false;
        public bool IsMuted { get; set; }
        public double Rate { get; set; } = 1;
        public double Volume { get; set; } = 1;
        public TimeSpan Position { get; set; }
        public bool CanUseAudio => true;
        public string? Audio { get; private set; }
        public void UseAudio(string? wavPath) => Audio = wavPath;
    }

    private static float[] Sine(double amplitude, int channels, int seconds = 3) =>
        Enumerable.Range(0, 44100 * seconds).SelectMany(i => Enumerable.Repeat((float)(amplitude * Math.Sin(2 * Math.PI * 1000 * i / 44100.0)), channels)).ToArray();

    /// <summary>A quiet recording is boosted to the target from a copy with the gain and the soft limiter; a loud one is turned down.</summary>
    [Fact]
    public async Task A_quiet_recording_is_boosted_to_the_target_and_cannot_clip()
    {
        var dir = Directory.CreateTempSubdirectory();
        try
        {
            string quiet = Path.Combine(dir.FullName, "quiet.wav"), loud = Path.Combine(dir.FullName, "loud.wav");
            WriteWav(quiet, Sine(0.06, 2), 2, pcm16: true); // about −24 LUFS
            WriteWav(loud, Sine(0.5, 2), 2, pcm16: true);
            RecordingLevel.SetArrangement(-14.0);
            var a = new BoostingOriginal();
            double lufs = (await RecordingLevel.ApplyAsync(a, quiet))!.Value;
            Assert.InRange(-14.0 - lufs, 4, PlaybackLevels.RecordingMaxBoostDb);
            Assert.Equal(1.0, a.Volume);
            Assert.NotNull(a.Audio);
            Assert.Equal(-14.0, LoudnessMeter.IntegratedWav(a.Audio!), 0.3);

            // The target follows the next arrangement: a new copy, and none when it no longer needs a boost.
            RecordingLevel.SetArrangement(-18.0);
            await RecordingLevel.Settled;
            Assert.Equal(-18.0, LoudnessMeter.IntegratedWav(a.Audio!), 0.3);
            RecordingLevel.SetArrangement(-30.0); // clamped to −20: still a boost
            await RecordingLevel.Settled;
            Assert.Equal(-20.0, LoudnessMeter.IntegratedWav(a.Audio!), 0.3);

            var b = new BoostingOriginal();
            double loudLufs = (await RecordingLevel.ApplyAsync(b, loud))!.Value;
            Assert.Null(b.Audio);
            Assert.Equal(RecordingLevel.TargetLufs, loudLufs + 20 * Math.Log10(b.Volume), 1);
        }
        finally { RecordingLevel.SetArrangement(null); dir.Delete(true); }
    }

    [Fact]
    public void The_boost_is_capped_and_its_peaks_stay_under_the_ceiling()
    {
        var dir = Directory.CreateTempSubdirectory();
        try
        {
            string near = Path.Combine(dir.FullName, "near.wav");
            WriteWav(near, Sine(0.3, 1), 1, pcm16: false);
            string boosted = RecordingBoost.Prepare(near, 12.0); // 0.3 × 4 = 1.2 before the limiter
            float peak = 0;
            LoudnessMeter.ReadWav(boosted, (_, ch) => Assert.Equal(1, ch), s => { foreach (var x in s) peak = Math.Max(peak, Math.Abs(x)); });
            Assert.InRange(peak, OutputStage.Threshold, OutputStage.Ceiling);
            Assert.Equal(boosted, RecordingBoost.Prepare(near, 12.04)); // the same 0.1 dB step: reused
            Assert.Equal(PlaybackLevels.RecordingMaxBoostDb, PlaybackLevels.RecordingGainDb(-60, -12));
        }
        finally { dir.Delete(true); }
    }

    private static void WriteWav(string path, float[] samples, int channels, bool pcm16)
    {
        using var w = new BinaryWriter(File.Create(path));
        int bps = pcm16 ? 2 : 4, bytes = samples.Length * bps;
        w.Write("RIFF"u8); w.Write(36 + bytes); w.Write("WAVE"u8);
        w.Write("fmt "u8); w.Write(16); w.Write((short)(pcm16 ? 1 : 3)); w.Write((short)channels); w.Write(44100);
        w.Write(44100 * channels * bps); w.Write((short)(channels * bps)); w.Write((short)(bps * 8));
        w.Write("data"u8); w.Write(bytes);
        foreach (var v in samples) { if (pcm16) w.Write((short)Math.Round(v * 32767)); else w.Write(v); }
    }

    /// <summary>The full band lands on the shared phrase target and never clips.</summary>
    [SkippableFact]
    public void Full_band_phrase_lands_on_the_shared_target()
    {
        var mix = RenderBandPhrase();
        Skip.If(mix is null, TestPaths.Missing($"{BandSf2}, data/sounds/phrases/phrases.json or sounds/mapping.json"));
        double lufs = LoudnessMeter.Integrated(mix, 44100, 2);
        float peak = Peak(mix);
        log.WriteLine($"LEVELS windows phrase peak {Db(peak):0.00} dBFS, {lufs:0.00} LUFS at {PlaybackLevels.BandGainDb} dB");
        Assert.True(peak <= OutputStage.Ceiling);
        Assert.InRange(lufs, PlaybackLevels.BandPhraseLufs - 1, PlaybackLevels.BandPhraseLufs + 1);
    }

    private static (AlphaTabScorePlayer Player, BufferedSynthOutput Output)? GoldenPlayer()
    {
        var sf2 = TestPaths.RepoFile(BandSf2);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (Mapping is null || sf2 is null || golden is null) return null;
        var output = new BufferedSynthOutput();
        var player = new AlphaTabScorePlayer(output);
        BandSoundFont.Load(Mapping, sf2).ApplyTo(player).Wait();
        player.LoadScore(File.ReadAllBytes(golden));
        Assert.True(player.IsReady, player.LoadError?.Message);
        return (player, output);
    }

    private static float[] Pull(BufferedSynthOutput output, double seconds)
    {
        var all = new float[2 * (int)(seconds * 44100)];
        var buffer = new float[2 * 1024];
        for (int at = 0; at < all.Length; at += buffer.Length)
        {
            output.Read(buffer);
            Array.Copy(buffer, 0, all, at, Math.Min(buffer.Length, all.Length - at));
        }
        return all;
    }

    /// <summary>
    /// The golden arrangement from the band lands where its band estimate says, and the recording's
    /// target is that estimate: the recording plays at the band's loudness for this score (§11).
    /// </summary>
    [SkippableFact]
    [Trait("Category", "Slow")] // seconds; the fast tier filters it out (docs/dev/verify.md)
    public void Golden_arrangement_plays_at_the_recording_target()
    {
        var golden = GoldenPlayer();
        Skip.If(golden is null, NoGoldenPlayer);
        var g = golden.Value;
        using var player = g.Player;
        try
        {
            double target = RecordingLevel.TargetLufs;
            Assert.Equal(PlaybackLevels.RecordingTargetLufs(player.BandEstimateLufs), target);
            player.Play();
            var all = Pull(g.Output, 252); // the arrangement is 250 s
            player.Pause();
            double lufs = LoudnessMeter.Integrated(all, 44100, 2);
            log.WriteLine($"LEVELS windows golden arrangement peak {Db(Peak(all)):0.00} dBFS, {lufs:0.00} LUFS, recording target {target:0.00}");
            Assert.True(Peak(all) <= OutputStage.Ceiling);
            Assert.InRange(lufs, target - 0.5, target + 0.5);
        }
        finally { RecordingLevel.SetArrangement(null); }
    }

    /// <summary>The metronome click peaks at the shared level after the stage.</summary>
    [SkippableFact]
    public void Metronome_clicks_at_the_shared_level()
    {
        var golden = GoldenPlayer();
        Skip.If(golden is null, NoGoldenPlayer);
        var g = golden.Value;
        using var player = g.Player;
        foreach (var t in player.Tracks) player.SetMute(t.Index, true);
        player.Metronome = true;
        player.SeekToBar(4);
        player.Play();
        var all = Pull(g.Output, 4);
        player.Pause();
        log.WriteLine($"LEVELS windows metronome click peak {Db(Peak(all)):0.00} dBFS");
        Assert.InRange(Db(Peak(all)), PlaybackLevels.MetronomeClickPeakDbfs - 1.5, PlaybackLevels.MetronomeClickPeakDbfs + 1.5);
    }

    /// <summary>Below the knee the stage is a plain gain: soloing a part keeps its level in the mix.</summary>
    [SkippableFact]
    public void Solo_keeps_its_level_below_the_knee()
    {
        var golden = GoldenPlayer();
        Skip.If(golden is null, NoGoldenPlayer);
        var g = golden.Value;
        using var player = g.Player;
        var cornet = player.Tracks.First(t => t.Name.Contains("Solo Cornet", StringComparison.OrdinalIgnoreCase));
        player.SetSolo(cornet.Index, true);
        player.SeekToBar(1);
        player.Play();
        var solo = Pull(g.Output, 8);
        player.Pause();
        float peak = Peak(solo);
        log.WriteLine($"LEVELS windows solo cornet peak {Db(peak):0.00} dBFS");
        Assert.True(peak > 0.01 && peak < OutputStage.Threshold, "a solo part stays below the limiter");
    }

    /// <summary>Stop fades what is already rendered to silence: no step at the start, silence after 80 ms.</summary>
    [SkippableFact]
    public void Stop_fades_without_a_click()
    {
        var golden = GoldenPlayer();
        Skip.If(golden is null, NoGoldenPlayer);
        var g = golden.Value;
        using var player = g.Player;
        player.SeekToBar(4);
        player.Play();
        var before = Pull(g.Output, 1);
        player.Pause();
        var after = Pull(g.Output, 0.2);
        int fade = 2 * (int)(44100 * BufferedSynthOutput.StopFadeMs / 1000);
        // the first sample after Stop continues the waveform (no step), the tail is silent
        float last = before[^2], first = after[0];
        Assert.True(Math.Abs(first - last) < 0.1, $"step {last} → {first}");
        Assert.True(Peak(after[fade..]) == 0);
        // the envelope only goes down
        double prev = double.MaxValue;
        for (int w = 0; w + 441 * 2 <= fade; w += 441 * 2)
        {
            double e = Peak(after[w..(w + 441 * 2)]);
            Assert.True(e <= prev * 1.5 + 1e-4, $"fade rises at {w / 2} samples");
            prev = Math.Max(e, 1e-6);
        }
    }
}
