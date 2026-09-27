using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The single band SoundFont (sounds/band.py → data/sounds/band/brasscribe-band.sf2) in alphaTab:
/// every part has its own preset at (bank, GM program), drums at bank 128. Skips when the file or
/// the golden score is not in the checkout.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class BandSoundFontTests(ITestOutputHelper log)
{
    private const string BandSf2 = "data/sounds/band/brasscribe-band.sf2";

    private static (string Track, double Rms, bool HasNotes, bool Percussion)[] SoloLevels(byte[] sf2, byte[] score)
    {
        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        player.LoadSoundFont(sf2);
        player.LoadScore(score);
        Assert.True(player.IsReady, player.LoadError?.Message);
        var result = new List<(string, double, bool, bool)>();
        foreach (var track in player.Tracks)
        {
            foreach (var t in player.Tracks) player.SetSolo(t.Index, t.Index == track.Index);
            // from bar 20, or the track's first bar with notes after that (the drums enter at bar 36)
            var bars = player.Score!.Tracks[track.Index].Staves[0].Bars;
            int start = Enumerable.Range(19, Math.Max(0, bars.Count - 19))
                .FirstOrDefault(i => bars[i].Voices.Any(v => v.Beats.Any(b => b.Notes.Count > 0)), 19);
            player.SeekToBar(start);
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
            bool hasNotes = player.Score!.Tracks[track.Index].Staves.SelectMany(st => st.Bars).SelectMany(b => b.Voices)
                .SelectMany(v => v.Beats).Any(b => b.Notes.Count > 0);
            result.Add((track.Name, Math.Sqrt(sum / n), hasNotes, track.IsPercussion));
        }
        return [.. result];
    }

    private void Report(string label, (string Track, double Rms, bool HasNotes, bool Percussion)[] levels) =>
        log.WriteLine($"{label}: " + string.Join("; ", levels.Select(l => $"{l.Track} {l.Rms:0.0000}")));

    [Fact]
    public void Golden_score_plays_every_part_and_the_drums_from_the_band_soundfont()
    {
        var sf2 = TestPaths.RepoFile(BandSf2);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (sf2 is null || golden is null) return;
        var levels = SoloLevels(File.ReadAllBytes(sf2), File.ReadAllBytes(golden));
        Report("programs only", levels);
        Assert.Empty(levels.Where(l => l.HasNotes && l.Rms < 1e-4).Select(l => l.Track));
    }

    /// <summary>The first 3 s from bar 20 of one track played solo, as interleaved stereo samples.</summary>
    private static float[] SoloAudio(byte[] sf2, byte[] score, string trackPrefix)
    {
        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        player.LoadSoundFont(sf2);
        player.LoadScore(score);
        Assert.True(player.IsReady, player.LoadError?.Message);
        var track = player.Tracks.Single(t => t.Name.StartsWith(trackPrefix, StringComparison.Ordinal));
        foreach (var t in player.Tracks) player.SetSolo(t.Index, t.Index == track.Index);
        player.SeekToBar(19);
        player.Play();
        var all = new List<float>();
        var buffer = new float[2 * 1024];
        for (int i = 0; i < 44100 * 3 / 1024; i++)
        {
            output.Read(buffer);
            all.AddRange(buffer);
        }
        player.Pause();
        return [.. all];
    }

    private static double RelativeDifference(float[] a, float[] b)
    {
        double d = 0, r = 0;
        for (int i = 0; i < Math.Min(a.Length, b.Length); i++)
        {
            d += (a[i] - b[i]) * (a[i] - b[i]);
            r += a[i] * a[i];
        }
        return Math.Sqrt(d / Math.Max(r, 1e-20));
    }

    [Fact]
    public void Midi_bank_selects_the_part_preset_within_a_program()
    {
        // Without a part map (BandSoundFont.ApplyTo), the player plays the score's own
        // <midi-program>/<midi-bank>. The presets are level-matched (sounds/build.py), so the level
        // no longer tells bank 5 (flugel) from bank 0 (cornets); the waveform does.
        var sf2 = TestPaths.RepoFile(BandSf2);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (sf2 is null || golden is null) return;
        var xml = File.ReadAllText(golden);
        if (!xml.Contains("<midi-bank>", StringComparison.Ordinal)) return; // score written before banks
        var bytes = File.ReadAllBytes(sf2);
        var utf8 = System.Text.Encoding.UTF8;
        var withBanks = SoloAudio(bytes, utf8.GetBytes(xml), "Flugel");
        var noBanks = SoloAudio(bytes, utf8.GetBytes(
            System.Text.RegularExpressions.Regex.Replace(xml, @"\s*<midi-bank>\d+</midi-bank>", "")), "Flugel");
        double d = RelativeDifference(withBanks, noBanks);
        log.WriteLine($"Flugelhorn with vs without midi-bank: relative difference {d:0.000}");
        Assert.True(d > 0.3, "midi-bank did not change the Flugelhorn preset");
    }

    /// <summary>A percussion part written with score-instrument + midi-unpitched per drum (GM numbers, 1-based).</summary>
    private const string DrumScore = """
        <?xml version="1.0" encoding="UTF-8"?>
        <score-partwise version="4.0">
          <part-list>
            <score-part id="P1"><part-name>Percussion</part-name>
              <score-instrument id="P1-I36"><instrument-name>Bass Drum</instrument-name></score-instrument>
              <score-instrument id="P1-I38"><instrument-name>Snare</instrument-name></score-instrument>
              <score-instrument id="P1-I42"><instrument-name>Closed Hi-Hat</instrument-name></score-instrument>
              <midi-instrument id="P1-I36"><midi-channel>10</midi-channel><midi-program>1</midi-program><midi-unpitched>37</midi-unpitched></midi-instrument>
              <midi-instrument id="P1-I38"><midi-channel>10</midi-channel><midi-program>1</midi-program><midi-unpitched>39</midi-unpitched></midi-instrument>
              <midi-instrument id="P1-I42"><midi-channel>10</midi-channel><midi-program>1</midi-program><midi-unpitched>43</midi-unpitched></midi-instrument>
            </score-part>
          </part-list>
          <part id="P1">
            <measure number="1">
              <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>percussion</sign></clef></attributes>
              <note><unpitched><display-step>F</display-step><display-octave>4</display-octave></unpitched><duration>1</duration><instrument id="P1-I36"/><type>quarter</type></note>
              <note><unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched><duration>1</duration><instrument id="P1-I38"/><type>quarter</type></note>
              <note><unpitched><display-step>G</display-step><display-octave>5</display-octave></unpitched><duration>1</duration><instrument id="P1-I42"/><type>quarter</type><notehead>x</notehead></note>
              <note><unpitched><display-step>F</display-step><display-octave>4</display-octave></unpitched><duration>1</duration><instrument id="P1-I36"/><type>quarter</type></note>
            </measure>
          </part>
        </score-partwise>
        """;

    [Fact]
    public void Drum_kit_on_bank_128_sounds_for_unpitched_notes_with_midi_unpitched()
    {
        var sf2 = TestPaths.RepoFile(BandSf2);
        if (sf2 is null) return;
        var output = new BufferedSynthOutput();
        using var player = new AlphaTabScorePlayer(output);
        player.LoadSoundFont(File.ReadAllBytes(sf2));
        player.LoadScore(System.Text.Encoding.UTF8.GetBytes(DrumScore.Trim()));
        Assert.True(player.IsReady, player.LoadError?.Message);
        player.Play();
        var buffer = new float[2 * 1024];
        double sum = 0;
        long n = 0;
        for (int i = 0; i < 44100 * 2 / 1024; i++)
        {
            output.Read(buffer);
            foreach (var v in buffer) sum += v * v;
            n += buffer.Length;
        }
        player.Pause();
        double rms = Math.Sqrt(sum / n);
        log.WriteLine($"drum kit rms over 2 s: {rms:0.00000}");
        Assert.True(rms > 1e-4, "bank 128 drum kit is silent");
    }
}
