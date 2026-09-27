using System.Text.Json;
using AlphaTab.Core.EcmaScript;
using AlphaTab.Midi;
using AlphaTab.Synth;
using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Every score part reaches its own real-sample preset: the shared resolver vectors
/// (sounds/partsound-vectors.json), other writers' part names on the golden score, unisons in
/// the MIDI export, and (with BRASSCRIBE_SOUNDCHECK_OUT set) the test phrases rendered through
/// alphaSynth for sounds/soundcheck.py.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class PartSoundTests(ITestOutputHelper log)
{
    private static string? Mapping => TestPaths.RepoFile("sounds/mapping.json");
    private static string? Vectors => TestPaths.RepoFile("sounds/partsound-vectors.json");
    private const string BandSf2 = "data/sounds/band/brasscribe-band.sf2";

    [Fact]
    public void Resolver_matches_every_shared_vector()
    {
        if (Mapping is null || Vectors is null) return;
        var resolver = PartSoundResolver.Load(Mapping);
        using var doc = JsonDocument.Parse(File.ReadAllText(Vectors));
        int n = 0;
        foreach (var v in doc.RootElement.GetProperty("vectors").EnumerateArray())
        {
            string name = v.GetProperty("name").GetString()!;
            string? inst = v.GetProperty("instrument").ValueKind == JsonValueKind.Null ? null : v.GetProperty("instrument").GetString();
            int? prog = v.GetProperty("program").ValueKind == JsonValueKind.Null ? null : v.GetProperty("program").GetInt32();
            var got = resolver.Resolve(name, inst, prog);
            var e = v.GetProperty("expect");
            n++;
            if (e.ValueKind == JsonValueKind.Null)
            {
                Assert.Null(got);
                continue;
            }
            Assert.True(got is not null, $"'{name}' did not resolve");
            Assert.Equal(e.GetProperty("part").GetString(), got!.Part);
            Assert.Equal(e.GetProperty("step").GetString(), got.Step);
            Assert.Equal(e.GetProperty("program").GetInt32(), got.Sound.Program);
            Assert.Equal(e.GetProperty("bank").GetInt32(), got.Sound.Bank);
            Assert.Equal(e.GetProperty("channel_gain_db").GetDouble(), got.Sound.GainDb, 6);
            Assert.Equal(e.GetProperty("percussion").GetBoolean(), got.Sound.Percussion);
        }
        Assert.True(n > 20);
    }

    [Fact]
    public void Every_lineup_part_resolves_by_its_own_name()
    {
        if (Mapping is null) return;
        var resolver = PartSoundResolver.Load(Mapping);
        using var doc = JsonDocument.Parse(File.ReadAllText(Mapping));
        foreach (var lineup in doc.RootElement.GetProperty("lineups").EnumerateObject())
        {
            if (lineup.Value.ValueKind != JsonValueKind.Array) continue;
            foreach (var part in lineup.Value.EnumerateArray())
                Assert.Equal("exact", resolver.Resolve(part.GetString()!)?.Step);
        }
    }

    [Fact]
    public void Golden_score_with_other_writers_part_names_plays_every_part_from_the_band_soundfont()
    {
        var sf2 = TestPaths.RepoFile(BandSf2);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (Mapping is null || sf2 is null || golden is null) return;
        var names = new Dictionary<string, string>
        {
            ["Soprano Cornet"] = "Soprano", ["Solo Cornet"] = "1st Cornet", ["Repiano Cornet"] = "Cornet", ["2nd Cornet"] = "Cornet 2",
            ["3rd Cornet"] = "Trumpet in B♭", ["Flugelhorn"] = "Flügelhorn", ["Solo Horn"] = "Tenor Horn", ["1st Horn"] = "Horn in E♭",
            ["2nd Horn"] = "Alto Horn", ["1st Baritone"] = "Baritone", ["2nd Baritone"] = "Baritone Horn", ["1st Trombone"] = "Trombone",
            ["2nd Trombone"] = "Tenor Trombone", ["Bass Trombone"] = "B. Tbn.", ["Euphonium"] = "Euph", ["E♭ Bass"] = "Tuba",
            ["B♭ Bass"] = "Bass", ["Percussion"] = "Drum Set",
        };
        var xml = File.ReadAllText(golden);
        foreach (var (from, to) in names) xml = xml.Replace($"<part-name>{from}</part-name>", $"<part-name>{to}</part-name>");

        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        var band = BandSoundFont.Load(Mapping, sf2);
        band.ApplyTo(player);
        player.LoadScore(System.Text.Encoding.UTF8.GetBytes(xml));
        Assert.True(player.IsReady, player.LoadError?.Message);
        foreach (var t in player.Tracks) Assert.True(band.For(t.Name) is not null, $"{t.Name} has no preset");

        var silent = new List<string>();
        foreach (var track in player.Tracks)
        {
            foreach (var t in player.Tracks) player.SetSolo(t.Index, t.Index == track.Index);
            player.SeekToBar(50);
            player.Play();
            var buffer = new float[2 * 1024];
            double sum = 0;
            long n = 0;
            for (int i = 0; i < 44100 * 4 / 1024; i++)
            {
                output.Read(buffer);
                foreach (var v in buffer) sum += v * v;
                n += buffer.Length;
            }
            player.Pause();
            bool hasNotes = player.Score!.Tracks[track.Index].Staves.SelectMany(st => st.Bars).Skip(50).Take(2).SelectMany(b => b.Voices)
                .SelectMany(v => v.Beats).Any(b => b.Notes.Count > 0);
            if (hasNotes && Math.Sqrt(sum / n) < 1e-4) silent.Add(track.Name);
        }
        Assert.Empty(silent);
    }

    [Fact]
    public void Midi_export_keeps_a_unison_held_across_parts_sharing_a_channel()
    {
        var smf = new MidiFile { Format = MidiFileFormat.MultiTrack };
        smf.AddEvent(new NoteOnEvent(0, 0, 0, 70, 80));
        smf.AddEvent(new NoteOnEvent(1, 480, 0, 70, 80));
        smf.AddEvent(new NoteOffEvent(1, 960, 0, 70, 0)); // the second part lets go first
        smf.AddEvent(new NoteOffEvent(0, 1920, 0, 70, 0));
        smf.AddEvent(new NoteOnEvent(0, 1920, 0, 70, 80)); // a new note at the same tick: not a unison
        smf.AddEvent(new NoteOffEvent(0, 2400, 0, 70, 0));
        int dropped = AlphaTabScorePlayer.KeepSharedUnisons(smf);
        Assert.Equal(1, dropped);
        var offs = smf.Tracks.SelectMany(t => t.Events).OfType<NoteOffEvent>().Select(e => e.Tick).Order().ToList();
        Assert.Equal([1920.0, 2400.0], offs);
    }

    // ---------------------------------------------------------------- sound check harness

    private const double TicksPerSecond = 1920; // 960 per beat at 120 bpm

    private static MidiFile Phrase(IEnumerable<(int Channel, int Program, int Bank, JsonElement Notes)> parts)
    {
        var midi = new MidiFile { Division = 960 };
        midi.AddEvent(new TempoChangeEvent(0, 500000));
        foreach (var (ch, program, bank, notes) in parts)
        {
            if (ch != ChannelPlan.Drums) midi.AddEvent(new ControlChangeEvent(0, 0, ch, ControllerType.BankSelectCoarse, bank));
            midi.AddEvent(new ProgramChangeEvent(0, 0, ch, program));
            var events = new List<(double Tick, int Order, MidiEvent Event)>();
            foreach (var n in notes.EnumerateArray())
            {
                double on = Math.Round(n[0].GetDouble() * TicksPerSecond), off = Math.Round(n[1].GetDouble() * TicksPerSecond);
                int key = n[2].GetInt32(), vel = n[3].GetInt32();
                events.Add((on, 1, new NoteOnEvent(0, on, ch, key, vel)));
                events.Add((off, 0, new NoteOffEvent(0, off, ch, key, 0)));
            }
            foreach (var e in events.OrderBy(e => e.Tick).ThenBy(e => e.Order)) midi.AddEvent(e.Event);
        }
        var all = midi.Events.OrderBy(e => e.Tick).ToList();
        midi.Events.Clear();
        foreach (var e in all) midi.Events.Add(e);
        AlphaTabScorePlayer.AddReleaseTail(midi); // as the player does
        return midi;
    }

    /// <summary>Renders a MIDI file through alphaSynth as the app does (BufferedSynthOutput), stereo interleaved.</summary>
    private static float[] Render(byte[] sf2, MidiFile midi, double seconds, IReadOnlyDictionary<int, double>? channelGain = null)
    {
        var output = new BufferedSynthOutput();
        var synth = new AlphaSynth(output, 500) { MetronomeVolume = 0, CountInVolume = 0, MasterVolume = AlphaTabScorePlayer.MasterVolume };
        lock (output.SyncRoot)
        {
            synth.LoadSoundFont(new Uint8Array(sf2), false);
            synth.LoadMidiFile(midi);
            if (channelGain is not null)
                foreach (var (ch, g) in channelGain) synth.SetChannelVolume(ch, g);
            synth.Play();
        }
        var total = new float[2 * (int)(seconds * 44100)];
        var buffer = new float[2 * 1024];
        int at = 0;
        while (at < total.Length)
        {
            output.Read(buffer);
            int n = Math.Min(buffer.Length, total.Length - at);
            Array.Copy(buffer, 0, total, at, n);
            at += n;
        }
        lock (output.SyncRoot) synth.Destroy();
        return total;
    }

    private static void WriteWav(string path, float[] stereo)
    {
        using var w = new BinaryWriter(File.Create(path));
        int bytes = stereo.Length * 4;
        w.Write("RIFF"u8); w.Write(36 + bytes); w.Write("WAVE"u8);
        w.Write("fmt "u8); w.Write(16); w.Write((short)3); w.Write((short)2); w.Write(44100); w.Write(44100 * 8); w.Write((short)8); w.Write((short)32);
        w.Write("data"u8); w.Write(bytes);
        foreach (var v in stereo) w.Write(v);
    }

    private static float[] Sum(IEnumerable<float[]> parts, int length)
    {
        var sum = new float[length];
        foreach (var p in parts) for (int i = 0; i < length; i++) sum[i] += p[i];
        return sum;
    }

    private static string Slug(string name) => name.Replace("♭", "b").Replace(' ', '-').ToLowerInvariant();

    private static double End(JsonElement notes) => notes.EnumerateArray().Max(n => n[1].GetDouble());

    /// <summary>Largest difference between a one-synth mix and the sum of the same parts rendered alone, in dB below the mix, per 50 ms.</summary>
    private static (double WorstDb, double AtS) MixResidual(float[] mix, IEnumerable<float[]> solos)
    {
        var sum = new double[mix.Length];
        foreach (var s in solos) for (int i = 0; i < mix.Length; i++) sum[i] += s[i];
        int w = 2 * 2205;
        double worst = double.NegativeInfinity, at = 0;
        for (int a = 0; a + w <= mix.Length; a += w)
        {
            double e = 0, d = 0;
            for (int i = a; i < a + w; i++) { e += mix[i] * (double)mix[i]; d += (mix[i] - sum[i]) * (mix[i] - sum[i]); }
            if (e < 1e-8) continue;
            double r = 10 * Math.Log10(d / e + 1e-20);
            if (r > worst) { worst = r; at = a / 2 / 44100.0; }
        }
        return (worst, at);
    }

    [Fact]
    public void Sound_check_renders_the_test_phrases_through_alphaSynth()
    {
        var outDir = Environment.GetEnvironmentVariable("BRASSCRIBE_SOUNDCHECK_OUT");
        var sf2Path = Environment.GetEnvironmentVariable("BRASSCRIBE_SOUNDCHECK_SF2") is { Length: > 0 } p ? p : TestPaths.RepoFile(BandSf2);
        var phrases = TestPaths.RepoFile("data/sounds/phrases/phrases.json");
        if (string.IsNullOrEmpty(outDir) || sf2Path is null || phrases is null || Mapping is null) return;
        Directory.CreateDirectory(outDir);
        var sf2 = File.ReadAllBytes(sf2Path);
        var band = BandSoundFont.Load(Mapping);
        using var doc = JsonDocument.Parse(File.ReadAllText(phrases));

        // 1. Every part alone on channel 0 at unity channel volume (the raw preset, like fluid-band).
        foreach (var part in doc.RootElement.GetProperty("parts").EnumerateObject())
        {
            var s = band.For(part.Name)!;
            var notes = part.Value.GetProperty("notes");
            var audio = Render(sf2, Phrase([(0, s.Program, s.Bank, notes)]), End(notes) + 2.0);
            WriteWav(Path.Combine(outDir, Slug(part.Name) + ".wav"), audio);
        }

        // 2. The full band through one synth with the app's channel plan and balance, against the
        //    sum of each part rendered alone: stolen or dropped voices show as a residual.
        var bandParts = doc.RootElement.GetProperty("band").EnumerateObject().ToList();
        var plan = ChannelPlan.ForPlayback(bandParts.Select((b, i) =>
        {
            var s = band.For(b.Name)!;
            return new ChannelPlan.Part(i, s.Percussion, s.Program, s.GainDb);
        }).ToList());
        var gains = new Dictionary<int, double>();
        var rows = new List<(int, int, int, JsonElement)>();
        for (int i = 0; i < bandParts.Count; i++)
        {
            var s = band.For(bandParts[i].Name)!;
            gains[plan[i]] = Math.Pow(10, s.GainDb / 20);
            rows.Add((plan[i], s.Percussion ? 0 : s.Program, s.Bank, bandParts[i].Value.GetProperty("notes")));
        }
        double len = rows.Max(r => End(r.Item4)) + 2.0;
        var mix = Render(sf2, Phrase(rows), len, gains);
        WriteWav(Path.Combine(outDir, "band.wav"), mix);
        var solos = rows.Select(r => Render(sf2, Phrase([r]), len, gains)).ToList();
        var (worst, at) = MixResidual(mix, solos);
        WriteWav(Path.Combine(outDir, "band-sum-of-solos.wav"), Sum(solos, mix.Length));
        log.WriteLine($"band: {bandParts.Count} parts on channels {string.Join(",", plan)}; mix vs sum of solos worst residual {worst:0.0} dB at {at:0.00} s; peak {mix.Max(Math.Abs):0.000}");
        File.WriteAllText(Path.Combine(outDir, "band.json"), JsonSerializer.Serialize(new { channels = plan, residual_db = worst, residual_at_s = at, peak = mix.Max(Math.Abs) }));

        // 3. Unison: two parts on the same pitch with staggered note-offs, on their playback channels.
        var sc = band.For("Solo Cornet")!;
        var rep = band.For("Repiano Cornet")!;
        var unison = Phrase([
            (0, sc.Program, sc.Bank, JsonDocument.Parse("[[0.5, 3.0, 70, 80]]").RootElement),
            (1, rep.Program, rep.Bank, JsonDocument.Parse("[[1.0, 2.0, 70, 80], [2.0, 2.5, 70, 80]]").RootElement)]);
        var u = Render(sf2, unison, 4.0);
        var uA = Render(sf2, Phrase([(0, sc.Program, sc.Bank, JsonDocument.Parse("[[0.5, 3.0, 70, 80]]").RootElement)]), 4.0);
        var uB = Render(sf2, Phrase([(1, rep.Program, rep.Bank, JsonDocument.Parse("[[1.0, 2.0, 70, 80], [2.0, 2.5, 70, 80]]").RootElement)]), 4.0);
        var (uw, uat) = MixResidual(u, [uA, uB]);
        WriteWav(Path.Combine(outDir, "unison.wav"), u);
        WriteWav(Path.Combine(outDir, "unison-sum-of-solos.wav"), Sum([uA, uB], u.Length));
        log.WriteLine($"unison: mix vs sum of solos worst residual {uw:0.0} dB at {uat:0.00} s");
        File.WriteAllText(Path.Combine(outDir, "unison.json"), JsonSerializer.Serialize(new { residual_db = uw, residual_at_s = uat }));
    }
}
