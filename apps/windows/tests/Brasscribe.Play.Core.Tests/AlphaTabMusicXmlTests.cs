using System.Text;
using System.Xml.Linq;
using AlphaTab.Midi;
using Brasscribe.Play.Core.Playback;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// alphaTab's MusicXML fixes (<see cref="AlphaTabMusicXml"/>): ties in transposing parts sound once, a note whose
/// tie start comes before its stop loads, and trills alternate with the written auxiliary. The fixture is
/// apps/fixtures/ties-and-trills.musicxml (make-ties-and-trills.py), at 60 bpm, a quarter a second.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class AlphaTabMusicXmlTests
{
    private const string Fixture = "apps/fixtures/ties-and-trills.musicxml";

    /// <summary>The notes the player sounds: (track, start s, end s, key).</summary>
    internal static List<(int Track, double Start, double End, int Key)> Played(byte[] musicXml)
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(musicXml);
        var midi = player.PlaybackMidi!;
        var tempos = midi.Events.OfType<TempoChangeEvent>().OrderBy(e => e.Tick).ToList();
        double Seconds(double tick)
        {
            double sec = 0, at = 0, us = 500000;
            foreach (var t in tempos.TakeWhile(t => t.Tick <= tick))
            {
                sec += (t.Tick - at) / midi.Division * us / 1e6;
                at = t.Tick;
                us = t.MicroSecondsPerQuarterNote;
            }
            return sec + (tick - at) / midi.Division * us / 1e6;
        }
        var track = player.TrackChannels.Select((c, i) => (c, i)).ToDictionary(x => x.c, x => x.i);
        var open = new Dictionary<(int, int), Queue<double>>();
        var notes = new List<(int, double, double, int)>();
        foreach (var e in midi.Events.OfType<NoteEvent>().OrderBy(e => e.Tick).ThenBy(e => e is NoteOnEvent { NoteVelocity: > 0 } ? 1 : 0))
        {
            var key = ((int)e.Channel, (int)e.NoteKey);
            if (e is NoteOnEvent { NoteVelocity: > 0 })
            {
                if (!open.TryGetValue(key, out var q)) open[key] = q = new();
                q.Enqueue(e.Tick);
            }
            else if (open.TryGetValue(key, out var q) && q.Count > 0)
                notes.Add((track.GetValueOrDefault(key.Item1, -1), Seconds(q.Dequeue()), Seconds(e.Tick), key.Item2));
        }
        return notes.OrderBy(n => n.Item1).ThenBy(n => n.Item2).ToList();
    }

    private static byte[] Read(string relative)
    {
        var path = TestPaths.RepoFile(relative);
        Skip.If(path is null, TestPaths.Missing(relative));
        return File.ReadAllBytes(path!);
    }

    [SkippableFact]
    public void Ties_sound_once_in_transposing_and_concert_parts()
    {
        var notes = Played(Read(Fixture));
        // bars 1-3: a tie in the bar, then a chain over the barline (Flugelhorn: its middle note's start before its stop)
        Assert.Equal([(0.0, 3.0, 72), (3.0, 4.0, 74), (4.0, 5.0, 70), (5.0, 6.0, 65), (6.0, 11.0, 67)],
            notes.Where(n => n.Track == 0 && n.Start < 12).Select(n => (n.Start, n.End, n.Key)));
        Assert.Equal([(0.0, 4.0, 70)], notes.Where(n => n.Track == 1 && n.Start < 12).Select(n => (n.Start, n.End, n.Key)));
        Assert.Equal([(0.0, 3.0, 50), (3.0, 4.0, 52), (4.0, 5.0, 48), (5.0, 6.0, 43), (6.0, 11.0, 45)],
            notes.Where(n => n.Track == 2 && n.Start < 12).Select(n => (n.Start, n.End, n.Key)));
    }

    public static TheoryData<int, double, double, int, int> FixtureTrills => new()
    {
        // track, start, end, main key, auxiliary key (sounding)
        { 0, 12, 16, 74, 75 }, { 0, 16, 20, 72, 74 }, { 0, 20, 24, 74, 76 }, { 0, 24, 28, 67, 68 }, { 0, 28, 34, 65, 67 },
        { 1, 12, 16, 67, 68 },
        { 2, 12, 16, 52, 53 }, { 2, 16, 20, 50, 52 }, { 2, 20, 24, 52, 54 }, { 2, 24, 28, 45, 46 }, { 2, 28, 34, 43, 45 },
    };

    [SkippableTheory]
    [MemberData(nameof(FixtureTrills))]
    public void Trills_alternate_with_the_written_auxiliary(int track, double start, double end, int main, int aux)
    {
        var trill = Played(Read(Fixture)).Where(n => n.Track == track && n.Start >= start && n.Start < end).ToList();
        Assert.Equal([main, aux], trill.Select(n => n.Key).Distinct().Order());
        Assert.Equal(main, trill[0].Key);
        Assert.Equal(end, trill[^1].End, 3);
        Assert.Equal(0.125, trill[1].Start - trill[0].Start, 3); // alphaTab's 32nds
    }

    [Fact]
    public void Ties_are_numbered_stop_first_and_numbers_kept()
    {
        string Part(params string[] notes) => "<part id=\"P1\">" + string.Concat(notes) + "</part>";
        string Note(string step, params string[] tied) =>
            $"<note><pitch><step>{step}</step><octave>5</octave></pitch><notations>{string.Concat(tied)}</notations></note>";
        string outp = AlphaTabMusicXml.NumberTies(Part(
            Note("D", "<tied type=\"start\" />"),
            Note("D", "<tied type=\"start\" />", "<tied type=\"stop\" />"),
            Note("D", "<tied type=\"stop\" />"),
            Note("E", "<tied type=\"start\" number=\"3\" />"),
            Note("E", "<tied type=\"stop\" number=\"3\" />")));
        Assert.Equal(Part(
            Note("D", "<tied number=\"1\" type=\"start\" />"),
            Note("D", "<tied number=\"1\" type=\"stop\" />", "<tied number=\"1\" type=\"start\" />"),
            Note("D", "<tied number=\"1\" type=\"stop\" />"),
            Note("E", "<tied type=\"start\" number=\"3\" />"),
            Note("E", "<tied type=\"stop\" number=\"3\" />")), outp);
    }

    /// <summary>
    /// The golden arrangement as saved before the ties were numbered: every pitched part sounds each tie chain
    /// once, so its notes are the score's notes less its tie stops. Before the fix alphaTab sounded the Solo
    /// Cornet 1146 s in all (the score has 195 s), from notes held into the next phrase.
    /// </summary>
    [SkippableFact]
    public void Golden_plays_each_tie_chain_once()
    {
        var bytes = Read(TestPaths.GoldenMusicXml);
        var played = Played(bytes);
        var doc = XDocument.Parse(Encoding.UTF8.GetString(bytes));
        int track = 0;
        foreach (var part in doc.Root!.Elements("part"))
        {
            var notes = part.Descendants("note").Where(n => n.Element("pitch") is not null && n.Element("grace") is null).ToList();
            int chains = notes.Count(n => !n.Elements("tie").Any(t => (string?)t.Attribute("type") == "stop"));
            if (notes.Count > 0) Assert.True(chains == played.Count(p => p.Track == track), $"part {track + 1}: {chains} chains, {played.Count(p => p.Track == track)} played");
            track++;
        }
    }
}
