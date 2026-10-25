using System.Text.RegularExpressions;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>"Your instrument": the defaults, what can be chosen, what a job is asked for, and the stored answer.</summary>
public class YourInstrumentTests
{
    /// <summary>Every instrument, kind and tuning the screen offers.</summary>
    private static readonly List<(FrettedInstrument Kind, string Tuning)> Offered =
        [.. Instruments.All.SelectMany(i => i.Kinds()).SelectMany(kind => kind.Tunings().Select(t => (kind, t)))];

    private static YourInstrument Load(params (string Key, string Value)[] stored) =>
        new YourInstrumentStore(new DictionarySettings(stored.ToDictionary(s => s.Key, s => (object?)s.Value))).Load();

    [Fact]
    public void Not_now_is_a_six_string_guitar_in_standard_tuning_read_as_tab()
    {
        var d = YourInstrument.Default;
        Assert.Equal(Instrument.Guitar, d.Instrument);
        Assert.Equal(FrettedInstrument.Guitar6, d.Kind);
        Assert.Equal(6, d.Strings);
        Assert.Equal("standard", d.Tuning);
        Assert.Equal(FrettingHand.Left, d.Hand);
        Assert.Equal(Reads.Tab, d.Reads);
        Assert.Equal(new TabJobOptions("guitar-6", "standard", "tab"), d.JobOptions());
        // Nothing stored reads as the same.
        Assert.Equal(d, new YourInstrumentStore(new DictionarySettings()).Load());
    }

    [Fact]
    public void Every_instrument_can_be_chosen_with_its_kinds()
    {
        Assert.Equal([Instrument.Guitar, Instrument.Bass, Instrument.Ukulele, Instrument.Mandolin], Instruments.All);
        Assert.Equal(["guitar-6", "guitar-7", "guitar-8"], Instrument.Guitar.Kinds().Select(k => k.Id()));
        Assert.Equal(["bass-4", "bass-5", "bass-6"], Instrument.Bass.Kinds().Select(k => k.Id()));
        // Soprano, concert and tenor are one kind; the baritone is another.
        Assert.Equal(["ukulele", "ukulele-baritone"], Instrument.Ukulele.Kinds().Select(k => k.Id()));
        Assert.Equal(["mandolin"], Instrument.Mandolin.Kinds().Select(k => k.Id()));
        // Every instrument the computer writes tab for is offered, once.
        var kinds = Instruments.All.SelectMany(i => i.Kinds()).ToList();
        Assert.True(WireEnum<FrettedInstrument>.Values.ToHashSet().SetEquals(kinds));
        Assert.Equal(kinds.Count, kinds.Distinct().Count());
        foreach (var kind in kinds) Assert.Contains(kind, Instruments.Of(kind)!.Value.Kinds());
        Assert.Null(Instruments.Of(FrettedInstrument.Unknown));
        // A guitar and a bass are chosen by their strings; a ukulele by its size; a mandolin comes in one kind.
        Assert.Equal([6, 7, 8, 4, 5, 6], Instrument.Guitar.Kinds().Concat(Instrument.Bass.Kinds()).Select(k => YourInstrument.StringsOf(k)));
        foreach (var kind in Instrument.Ukulele.Kinds().Concat(Instrument.Mandolin.Kinds())) Assert.Null(YourInstrument.StringsOf(kind));
        // A capo is asked about for a guitar and a ukulele.
        Assert.Equal([Instrument.Guitar, Instrument.Ukulele], Instruments.All.Where(i => i.TakesCapo()));
    }

    [Fact]
    public void The_tunings_of_each_instrument_are_the_ones_the_computer_has_its_usual_one_first()
    {
        static IReadOnlyList<string> Tunings(FrettedInstrument kind) => new YourInstrument(kind).Tunings;
        Assert.Equal(["standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e"],
            Tunings(FrettedInstrument.Guitar6));
        Assert.Equal(["standard", "eb-standard"], Tunings(FrettedInstrument.Guitar7));
        Assert.Equal(["standard"], Tunings(FrettedInstrument.Guitar8));
        Assert.Equal(["standard", "eb-standard", "d-standard", "drop-d", "bead"], Tunings(FrettedInstrument.Bass4));
        Assert.Equal(["standard", "drop-a"], Tunings(FrettedInstrument.Bass5));
        Assert.Equal(["standard"], Tunings(FrettedInstrument.Bass6));
        Assert.Equal(["high-g", "low-g"], Tunings(FrettedInstrument.Ukulele));
        Assert.Equal(["standard"], Tunings(FrettedInstrument.UkuleleBaritone));
        Assert.Equal(["standard"], Tunings(FrettedInstrument.Mandolin));
        // A new answer starts in the instrument's usual tuning: a ukulele's is high G, not "standard".
        foreach (var kind in Instruments.All.SelectMany(i => i.Kinds())) Assert.Equal(kind.Tunings()[0], new YourInstrument(kind).Tuning);
        Assert.Equal("high-g", new YourInstrument(FrettedInstrument.Ukulele).Tuning);
    }

