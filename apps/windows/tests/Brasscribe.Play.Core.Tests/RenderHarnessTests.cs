using System.Diagnostics;
using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Offline renders of whole scores through the Windows player (alphaSynth, the band SoundFont and
/// the output stage), for listening and for comparing sound changes. Runs only when
/// BRASSCRIBE_RENDER_OUT is set:
/// <list type="bullet">
/// <item>BRASSCRIBE_RENDER_SCORES: brass-band.musicxml paths, colon-separated (default: the golden arrangement)</item>
/// <item>BRASSCRIBE_RENDER_SF2: label=path pairs, comma-separated (default: desktop and mobile band SoundFonts)</item>
/// <item>BRASSCRIBE_RENDER_PARTS=1: also every part solo, first score, first SoundFont, at −12 dB</item>
/// </list>
/// Writes &lt;score&gt;-alphatab-&lt;label&gt;.wav (the app's output) and …-m12.wav (make-up gain 12 dB lower,
/// so the limiter all but never bends: the signal before it), 32-bit float stereo at 44.1 kHz.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class RenderHarnessTests(ITestOutputHelper log)
{
    private const double RenderGainDb = -12;

    /// <summary>
    /// The band kit (bank 128 program 0) against the pop kit (program 1, MS Basic unchanged) through
    /// alphaSynth: K-weighted level of each drum's hits. Runs only when BRASSCRIBE_KNOTS=1.
    /// </summary>
    [SkippableFact]
    public void Measure_kits()
    {
        Skip.If(Environment.GetEnvironmentVariable("BRASSCRIBE_KNOTS") != "1", "BRASSCRIBE_KNOTS is not 1");
        var bytes = File.ReadAllBytes(TestPaths.RepoFile("data/sounds/band/brasscribe-band-16bit.sf2")!);
        foreach (var key in new[] { 36, 38, 40, 42, 49, 57 })
        {
            var levels = new List<string>();
            foreach (var program in new[] { 0, 1 })
            {
                var notes = System.Text.Json.JsonSerializer.SerializeToElement(new[] { 47, 79, 95, 111, 127 }
                    .Select((v, i) => new object[] { 0.5 + 2.0 * i, 0.6 + 2.0 * i, key, v }).ToArray());
                var mix = PartSoundTests.Render(bytes, PartSoundTests.Phrase([(ChannelPlan.Drums, program, 128, notes)]), 11.0);
                levels.Add($"{LoudnessMeter.Integrated(mix, 44100, 2):0.00}");
            }
            log.WriteLine($"KIT key {key}: band kit {levels[0]} LUFS, pop kit {levels[1]} LUFS");
        }
    }

    /// <summary>
    /// dynamics.sampler_velocity.alphatab_lufs, measured: the full-band phrase's pitched parts at one
    /// velocity through alphaSynth with the app's channel plan and balance, 12 dB under the band gain.
    /// Runs only when BRASSCRIBE_KNOTS=1 (after a sound pack change).
    /// </summary>
    [SkippableFact]
    public void Measure_velocity_knots()
    {
        Skip.If(Environment.GetEnvironmentVariable("BRASSCRIBE_KNOTS") != "1", "BRASSCRIBE_KNOTS is not 1");
        var sf2Path = TestPaths.RepoFile("data/sounds/band/brasscribe-band-16bit.sf2")!;
        var phrases = TestPaths.RepoFile("data/sounds/phrases/phrases.json")!;
        var band = BandSoundFont.Load(TestPaths.RepoFile("sounds/mapping.json")!);
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(phrases));
        var parts = doc.RootElement.GetProperty("band").EnumerateObject().Where(p => !band.For(p.Name)!.Percussion).ToList();
        var plan = ChannelPlan.ForPlayback(parts.Select((b, i) =>
        {
            var s = band.For(b.Name)!;
            return new ChannelPlan.Part(i, s.Percussion, s.Program, s.GainDb);
        }).ToList());
        var bytes = File.ReadAllBytes(sf2Path);
        foreach (var v in new[] { 15, 31, 47, 63, 79, 95, 111, 127 })
        {
            var gains = new Dictionary<int, double>();
            var rows = new List<(int, int, int, System.Text.Json.JsonElement)>();
            for (int i = 0; i < parts.Count; i++)
            {
                var s = band.For(parts[i].Name)!;
                gains[plan[i]] = Math.Pow(10, (s.GainDb - 12) / 20);
                var notes = System.Text.Json.JsonSerializer.SerializeToElement(parts[i].Value.GetProperty("notes").EnumerateArray()
                    .Select(n => new object[] { n[0].GetDouble(), n[1].GetDouble(), n[2].GetInt32(), v }).ToArray());
                rows.Add((plan[i], s.Program, s.Bank, notes));
            }
            var mix = PartSoundTests.Render(bytes, PartSoundTests.Phrase(rows), rows.Max(r => PartSoundTests.End(r.Item4)) + 2.0, gains);
            log.WriteLine($"KNOT {v} {LoudnessMeter.Integrated(mix, 44100, 2):0.00} LUFS, peak {20 * Math.Log10(mix.Max(Math.Abs)):0.0} dBFS");
        }
    }

    /// <summary>
    /// Each part of the full-band phrase alone at velocity 80 with the app's channel plan and balance, for
    /// comparing the part balance with Apple's (DynamicsLevelTests.partBalance). Runs only when BRASSCRIBE_KNOTS=1.
    /// </summary>
    [SkippableFact]
    public void Measure_part_balance()
    {
        Skip.If(Environment.GetEnvironmentVariable("BRASSCRIBE_KNOTS") != "1", "BRASSCRIBE_KNOTS is not 1");
        var bytes = File.ReadAllBytes(TestPaths.RepoFile("data/sounds/band/brasscribe-band-16bit.sf2")!);
        var band = BandSoundFont.Load(TestPaths.RepoFile("sounds/mapping.json")!);
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(TestPaths.RepoFile("data/sounds/phrases/phrases.json")!));
        var parts = doc.RootElement.GetProperty("band").EnumerateObject().ToList();
        var plan = ChannelPlan.ForPlayback(parts.Select((b, i) =>
        {
            var s = band.For(b.Name)!;
            return new ChannelPlan.Part(i, s.Percussion, s.Program, s.GainDb);
        }).ToList());
        for (int i = 0; i < parts.Count; i++)
        {
            var s = band.For(parts[i].Name)!;
            var notes = System.Text.Json.JsonSerializer.SerializeToElement(parts[i].Value.GetProperty("notes").EnumerateArray()
                .Select(n => new object[] { n[0].GetDouble(), n[1].GetDouble(), n[2].GetInt32(), 80 }).ToArray());
            var gains = new Dictionary<int, double> { [plan[i]] = Math.Pow(10, (s.GainDb - 12) / 20) };
            var mix = PartSoundTests.Render(bytes, PartSoundTests.Phrase([(plan[i], s.Program, s.Bank, notes)]), PartSoundTests.End(notes) + 2.0, gains);
            log.WriteLine($"BALANCE {parts[i].Name}\t{LoudnessMeter.Integrated(mix, 44100, 2):0.00}");
        }
    }

    /// <summary>
    /// Every pitched part of the full-band phrase alone through alphaSynth, one held note at the middle of the
    /// part's phrase at every odd velocity: where the velocity layers split, the level jumps. Writes
    /// part, velocity and the note's RMS (dBFS, 100–600 ms after the onset) to BRASSCRIBE_SWEEP_OUT (a TSV).
    /// </summary>
    [SkippableFact]
    public void Measure_velocity_sweep()
    {
        var outPath = Environment.GetEnvironmentVariable("BRASSCRIBE_SWEEP_OUT");
        Skip.If(string.IsNullOrEmpty(outPath), "BRASSCRIBE_SWEEP_OUT is not set");
        var bytes = File.ReadAllBytes(TestPaths.RepoFile("data/sounds/band/brasscribe-band-16bit.sf2")!);
        var band = BandSoundFont.Load(TestPaths.RepoFile("sounds/mapping.json")!);
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(TestPaths.RepoFile("data/sounds/phrases/phrases.json")!));
        var lines = new List<string> { "part\tpitch\tvelocity\trms_db" };
        var velocities = Enumerable.Range(0, 64).Select(i => 1 + 2 * i).ToArray();
        foreach (var p in doc.RootElement.GetProperty("band").EnumerateObject())
        {
            var s = band.For(p.Name)!;
            if (s.Percussion) continue;
            var pitches = p.Value.GetProperty("notes").EnumerateArray().Select(n => n[2].GetInt32()).OrderBy(x => x).ToList();
            int pitch = pitches[pitches.Count / 2];
            var notes = System.Text.Json.JsonSerializer.SerializeToElement(velocities
                .Select((v, i) => new object[] { 0.2 + 1.0 * i, 0.9 + 1.0 * i, pitch, v }).ToArray());
            var mix = PartSoundTests.Render(bytes, PartSoundTests.Phrase([(0, s.Program, s.Bank, notes)]), velocities.Length + 1.0);
            for (int i = 0; i < velocities.Length; i++)
            {
                int a = (int)((0.3 + i) * 44100), b = (int)((0.8 + i) * 44100);
                double sum = 0;
                for (int k = a; k < b; k++) { double m = 0.5 * (mix[2 * k] + mix[2 * k + 1]); sum += m * m; }
                lines.Add($"{p.Name}\t{pitch}\t{velocities[i]}\t{10 * Math.Log10(sum / (b - a) + 1e-20):0.00}");
            }
        }
        File.WriteAllLines(outPath!, lines);
        log.WriteLine($"SWEEP {outPath}: {lines.Count - 1} rows");
    }

    [SkippableFact]
    public void Render_scores()
    {
        var outDir = Environment.GetEnvironmentVariable("BRASSCRIBE_RENDER_OUT");
        Skip.If(string.IsNullOrEmpty(outDir), "BRASSCRIBE_RENDER_OUT is not set");
        Directory.CreateDirectory(outDir);
        var mapping = TestPaths.RepoFile("sounds/mapping.json");
        Assert.NotNull(mapping);
        log.WriteLine($"mapping {mapping}");

        var scores = (Environment.GetEnvironmentVariable("BRASSCRIBE_RENDER_SCORES") is { Length: > 0 } s
            ? s.Split(':', StringSplitOptions.RemoveEmptyEntries)
            : [TestPaths.RepoFile(TestPaths.GoldenMusicXml)!]).ToList();
        var repo = Environment.GetEnvironmentVariable("BRASSCRIBE_REPO") ?? TestPaths.RepoRoot!;
        var sf2s = (Environment.GetEnvironmentVariable("BRASSCRIBE_RENDER_SF2") is { Length: > 0 } f
                ? f
                : $"desktop={repo}/data/sounds/band/brasscribe-band-16bit.sf2,mobile={repo}/data/sounds/band/brasscribe-band-mobile.sf2")
            .Split(',', StringSplitOptions.RemoveEmptyEntries)
            .Select(p => p.Split('=', 2))
            .Select(p => (Label: p[0], Path: p[1]))
            .ToList();
        foreach (var (label, path) in sf2s) Assert.True(File.Exists(path), $"{label}: {path} not found");
        foreach (var score in scores) Assert.True(File.Exists(score), $"{score} not found");

        foreach (var score in scores)
        {
            string name = new DirectoryInfo(Path.GetDirectoryName(Path.GetFullPath(score))!).Name;
            foreach (var (label, sf2) in sf2s)
            {
                Render(mapping, sf2, score, Path.Combine(outDir, $"{name}-alphatab-{label}.wav"), 0, null);
                Render(mapping, sf2, score, Path.Combine(outDir, $"{name}-alphatab-{label}-m12.wav"), RenderGainDb, null);
            }
        }

        if (Environment.GetEnvironmentVariable("BRASSCRIBE_RENDER_PARTS") != "1") return;
        string first = scores[0];
        string firstName = new DirectoryInfo(Path.GetDirectoryName(Path.GetFullPath(first))!).Name;
        var (_, desktop) = sf2s[0];
        var tracks = Load(mapping, desktop, first, 0).Player;
        var parts = tracks.Tracks.ToList();
        tracks.Dispose();
        foreach (var t in parts)
        {
            string slug = t.Name.ToLowerInvariant().Replace(' ', '-').Replace("♭", "b");
            Render(mapping, desktop, first, Path.Combine(outDir, $"{firstName}-alphatab-part-{slug}.wav"), RenderGainDb, t.Index);
        }
    }

    private static (AlphaTabScorePlayer Player, BufferedSynthOutput Output) Load(string mapping, string sf2, string score, double gainDb)
    {
        var output = new BufferedSynthOutput { Gain = OutputStage.BandGain * (float)Math.Pow(10, gainDb / 20) };
        var player = new AlphaTabScorePlayer(output);
        var band = BandSoundFont.Load(mapping, sf2);
        Assert.Equal(Path.GetFullPath(sf2), Path.GetFullPath(band.SoundFontPath!));
        band.ApplyTo(player).Wait();
        player.LoadScore(File.ReadAllBytes(score));
        Assert.True(player.IsReady, player.LoadError?.Message);
        return (player, output);
    }

    private void Render(string mapping, string sf2, string score, string wav, double gainDb, int? solo)
    {
        var clock = Stopwatch.StartNew();
        var (player, output) = Load(mapping, sf2, score, gainDb);
        try
        {
            if (solo is { } s) player.SetSolo(s, true);
            bool finished = false;
            player.Finished += (_, _) => finished = true;
            player.Play();
            var all = new List<float>(2 * 44100 * 260);
            var buffer = new float[2 * 1024];
            // alphaSynth ends the song after the release tail (AddReleaseTail); the cap only guards a hang
            while (!finished && all.Count < 2 * 44100 * 900)
            {
                output.Read(buffer);
                all.AddRange(buffer);
            }
            // what the ring still held when the song ended
            for (int i = 0; i < 44100 * 2 / buffer.Length; i++) { output.Read(buffer); all.AddRange(buffer); }
            player.Stop();
            var x = all.ToArray();
            WriteFloatWav(wav, x);
            double lufs = LoudnessMeter.Integrated(x, 44100, 2);
            float peak = x.Length == 0 ? 0 : x.Max(Math.Abs);
            double over = x.Count(v => Math.Abs(v) > OutputStage.Threshold) / (double)Math.Max(1, x.Length);
            log.WriteLine($"RENDER {Path.GetFileName(wav)}: {x.Length / 2 / 44100.0:0.0} s, {lufs:0.00} LUFS, peak {20 * Math.Log10(Math.Max(peak, 1e-9)):0.00} dBFS, " +
                          $"|x|>{OutputStage.Threshold}: {over:P3}, gain {PlaybackLevels.BandGainDb + gainDb:+0;-0} dB, sf2 {sf2}, {clock.Elapsed.TotalSeconds:0.0} s wall");
        }
        finally
        {
            player.Dispose();
            RecordingLevel.SetArrangement(null);
        }
    }

    private static void WriteFloatWav(string path, float[] samples)
    {
        using var w = new BinaryWriter(File.Create(path));
        int bytes = samples.Length * 4;
        w.Write("RIFF"u8); w.Write(36 + bytes); w.Write("WAVE"u8);
        w.Write("fmt "u8); w.Write(16); w.Write((short)3); w.Write((short)2); w.Write(44100);
        w.Write(44100 * 2 * 4); w.Write((short)8); w.Write((short)32);
        w.Write("data"u8); w.Write(bytes);
        foreach (var v in samples) w.Write(v);
    }
}
