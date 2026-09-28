using System.Diagnostics;
using AlphaTab.Core.EcmaScript;
using AlphaTab.Importer;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Review;
using Brasscribe.Play.Core.TalkingScore;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// alphaTab .NET run headless: MusicXML import, transposition display, SVG rendering, MIDI and the
/// synth pulled through <see cref="BufferedSynthOutput"/> without an audio device.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class AlphaTabTests(ITestOutputHelper log)
{
    private static byte[] Fixture() => File.ReadAllBytes(TestPaths.Fixture("two-parts.musicxml"));

    [Fact]
    public void Imports_transposing_parts_and_generates_midi()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(Fixture());
        Assert.Equal(3, player.Tracks.Count);
        Assert.Equal(5, player.BarCount);
        Assert.Equal("Solo Cornet", player.Tracks[0].Name);
        Assert.Equal(-2, player.Tracks[0].DisplayTransposition);
        Assert.True(player.Tracks[2].IsPercussion);
        var midi = player.ExportMidi();
        Assert.Equal("MThd"u8.ToArray(), midi[..4]);
        Assert.Equal((0.0, 3840.0), player.BarTicks(0));
    }

    [Fact]
    public void Midi_export_ignores_playback_routing_and_styling()
    {
        using var plain = new AlphaTabScorePlayer(new BufferedSynthOutput());
        plain.LoadScore(Fixture());
        using var routed = new AlphaTabScorePlayer(new BufferedSynthOutput()) { ProgramMap = _ => 8 };
        routed.LoadScore(Fixture());
        var ts = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")));
        ts.Parts[0].Bars[0].Events[1].Confidence = 0.2; // very uncertain: ghost notehead in the view
        ScoreStyler.ApplyUncertainty(routed.Score!, ts, UncertaintyPalette.Light);
        Assert.Equal(plain.ExportMidi(), routed.ExportMidi());
    }

    [Fact]
    public void Loop_speed_and_mixer_state()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(Fixture());
        player.SetLoop(3, 1);
        Assert.Equal((1, 3), player.Loop);
        player.SetLoop(null, null);
        Assert.Null(player.Loop);
        player.Speed = 2.0;
        Assert.Equal(1.5, player.Speed);
        player.Speed = 0.1;
        Assert.Equal(0.25, player.Speed);
        player.SetMute(1, true);
        player.SetSolo(0, true);
        Assert.True(player.IsMuted(1));
        Assert.True(player.IsSolo(0));
        player.Metronome = true;
        player.CountIn = true;
        Assert.True(player.Metronome && player.CountIn);
    }

    [Fact]
    public void Renders_svg_and_styles_uncertain_notes()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(Fixture());
        var ts = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")));
        int styled = ScoreStyler.ApplyUncertainty(player.Score!, ts, UncertaintyPalette.Light);
        Assert.Equal(1, styled);

        var output = new ScoreRenderService("svg").Render(player.Score!, [0], 1000);
        Assert.NotEmpty(output.Partials);
        Assert.True(output.TotalHeight > 0);
        var svg = string.Concat(output.Partials.Select(p => p.Result as string));
        Assert.Contains("<svg", svg);
        Assert.Contains("#0063A6", svg, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(output.Bounds?.FindMasterBarByIndex(0));
    }

    [Fact]
    public void Renders_png_bitmaps_with_skia_as_the_app_does()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(Fixture());
        var svc = new ScoreRenderService("skia") { Scale = 2.0 };
        var output = svc.Render(player.Score!, [0, 1], 800);
        try
        {
            Assert.NotEmpty(output.Partials);
            var png = ScoreRenderService.ToPng(output.Partials[0].Result)!;
            Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47 }, png[..4]);
            var small = new ScoreRenderService("skia") { Scale = 1.0 }.Render(player.Score!, [0, 1], 800);
            Assert.True(output.TotalHeight > small.TotalHeight * 1.5, $"zoom 200% should grow the score: {small.TotalHeight} -> {output.TotalHeight}");
            ScoreRenderService.Release(small);
        }
        finally
        {
            ScoreRenderService.Release(output);
        }
    }

    [SkippableFact]
    public void Golden_brass_band_score_imports_and_renders()
    {
        var path = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        Skip.If(path is null, TestPaths.Missing(TestPaths.GoldenMusicXml));
        var sw = Stopwatch.StartNew();
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(File.ReadAllBytes(path));
        long load = sw.ElapsedMilliseconds;
        Assert.Equal(18, player.Tracks.Count);
        Assert.True(player.BarCount > 100);
        var solo = player.Tracks.Single(t => t.Name == "Solo Cornet");
        Assert.Equal(-2, solo.DisplayTransposition);
        Assert.Equal(3, player.Tracks.Single(t => t.Name == "Soprano Cornet").DisplayTransposition);
        Assert.True(player.Tracks.Single(t => t.Name == "Percussion").IsPercussion);

        sw.Restart();
        var part = new ScoreRenderService("svg").Render(player.Score!, [solo.Index], 1200);
        long renderPart = sw.ElapsedMilliseconds;
        sw.Restart();
        var full = new ScoreRenderService("svg").Render(player.Score!, player.Tracks.Select(t => t.Index).ToList(), 1600);
        long renderFull = sw.ElapsedMilliseconds;
        Assert.NotEmpty(part.Partials);
        Assert.NotEmpty(full.Partials);
        log.WriteLine($"golden: load+midi {load} ms, solo part svg {renderPart} ms ({part.TotalWidth:0}x{part.TotalHeight:0}), " +
                      $"full score svg {renderFull} ms ({full.TotalWidth:0}x{full.TotalHeight:0}), midi {player.ExportMidi().Length} bytes");

        // What the app does on the UI thread for every load, zoom or part change: Skia render plus PNG encode.
        foreach (var (scale, tracks, label) in new[] { (1.0, player.Tracks.Select(t => t.Index).ToList(), "full 100%"),
                     (2.0, player.Tracks.Select(t => t.Index).ToList(), "full 200%"), (1.0, [solo.Index], "solo 100%"), (4.0, [solo.Index], "solo 400%") })
        {
            sw.Restart();
            var skia = new ScoreRenderService("skia") { Scale = scale }.Render(player.Score!, tracks, 1600);
            long render = sw.ElapsedMilliseconds;
            sw.Restart();
            long bytes = skia.Partials.Sum(p => (long)(ScoreRenderService.ToPng(p.Result)?.Length ?? 0));
            long png = sw.ElapsedMilliseconds;
            ScoreRenderService.Release(skia);
            log.WriteLine($"golden skia {label}: render {render} ms, png {png} ms, {skia.Partials.Count} partials, {bytes / 1024} KiB");
        }
    }

    [SkippableFact]
    public void Synth_plays_through_the_buffered_output()
    {
        var sf = TestPaths.RepoFile(Environment.GetEnvironmentVariable("BRASSCRIBE_TEST_SF2") ?? "data/sounds/built/trombone/trombone.sf2");
        Skip.If(sf is null, TestPaths.Missing(Environment.GetEnvironmentVariable("BRASSCRIBE_TEST_SF2") ?? "data/sounds/built/trombone/trombone.sf2"));
        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        player.LoadSoundFont(File.ReadAllBytes(sf));
        player.LoadScore(Fixture());
        Assert.True(player.IsReady, player.LoadError?.Message);

        player.Play();
        var buffer = new float[2 * 1024];
        double sumSquares = 0;
        long n = 0;
        for (int i = 0; i < 44100 * 2 / 1024; i++) // about two seconds of audio
        {
            output.Read(buffer);
            foreach (var s in buffer) sumSquares += s * s;
            n += buffer.Length;
        }
        double rms = Math.Sqrt(sumSquares / n);
        log.WriteLine($"synth rms over 2 s: {rms:0.0000}, position {player.Position}");
        Assert.True(rms > 0.001, $"synth output is silent (rms {rms})");
        Assert.True(player.Position.Seconds > 1.0, $"position did not advance: {player.Position}");
        Assert.True(player.Position.BarIndex >= 0);
    }

    [SkippableFact]
    public void Synth_survives_ui_calls_while_the_audio_thread_renders()
    {
        var sf = TestPaths.RepoFile("data/sounds/built/cornet-b/cornet-b.sf2");
        Skip.If(sf is null, TestPaths.Missing("data/sounds/built/cornet-b/cornet-b.sf2"));
        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        player.LoadSoundFont(File.ReadAllBytes(sf));
        player.LoadScore(Fixture());
        player.Play();

        using var stop = new CancellationTokenSource();
        Exception? audioError = null;
        long frames = 0;
        var audio = new Thread(() =>
        {
            var buffer = new float[2 * 512];
            try
            {
                while (!stop.IsCancellationRequested)
                {
                    output.Read(buffer);
                    frames += 512;
                }
            }
            catch (Exception e) { audioError = e; }
        });
        audio.Start();

        var xml = Fixture();
        for (int i = 0; i < 200; i++)
        {
            player.SetMute(i % 3, i % 2 == 0);
            player.SetSolo(0, i % 5 == 0);
            player.SetLoop(i % 4, i % 4 + 1);
            player.SeekToBar(i % 5);
            player.Speed = 0.5 + i % 10 / 10.0;
            if (i % 50 == 0) player.LoadScore(xml);
            if (i % 50 == 1) player.Play();
        }
        stop.Cancel();
        audio.Join();
        Assert.Null(audioError);
        Assert.True(frames > 0);
        log.WriteLine($"rendered {frames} frames on the audio thread during 200 UI calls");
    }

    [SkippableFact]
    public void Golden_score_sounds_with_the_built_brass_soundfonts()
    {
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var dir = TestPaths.RepoRoot is { } root ? Path.Combine(root, "data", "sounds", "built") : null;
        Skip.If(golden is null, TestPaths.Missing(TestPaths.GoldenMusicXml));
        Skip.If(dir is null || !Directory.Exists(dir), TestPaths.Missing("data/sounds/built"));
        var set = BrassSoundSet.Load(dir, TestPaths.RepoFile("sounds/mapping.json"));
        Skip.If(set.Files.Count == 0, "data/sounds/built has no SoundFonts: they are build outputs (scripts/worktree-setup.sh links data/ from a checkout that has them)");

        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        set.ApplyTo(player);
        player.LoadScore(File.ReadAllBytes(golden));
        Assert.True(player.IsReady, player.LoadError?.Message);

        // Solo each track in turn for three seconds from bar 20 and measure the level.
        var levels = new List<string>();
        int silent = 0, pitched = 0;
        foreach (var track in player.Tracks)
        {
            foreach (var t in player.Tracks) player.SetSolo(t.Index, t.Index == track.Index);
            player.SeekToBar(19);
            player.Play();
            var buffer = new float[2 * 1024];
            double sum = 0;
            long n = 0;
            for (int i = 0; i < 44100 * 3 / 1024; i++)
            {
                output.Read(buffer);
                foreach (var v in buffer) sum += v * v;
                n += buffer.Length;
            }
            player.Pause();
            double rms = Math.Sqrt(sum / n);
            levels.Add($"{track.Name} {rms:0.0000}");
            bool hasNotes = player.Score!.Tracks[track.Index].Staves.SelectMany(st => st.Bars).SelectMany(b => b.Voices)
                .SelectMany(v => v.Beats).Any(b => b.Notes.Count > 0);
            if (!track.IsPercussion && hasNotes) // the arranger leaves some parts empty (Soprano Cornet in Mikkel)
            {
                pitched++;
                if (rms < 1e-4) silent++;
            }
        }
        log.WriteLine($"{set.Files.Count} SoundFonts, programs {string.Join(",", set.Programs.Select(p => $"{p.Key}={p.Value}"))}; per-track rms from bar 20: " + string.Join("; ", levels));
        Assert.Equal(0, silent);
    }

    [Fact]
    public void Score_loader_accepts_bytes()
    {
        var score = ScoreLoader.LoadScoreFromBytes(new Uint8Array(Fixture()), new AlphaTab.Settings());
        Assert.Equal("Test tune", score.Title.Replace('\u00A0', ' ')); // alphaTab stores spaces as no-break spaces
    }
}