    [Fact]
    public void Every_instrument_tuning_and_layout_maps_to_its_job_options()
    {
        var layouts = new Dictionary<Reads, string> { [Reads.Tab] = "tab", [Reads.TabAndNotation] = "tab-and-notation", [Reads.Notation] = "notation" };
        Assert.True(Enum.GetValues<Reads>().ToHashSet().SetEquals(layouts.Keys));
        int seen = 0;
        foreach (var (kind, tuning) in Offered)
            foreach (var (reads, layout) in layouts)
                foreach (var hand in Enum.GetValues<FrettingHand>())
                {
                    var chosen = new YourInstrument(kind, tuning, hand, reads);
                    Assert.Equal(chosen, chosen.Valid());
                    // The hand is for the screens that draw a neck: it never reaches the job.
                    Assert.Equal(new TabJobOptions(kind.Id()!, tuning, layout), chosen.JobOptions());
                    Assert.Equal(kind.Id(), chosen.Family);
                    Assert.Equal(kind.Preset(tuning), chosen.Preset);
                    seen++;
                }
        Assert.Equal((11 + 2 + 1 + 5 + 2 + 1 + 2 + 1 + 1) * 3 * 3, seen);
        Assert.Equal("guitar-drop-d", new YourInstrument(FrettedInstrument.Guitar6, "drop-d").Preset);
        Assert.Equal("ukulele-baritone", new YourInstrument(FrettedInstrument.UkuleleBaritone).Preset);
        Assert.Equal("mandolin", new YourInstrument(FrettedInstrument.Mandolin).Preset);
    }

    [Fact]
    public void The_tunings_are_the_crates_presets()
    {
        string source = File.ReadAllText(TestPaths.RepoFile("core/targets/fretted/src/instrument.rs")!);
        const string start = "pub const PRESET_IDS: &[&str] = &[";
        int from = source.IndexOf(start, StringComparison.Ordinal) + start.Length;
        string list = source[from..source.IndexOf("];", from, StringComparison.Ordinal)];
        var crate = Regex.Matches(list, "\"([^\"]+)\"").Select(m => m.Groups[1].Value).ToList();
        Assert.NotEmpty(crate);
        // In the crate's order: the guitars, the basses, the ukuleles, the mandolin, each kind's usual tuning first.
        Assert.Equal(crate, Offered.Select(o => new YourInstrument(o.Kind, o.Tuning).Preset));
    }

    [Fact]
    public void Changing_the_kind_keeps_a_tuning_the_new_one_has()
    {
        var dropD = new YourInstrument(FrettedInstrument.Bass4, "drop-d");
        Assert.Equal(new YourInstrument(FrettedInstrument.Bass5, "standard"), dropD.WithKind(FrettedInstrument.Bass5));
        Assert.Equal(new YourInstrument(FrettedInstrument.Bass4, "standard"), new YourInstrument(FrettedInstrument.Bass5, "drop-a").WithKind(FrettedInstrument.Bass4));
        Assert.Equal(new YourInstrument(FrettedInstrument.Bass6), new YourInstrument(FrettedInstrument.Bass5).WithKind(FrettedInstrument.Bass6));
        Assert.Equal(new YourInstrument(FrettedInstrument.Guitar7, "eb-standard"), new YourInstrument(FrettedInstrument.Guitar6, "eb-standard").WithKind(FrettedInstrument.Guitar7));
        Assert.Equal(new YourInstrument(FrettedInstrument.Guitar7, "standard"), new YourInstrument(FrettedInstrument.Guitar6, "dadgad").WithKind(FrettedInstrument.Guitar7));
        // A baritone has no high or low G; back on the smaller ones the usual tuning is high G.
        var baritone = new YourInstrument(FrettedInstrument.Ukulele, "low-g").WithKind(FrettedInstrument.UkuleleBaritone);
        Assert.Equal(new YourInstrument(FrettedInstrument.UkuleleBaritone, "standard"), baritone);
        Assert.Equal(new YourInstrument(FrettedInstrument.Ukulele, "high-g"), baritone.WithKind(FrettedInstrument.Ukulele));
        // The hand and what is read stay.
        var mine = new YourInstrument(FrettedInstrument.Guitar6, "drop-d", FrettingHand.Right, Reads.Notation);
        Assert.Equal(mine with { Kind = FrettedInstrument.Guitar8, Tuning = "standard" }, mine.WithKind(FrettedInstrument.Guitar8));
    }

    [Fact]
    public void Another_instrument_starts_in_its_own_usual_tuning()
    {
        var mine = new YourInstrument(FrettedInstrument.Guitar6, "drop-d", FrettingHand.Right, Reads.TabAndNotation);
        // A four-string bass has a drop D too, but the player has not said the bass is in it.
        Assert.Equal(mine with { Kind = FrettedInstrument.Bass4, Tuning = "standard" }, mine.WithInstrument(Instrument.Bass));
        Assert.Equal(mine with { Kind = FrettedInstrument.Ukulele, Tuning = "high-g" }, mine.WithInstrument(Instrument.Ukulele));
        Assert.Equal(mine with { Kind = FrettedInstrument.Mandolin, Tuning = "standard" }, mine.WithInstrument(Instrument.Mandolin));
        // The same instrument again changes nothing.
        Assert.Equal(mine, mine.WithInstrument(Instrument.Guitar));
        var seven = new YourInstrument(FrettedInstrument.Guitar7, "eb-standard");
        Assert.Equal(seven, seven.WithInstrument(Instrument.Guitar));
        foreach (var i in Instruments.All) Assert.Equal(i, mine.WithInstrument(i).Instrument);
    }

