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
    private const string BankedScore = "data/runs/sound/band-sf2/brass-band.banks.musicxml";

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
            bool hasNotes = player.Score!.Tracks[track.Index].Staves.SelectMany(st => st.Bars).SelectMany(b => b.Voices)
                .SelectMany(v => v.Beats).Any(b => b.Notes.Count > 0);
            result.Add((track.Name, Math.Sqrt(sum / n), hasNotes, track.IsPercussion));
        }
        return [.. result];
    }

    private void Report(string label, (string Track, double Rms, bool HasNotes, bool Percussion)[] levels) =>
        log.WriteLine($"{label}: " + string.Join("; ", levels.Select(l => $"{l.Track} {l.Rms:0.0000}")));

    [Fact]
    public void Golden_score_plays_every_part_from_the_band_soundfont_by_program_alone()
    {
        var sf2 = TestPaths.RepoFile(BandSf2);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (sf2 is null || golden is null) return;
        var levels = SoloLevels(File.ReadAllBytes(sf2), File.ReadAllBytes(golden));
        Report("programs only", levels);
        // Percussion is checked separately: the golden score's unpitched notes carry no
        // <midi-unpitched> mapping, so alphaTab sends them all as MIDI note 0 (silent in any kit).
        Assert.Empty(levels.Where(l => l.HasNotes && !l.Percussion && l.Rms < 1e-4).Select(l => l.Track));
    }

    [Fact]
    public void Banked_score_plays_every_part_and_banks_select_distinct_presets()
    {
        var sf2 = TestPaths.RepoFile(BandSf2);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var banked = TestPaths.RepoFile(BankedScore);
        if (sf2 is null || golden is null || banked is null) return;
        var bytes = File.ReadAllBytes(sf2);
        // The golden score now carries <midi-bank> itself, so "plain" is the golden with the banks removed.
        var withoutBanks = System.Text.RegularExpressions.Regex.Replace(File.ReadAllText(golden), @"<midi-bank>\d+</midi-bank>", "");
        var plain = SoloLevels(bytes, System.Text.Encoding.UTF8.GetBytes(withoutBanks));
        var withBanks = SoloLevels(bytes, File.ReadAllBytes(banked));
        Report("with midi-bank", withBanks);
        Assert.Empty(withBanks.Where(l => l.HasNotes && !l.Percussion && l.Rms < 1e-4).Select(l => l.Track));
        // Flugelhorn is program 56 bank 5 (flugel samples); without the bank it gets bank 0 (cornets).
        var a = plain.Single(l => l.Track.StartsWith("Flugel", StringComparison.Ordinal)).Rms;
        var b = withBanks.Single(l => l.Track.StartsWith("Flugel", StringComparison.Ordinal)).Rms;
        log.WriteLine($"Flugelhorn rms without bank {a:0.00000}, with bank {b:0.00000}");
        Assert.True(Math.Abs(20 * Math.Log10(b / a)) > 0.5, "midi-bank did not change the Flugelhorn preset");
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
