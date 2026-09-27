using System.Text.Json.Nodes;
using System.Xml.Linq;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>The three lineups (full band, small band, quartet): names on every side, the solo gate, the core.</summary>
[Collection(AlphaTabCollection.Name)]
public class LineupTests
{
    private sealed class Announcements : IAnnouncer
    {
        public List<(string Text, AnnouncementKind Kind)> Items { get; } = [];
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Items.Add((text, kind));
    }

    private static IStrings Strings(string lang = "en-US") => new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", lang, "Resources.resw"))));

    [Fact]
    public void Every_lineup_has_an_engine_and_a_core_name_and_the_quartet_is_never_the_band()
    {
        var engine = new Dictionary<Lineup, string> { [Lineup.FullBand] = "full", [Lineup.MinimalBand] = "minimal", [Lineup.Quartet] = "quartet" };
        var core = new Dictionary<Lineup, string> { [Lineup.FullBand] = "band", [Lineup.MinimalBand] = "minimal", [Lineup.Quartet] = "quartet" };
        foreach (var lineup in Enum.GetValues<Lineup>())
        {
            Assert.Equal(engine[lineup], Lineups.Engine(lineup));
            Assert.Equal(core[lineup], Lineups.Core(lineup));
            Assert.Equal(lineup, Lineups.Parse(Lineups.Engine(lineup)));
            Assert.Equal(lineup, Lineups.Parse(Lineups.Core(lineup)));
        }
        Assert.DoesNotContain(Lineups.Engine(Lineup.Quartet), new[] { "full", "band" });
        Assert.DoesNotContain(Lineups.Core(Lineup.Quartet), new[] { "full", "band" });
        Assert.Null(Lineups.Parse("quintet"));
        Assert.Throws<ArgumentException>(() => Lineups.Of(new ArrangementOptions("quintet")));
    }

    [Fact]
    public void The_options_reach_the_engine_and_the_core_as_quartet()
    {
        var vm = new OutputOptionsViewModel(new ManagedCoreBridge(), new Announcements(), Strings()) { Lineup = Lineup.Quartet };
        Assert.Equal("quartet", vm.Options.Lineup);
        var arrange = JsonNode.Parse(NativeCoreBridge.ArrangeOptions(new ArrangementOptions("quartet", "easier")))!;
        Assert.Equal("quartet", arrange["lineup"]!.GetValue<string>());
        Assert.Equal("easier", arrange["difficulty"]!.GetValue<string>());
        Assert.Equal("band", JsonNode.Parse(NativeCoreBridge.ArrangeOptions(new ArrangementOptions("full")))!["lineup"]!.GetValue<string>());
        Assert.Equal("quartet", JsonNode.Parse(NativeCoreBridge.LayersOptions(null, new ArrangementOptions("quartet")))!["lineup"]!.GetValue<string>());
    }

    [Fact]
    public void Part_name_tables_know_the_quartet_parts()
    {
        Assert.Contains("1st Cornet", PartNames.Known);
        Assert.Contains("Tenor Horn", PartNames.Known);
        Assert.Equal("1. kornett", PartNames.Nb("1st Cornet"));
        Assert.Equal("2. kornett", PartNames.Nb("2nd Cornet"));
        Assert.Equal("Althorn", PartNames.Nb("Tenor Horn"));
        Assert.Equal("Eufonium", PartNames.Nb("Euphonium"));
        Assert.All(Lineups.QuartetParts, p => Assert.Contains(p, PartNames.Known));
    }

    [Fact]
    public void A_solo_take_is_one_line()
    {
        Assert.True(Lineups.IsSoloTake(null, "solo"));
        Assert.False(Lineups.IsSoloTake(null, "brass-band"));
        Assert.True(Lineups.IsSoloTake(Chorale(melodyOnly: true)));
        Assert.False(Lineups.IsSoloTake(Chorale()));
        var layered = Chorale();
        foreach (var v in layered.Voices) v.Layer = "solo";
        Assert.True(Lineups.IsSoloTake(layered));
        layered.Voices[^1].Layer = "bass";
        Assert.False(Lineups.IsSoloTake(layered));
    }

    [Fact]
    public void The_quartet_card_says_why_it_cannot_be_chosen_for_a_solo_take()
    {
        var said = new Announcements();
        var vm = new OutputOptionsViewModel(new ManagedCoreBridge(), said, Strings());
        Assert.True(vm.QuartetAvailable);
        Assert.Equal("4 players, one on each part", vm.QuartetDescription);
        Assert.Equal("", vm.QuartetHelpText);
        Assert.True(vm.TryChooseLineup(Lineup.Quartet));
        Assert.Equal(Lineup.Quartet, vm.Lineup);

        // A solo take: a quartet chosen earlier goes back to the band, and choosing it again is refused aloud.
        vm.IsSoloTake = true;
        Assert.Equal(Lineup.FullBand, vm.Lineup);
        Assert.False(vm.QuartetAvailable);
        Assert.Equal("Needs a recording of the whole group", vm.QuartetDescription);
        Assert.Equal("Needs a recording of the whole group", vm.QuartetHelpText);
        Assert.False(vm.TryChooseLineup(Lineup.Quartet));
        Assert.Equal(Lineup.FullBand, vm.Lineup);
        Assert.Equal(("Needs a recording of the whole group", AnnouncementKind.Important), said.Items[^1]);
        Assert.True(vm.TryChooseLineup(Lineup.MinimalBand));

        var nb = new OutputOptionsViewModel(new ManagedCoreBridge(), said, Strings("nb-NO")) { IsSoloTake = true };
        Assert.Equal("Trenger et opptak av hele gruppen", nb.QuartetDescription);
        nb.IsSoloTake = false;
        Assert.Equal("4 musikere, én på hver stemme", nb.QuartetDescription);
    }

