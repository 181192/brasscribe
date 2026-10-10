using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Tests;

public class ScoreNavigatorTests
{
    /// <summary>The fixture's Norwegian part names, as the core's table gives them.</summary>
    internal static string FixtureNb(string name) => name switch
    {
        "Solo Cornet" => "Solokornett",
        "Solo Horn" => "Solo althorn",
        "Percussion" => "Slagverk",
        _ => name,
    };

    private static TalkingScoreDocument Doc() =>
        MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), nameNb: FixtureNb);

    [Fact]
    public void Builder_reads_parts_transposition_and_spelling()
    {
        var doc = Doc();
        Assert.Equal("Test tune", doc.Title);
        Assert.Equal(5, doc.TotalBars);
        Assert.Equal(["Solo Cornet", "Solo Horn", "Percussion"], doc.Parts.Select(p => p.Name));
        Assert.Equal("Solo althorn", doc.Parts[1].NameNb);
        Assert.Equal("althorn i Ess", doc.Parts[1].InstrumentNb);
        var bflat = doc.Parts[0].Bars[0].Events[1];
        Assert.Equal(new TsPitch("A", -1, 4), bflat.Concert);
        Assert.Equal(MusicXmlTalkingScoreBuilder.ColourOnlyConfidence, bflat.Confidence);
        Assert.Equal(new TsPitch("G", 0, 4), doc.Parts[1].Bars[0].Events[0].Concert); // E5 on an E-flat horn sounds G4
        Assert.True(doc.Parts[2].Percussion);
        Assert.Equal(136, doc.Parts[0].Bars[0].TempoBpm);
    }

    [Fact]
    public void Concert_spelling_keeps_the_diatonic_step()
    {
        Assert.Equal(new TsPitch("E", -1, 5), MusicXmlTalkingScoreBuilder.ToConcert(new("F", 0, 5), new TsTranspose(-2, -1)));
        Assert.Equal(new TsPitch("B", -1, 2), MusicXmlTalkingScoreBuilder.ToConcert(new("C", 0, 4), new TsTranspose(-2, -1, -1)));
    }

    [Fact]
    public void Notes_skip_tie_continuations_and_bars_collapse_rests()
    {
        var nav = new ScoreNavigator(Doc());
        Assert.Equal("bar 1, tempo 136, beat 1: quarter rest", nav.Text);
        Assert.Equal("beat 2: B-flat 4, eighth note, uncertain", nav.NextNote().Text);
        Assert.Equal("beat 2 and: C-natural 5, eighth note", nav.NextNote().Text);
        Assert.Equal("beat 3: G 5, half note, tied to dotted quarter note in bar 2", nav.NextNote().Text);
        Assert.Equal("bar 2, beat 2 and: F-sharp 4, eighth note, accent", nav.NextNote().Text);
        Assert.Equal("beat 3: E 4, half note", nav.NextBeat().Text);
        Assert.Equal("beat 2: G 5 held, from bar 1 beat 3", nav.PreviousBeat().Text);
        Assert.Equal("bars 3 to 4: rest, 2 bars", nav.NextBar().Text);
        Assert.Equal("bar 5, key 3 sharps, beat 1: C-sharp 5, whole note", nav.NextBar().Text);
        Assert.False(nav.NextNote().Moved);
        Assert.Equal("bars 3 to 4: rest, 2 bars", nav.PreviousNote().Text);
    }

    [Fact]
    public void Parts_keep_the_time_position()
    {
        var nav = new ScoreNavigator(Doc());
        nav.GoToBar(1);
        Assert.Equal("Solo Horn. bar 1, beat 1: E 5, half note", nav.NextPart().Text);
        Assert.Equal("beat 3: C-sharp 5, eighth note, triplet, 1 of 3", nav.NextNote().Text);
        Assert.Equal("beat 3, triplet 2: D 5, eighth note, triplet, 2 of 3", nav.NextNote().Text);
        nav.GoToPart(2);
        Assert.Equal("Percussion. bar 1, beat 3, triplet 2: double-dotted half rest", nav.Text);
        nav.FirstBar();
        Assert.Equal("bar 1, tempo 136, beat 1: bass drum and hi-hat, eighth note", nav.Text); // tempo marks are shared by all parts
        Assert.False(nav.NextPart().Moved);
    }

    [Fact]
    public void Uncertain_notes_and_checking()
    {
        var nav = new ScoreNavigator(Doc());
        Assert.Equal(1, nav.UncertainCount);
        Assert.Equal("beat 2: B-flat 4, eighth note, uncertain", nav.NextUncertain().Text);
        Assert.Equal(0, nav.MarkChecked());
        Assert.Equal("beat 2: B-flat 4, eighth note", nav.Text);
        Assert.False(nav.NextUncertain().Moved);
    }

    [Fact]
    public void Read_bar_where_am_i_and_pitch_mode()
    {
        var nav = new ScoreNavigator(Doc());
        Assert.StartsWith("bar 1: 1: quarter rest, 2: B-flat 4 eighth, uncertain, 2 and: C-natural 5 eighth", nav.ReadBar());
        nav.NextNote();
        Assert.Equal("bar 1 of 5, tempo 136, beat 2: written B-flat 4, sounds A-flat 4, eighth note, uncertain, confidence 55 percent", nav.WhereAmI());
        Assert.Equal("Concert pitch", nav.SetPitchMode(PitchMode.Concert));
        Assert.Equal("beat 2 and: B-flat 4, eighth note", nav.NextNote().Text);
        Assert.Equal("There is no bar 99", nav.GoToBar(99).Text);
    }

    [Fact]
    public void Norwegian_navigation()
    {
        var nav = new ScoreNavigator(Doc(), new TalkingScoreSettings("nb"));
        nav.NextNote();
        nav.NextNote();
        Assert.Equal("slag 3: G 5, halvnote, bundet til punktert fjerdedelsnote i takt 2", nav.NextNote().Text);
        Assert.Equal("Solo althorn. takt 1, slag 3: Ciss 5, åttendedelsnote, triol, 1 av 3", nav.NextPart().Text);
    }

    [Fact]
    public void Composition_supplies_confidence_sources_and_time()
    {
        // Tick 0 is the start of bar 1; the B-flat 4 (concert A-flat 4 = 68) sits on beat 2.
        var c = CompositionJson.Parse("""
        {"title":"t","meters":[{"tick":0,"beats":4}],"keys":[{"tick":0,"fifths":0}],"beat_times":[1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0],
         "voices":[{"id":"solo","role":"melody","notes":[{"pitch":68,"start":24,"dur":12,"confidence":0.31,"sources":["swiftf0"],"onset_s":1.52,"offset_s":1.7}]}]}
        """);
        var doc = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), c);
        var ev = doc.Parts[0].Bars[0].Events[1];
        Assert.Equal(0.31, ev.Confidence);
        Assert.Equal(["swiftf0"], ev.Sources);
        Assert.Equal(1.52, ev.TimeS);
        Assert.Equal(1.75, doc.Parts[0].Bars[0].Events[2].TimeS!.Value, 6); // beat 2 and = beat 1.5 of the map
        var nav = new ScoreNavigator(doc);
        Assert.Equal("beat 2: B-flat 4, eighth note, very uncertain", nav.NextNote().Text);
    }

    [SkippableFact]
    public void Golden_score_builds_with_confidence_from_the_composition()
    {
        var xml = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        Skip.If(xml is null, TestPaths.Missing(TestPaths.GoldenMusicXml));
        Skip.If(json is null, TestPaths.Missing(TestPaths.GoldenComposition));
        var doc = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(xml), CompositionJson.Parse(File.ReadAllText(json)));
        Assert.Equal(18, doc.Parts.Count);
        Assert.True(doc.TotalBars > 100);
        var solo = doc.Parts.Single(p => p.Name == "Solo Cornet");
        Assert.Equal(new TsTranspose(-2, -1), solo.Transpose);
        var notes = solo.Bars.SelectMany(b => b.Events).Where(e => e.Kind == EventKind.Note).ToList();
        Assert.True(notes.Count > 300);
        double withSources = notes.Count(n => n.Sources.Count > 0) / (double)notes.Count;
        Assert.True(withSources > 0.8, $"only {withSources:P0} of solo notes matched the Composition");
        var nav = new ScoreNavigator(doc);
        nav.GoToPart(doc.Parts.IndexOf(solo));
        Assert.True(nav.NextUncertain().Moved);

        // Free-time passages from the Composition map onto bars and change the announcements.
        var composition = CompositionJson.Parse(File.ReadAllText(json));
        Assert.Equal(composition.FreeRegions.Count, doc.FreeRegions.Count);
        if (doc.FreeRegions.FirstOrDefault() is { } region)
        {
            Assert.Equal(1, region.StartBar);
            var first = new ScoreNavigator(doc); // the first announcement enters the region
            int seconds = (int)Math.Round(region.EndS - region.StartS, MidpointRounding.AwayFromZero);
            Assert.True(first.Text.StartsWith($"Ad lib, free time, bars 1 to {region.EndBar}, about {seconds} seconds. "), first.Text);
            first.GoToPart(doc.Parts.IndexOf(solo));
            var inside = first.NextNote();
            Assert.Matches("^at \\d+ seconds: ", inside.Text); // performed time, not beats, inside the region
            first.GoToBar(region.EndBar + 1);
            Assert.StartsWith("A tempo, ", first.Text);
        }
    }

    [Fact]
    public void Positions_in_compound_time_say_so_whole_bar_rests_included()
    {
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"))
            .Replace("<beats>4</beats><beat-type>4</beat-type>", "<beats>12</beats><beat-type>8</beat-type>");
        var bars = MusicXmlTalkingScoreBuilder.Build(xml, nameNb: FixtureNb).Parts[0].Bars;
        Assert.Equal(new TsPos(1, Compound: true), bars[0].Events[0].Pos);
        Assert.Equal(EventKind.BarRest, bars[2].Events[0].Kind);
        Assert.Equal(new TsPos(1, Compound: true), bars[2].Events[0].Pos);
    }

    private const string Pickup = """
        <?xml version="1.0" encoding="UTF-8"?>
        <score-partwise version="4.0"><work><work-title>Pickup</work-title></work>
        <part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part><score-part id="P2"><part-name>2nd Horn</part-name></score-part></part-list>
        <part id="P1">
        <measure number="0" implicit="yes"><attributes><divisions>2</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
        <note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
        <note><pitch><step>A</step><octave>4</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type><tie type="start"/></note></measure>
        <measure number="1"><note><pitch><step>A</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type><tie type="stop"/></note></measure>
        <measure number="2"><note><pitch><step>C</step><octave>5</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type></note></measure>
        </part>
        <part id="P2">
        <measure number="0" implicit="yes"><attributes><divisions>2</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
        <note><rest measure="yes"/><duration>3</duration><voice>1</voice></note></measure>
        <measure number="1"><note><rest measure="yes"/><duration>8</duration><voice>1</voice></note></measure>
        <measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type></note></measure>
        </part></score-partwise>
        """;

    [Fact]
    public void A_pickup_is_named_and_its_notes_sit_on_the_beats_of_the_bar_they_lead_into()
    {
        var doc = MusicXmlTalkingScoreBuilder.Build(Pickup, nameNb: FixtureNb);
        Assert.Equal(2, doc.TotalBars); // the pickup is not one of the bars counted
        var pickup = doc.Parts[0].Bars[0];
        Assert.Equal(0, pickup.Number);
        Assert.Equal([0, MusicXmlTalkingScoreBuilder.TicksPerQuarter / 2], pickup.Events.Select(e => e.Tick));
        Assert.Equal([new TsPos(3, 1, 2), new TsPos(4)], pickup.Events.Select(e => e.Pos));

        var nav = new ScoreNavigator(doc);
        Assert.Equal("pickup, beat 3 and: G 4, eighth note", nav.Text);
        Assert.Equal("beat 4: A 4, quarter note, tied to whole note in bar 1", nav.NextNote().Text);
        // By beat: the pickup's beats are those of the bar it leads into.
        Assert.Equal("bar 1, beat 1: A 4 held, from pickup beat 4", nav.NextBeat().Text);
        Assert.Equal("pickup, beat 4: A 4, quarter note, tied to whole note in bar 1", nav.PreviousBeat().Text);
        Assert.False(nav.PreviousBeat().Moved); // beat 3 is before the pickup starts
        Assert.Equal("bar 2, beat 1: C 5, whole note", nav.NextNote().Text);

        var text = TalkingScoreExport.ToText(doc, new TalkingScoreSettings());
        Assert.Contains("Pickup\n  pickup, beat 3 and: G 4, eighth note\n", text);
        Assert.Contains("Pickup and bar 1\n  pickup and bar 1: rest\n", text);
        Assert.DoesNotContain("ar 0", text);
        var nb = TalkingScoreExport.ToText(doc, new TalkingScoreSettings("nb"));
        Assert.Contains("Opptakt\n  opptakt, slag 3-og: G 4, åttendedelsnote\n", nb);
        Assert.Contains("Opptakt og takt 1\n  opptakt og takt 1: pause\n", nb);

        // A first measure left out of the numbering is the pickup too.
        var unnumbered = MusicXmlTalkingScoreBuilder.Build(Pickup.Replace("number=\"0\" implicit=\"yes\"", "number=\"X1\" implicit=\"yes\""), nameNb: FixtureNb);
        Assert.Equal(0, unnumbered.Parts[0].Bars[0].Number);
    }
}