    [Fact]
    public void The_answer_comes_back_as_it_was_saved()
    {
        var settings = new DictionarySettings();
        foreach (var (kind, tuning) in Offered)
            foreach (var hand in Enum.GetValues<FrettingHand>())
                foreach (var reads in Enum.GetValues<Reads>())
                {
                    var chosen = new YourInstrument(kind, tuning, hand, reads);
                    new YourInstrumentStore(settings).Save(chosen);
                    // A new store on the same settings: what the next start of the app reads.
                    Assert.Equal(chosen, new YourInstrumentStore(settings).Load());
                }
        Assert.True(settings.Values.Keys.ToHashSet().SetEquals([YourInstrumentStore.KindKey, YourInstrumentStore.TuningKey, YourInstrumentStore.HandKey, YourInstrumentStore.ReadsKey]));
    }

    [Fact]
    public void Saving_leaves_everything_else_in_the_settings_alone()
    {
        var settings = new DictionarySettings(new() { ["appearance"] = "dark", ["seat"] = "solo-cornet" });
        new YourInstrumentStore(settings).Save(new YourInstrument(FrettedInstrument.Bass5, "drop-a", hand: FrettingHand.Right));
        Assert.Equal("dark", settings.Values["appearance"]);
        Assert.Equal("solo-cornet", settings.Values["seat"]);
    }

    [Fact]
    public void Stored_values_this_version_cant_offer_read_as_the_defaults()
    {
        var d = YourInstrument.Default;
        // An instrument this version has never heard of.
        Assert.Equal(d, Load((YourInstrumentStore.KindKey, "banjo-5")));
        Assert.Equal(d, Load((YourInstrumentStore.KindKey, "banjo-5"), (YourInstrumentStore.TuningKey, "open-g")));
        // A tuning the instrument has no preset for is its usual one; the instrument stays.
        Assert.Equal(new YourInstrument(FrettedInstrument.Bass5), Load((YourInstrumentStore.KindKey, "bass-5"), (YourInstrumentStore.TuningKey, "drop-d")));
        Assert.Equal(new YourInstrument(FrettedInstrument.Ukulele, "high-g"), Load((YourInstrumentStore.KindKey, "ukulele"), (YourInstrumentStore.TuningKey, "standard")));
        Assert.Equal(new YourInstrument(FrettedInstrument.Mandolin), Load((YourInstrumentStore.KindKey, "mandolin"), (YourInstrumentStore.TuningKey, "dadgad")));
        Assert.Equal(new YourInstrument(FrettedInstrument.Ukulele), Load((YourInstrumentStore.KindKey, "ukulele")));
        // An unknown hand or reading is the default; the rest of the answer stays.
        Assert.Equal(d with { Tuning = "dadgad" }, Load((YourInstrumentStore.KindKey, "guitar-6"), (YourInstrumentStore.TuningKey, "dadgad"),
            (YourInstrumentStore.HandKey, "both"), (YourInstrumentStore.ReadsKey, "braille")));
        // A tuning with no instrument beside it says nothing.
        Assert.Equal(d, Load((YourInstrumentStore.TuningKey, "dadgad")));
        Assert.Equal(d with { Hand = FrettingHand.RightUpsideDown, Reads = Reads.Notation },
            Load((YourInstrumentStore.HandKey, "right-upside-down"), (YourInstrumentStore.ReadsKey, "notation")));
    }

    [Fact]
    public void An_answer_that_cant_be_chosen_never_reaches_a_job_or_the_store()
    {
        var unknown = new YourInstrument(FrettedInstrument.Unknown, "dadgad", FrettingHand.Right, Reads.Notation);
        Assert.Equal(new TabJobOptions("guitar-6", "standard", "notation"), unknown.JobOptions());
        Assert.Equal(Instrument.Guitar, unknown.Instrument);
        Assert.Equal("guitar-standard", unknown.Preset);
        // A tuning of another instrument: the instrument's usual one is asked for.
        Assert.Equal(new TabJobOptions("ukulele", "high-g", "tab"), new YourInstrument(FrettedInstrument.Ukulele, "drop-d").JobOptions());
        Assert.Equal(new TabJobOptions("bass-6", "standard", "tab"), new YourInstrument(FrettedInstrument.Bass6, "bead").JobOptions());
        var settings = new DictionarySettings();
        new YourInstrumentStore(settings).Save(unknown);
        Assert.Equal("guitar-6", settings.Values[YourInstrumentStore.KindKey]);
        Assert.DoesNotContain("dadgad", settings.Values.Values);
    }
}