    [Fact]
    public void Picker_and_share_strings_in_both_languages()
    {
        var en = Strings();
        var nb = Strings("nb-NO");
        Assert.Equal(("Quartet", "Kvartett"), (en["Library_Quartet"], nb["Library_Quartet"]));
        Assert.Equal(("Small band", "Lite band"), (en["Library_SmallBand"], nb["Library_SmallBand"]));
        Assert.Equal(("Score (all 4 parts)", "Partitur (alle 4 stemmer)"), (en["Export_Scope_QuartetScore"], nb["Export_Scope_QuartetScore"]));
        Assert.Equal(("Conductor's score", "Dirigentpartitur"), (en["Export_Scope_Conductor"], nb["Export_Scope_Conductor"]));
        Assert.Equal(("1st Cornet (you)", "1. kornett (deg)"),
            (en.Format("Export_Scope_MyPart", "1st Cornet"), nb.Format("Export_Scope_MyPart", PartNames.Nb("1st Cornet"))));
        var resw = File.ReadAllText(Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "nb-NO", "Resources.resw"));
        Assert.Contains("<value>Kvartett</value>", resw);
        Assert.DoesNotContain("Lite korps", resw);
    }

    [Fact]
    public void The_core_arranges_a_quartet_with_one_player_on_each_part()
    {
        if (Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH") is not { Length: > 0 }) return;
        var bridge = NativeCoreBridge.TryCreate();
        Assert.NotNull(bridge);
        string json = CompositionJson.Serialize(Chorale());
        var composition = bridge.ParseComposition(json);

        var xml = bridge.ArrangeMusicXmlWith(composition, new ArrangementOptions("quartet"))!;
        var doc = MusicXmlTalkingScoreBuilder.Build(xml);
        Assert.Equal(Lineups.QuartetParts, doc.Parts.Select(p => p.Name));
        Assert.All(doc.Parts, p => Assert.Contains(p.Bars, b => b.Events.Count > 0));
        Assert.Equal(new[] { "1. kornett", "2. kornett", "Althorn", "Eufonium" }, doc.Parts.Select(p => p.NameNb));

        // The same Composition for the small band is not four parts; easier and a key reach the core too.
        var band = MusicXmlTalkingScoreBuilder.Build(bridge.ArrangeMusicXmlWith(composition, new ArrangementOptions("minimal"))!);
        Assert.NotEqual(Lineups.QuartetParts, band.Parts.Select(p => p.Name));
        var easier = MusicXmlTalkingScoreBuilder.Build(bridge.ArrangeMusicXmlWith(composition, new ArrangementOptions("quartet", "easier", "D"))!);
        Assert.Equal(Lineups.QuartetParts, easier.Parts.Select(p => p.Name));
    }

    /// <summary>Four bars of I–IV–V–I in C: melody, block chords and bass, one voice each.</summary>
    internal static Composition Chorale(bool melodyOnly = false)
    {
        const int beat = Composition.DefaultTicksPerBeat;
        int[][] chords = [[60, 64, 67], [60, 65, 69], [59, 62, 67], [60, 64, 67]];
        int[] melody = [72, 72, 71, 72];
        int[] bass = [48, 53, 43, 48];
        Voice V(string id, VoiceRole role, IEnumerable<(int Pitch, int Start)> notes) => new()
        {
            Id = id, Role = role,
            Notes = notes.Select(n => new Note { Pitch = n.Pitch, Start = n.Start, Dur = 4 * beat, Sources = ["test"] }).ToList(),
        };
        var voices = new List<Voice> { V("melody", VoiceRole.Melody, melody.Select((p, i) => (p, i * 4 * beat))) };
        if (!melodyOnly)
        {
            voices.Add(V("harmony", VoiceRole.Harmony, chords.SelectMany((c, i) => c.Select(p => (p, i * 4 * beat)))));
            voices.Add(V("bass", VoiceRole.Bass, bass.Select((p, i) => (p, i * 4 * beat))));
        }
        return new Composition
        {
            Title = "Chorale",
            Voices = voices,
            Meters = [new Meter { Tick = 0, Beats = 4 }],
            Keys = [new KeySig { Tick = 0, Fifths = 0 }],
            BeatTimes = Enumerable.Range(0, 20).Select(i => i * 0.5).ToList(),
            Review = [],
        };
    }
}
