using System.Text.Json.Nodes;
using System.Xml.Linq;
using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Seats;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// "What do you play?" and "your part" (docs/plan/my-instrument.md): the picker, the settings, which part is the
/// player's in each lineup, the options sent to the engine and the arrangers, and the screens that follow the part.
/// The core is faked with a few rows of its seat table; the native spot checks run against the real one.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class MyInstrumentTests
{
    /// <summary>Some rows of the core's seats and seat_part table (instruments.rs SEAT_PARTS), and a few Norwegian names.</summary>
    internal sealed class FakeCore : ICoreBridge
    {
        private readonly ManagedCoreBridge _managed = new();

        public bool Native { get; init; } = true;
        public Dictionary<string, string> Sources { get; } = [];

        public string Version => "fake";
        public bool IsNative => Native;
        public Composition ParseComposition(string json) => _managed.ParseComposition(json);
        public TalkingScoreDocument BuildTalkingScore(string musicXml, Composition? composition) =>
            MusicXmlTalkingScoreBuilder.Build(musicXml, composition, PartNameNb);
        public string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context, TalkingScoreSettings settings, bool byBar = false) =>
            _managed.Announce(part, bar, ev, context, settings, byBar);
        public string? ArrangeMusicXml(Composition composition, string arranger = "auto") => null;
        public string? ArrangeMusicXmlWith(Composition composition, ArrangementOptions options) => null;
        public BandArrangement? ArrangeLayersBand(LayerInputs inputs, string title, ArrangementOptions options) => null;
        public HumanizedPart? Humanize(IReadOnlyList<HumanizeNote> notes, string part, int player, string? compositionJson) => null;

        private static readonly string[] Treble = ["treble"];
        private static readonly string[] Both = ["treble", "bass"];

        public IReadOnlyList<SeatInfo> Seats() =>
        [
            new("solo-cornet", "Solo Cornet", "Solokornett", "bb-cornet", "treble", Treble),
            new("2nd-cornet", "2nd Cornet", "2. kornett", "bb-cornet", "treble", Treble),
            new("3rd-cornet", "3rd Cornet", "3. kornett", "bb-cornet", "treble", Treble),
            new("flugelhorn", "Flugelhorn", "Flygelhorn", "flugelhorn", "treble", Treble),
            new("solo-horn", "Solo Horn", "Solo althorn", "eb-tenor-horn", "treble", Treble),
            new("1st-baritone", "1st Baritone", "1. baryton", "baritone", "treble", Both),
            new("2nd-baritone", "2nd Baritone", "2. baryton", "baritone", "treble", Both),
            new("euphonium", "Euphonium", "Eufonium", "euphonium", "treble", Both),
            new("eb-bass", "E♭ Bass", "Ess-bass", "eb-bass", "treble", Both),
            new("percussion", "Percussion", "Slagverk", "drum-kit", "percussion", []),
        ];

        private static readonly Dictionary<string, (string? Band, string? Minimal, string? Quartet)> Table = new()
        {
            ["solo-cornet"] = ("Solo Cornet", "Solo Cornet", "1st Cornet"),
            ["2nd-cornet"] = ("2nd Cornet", "2nd Cornet", "2nd Cornet"),
            ["3rd-cornet"] = ("3rd Cornet", "2nd Cornet", "2nd Cornet"),
            ["flugelhorn"] = ("Flugelhorn", "Flugelhorn", "2nd Cornet"),
            ["solo-horn"] = ("Solo Horn", "Solo Horn", "Tenor Horn"),
            ["1st-baritone"] = ("1st Baritone", "Euphonium", "Euphonium"),
            ["2nd-baritone"] = ("2nd Baritone", "Euphonium", "Euphonium"),
            ["euphonium"] = ("Euphonium", "Euphonium", "Euphonium"),
            ["eb-bass"] = ("E♭ Bass", "E♭ Bass", "Euphonium"),
            ["percussion"] = ("Percussion", null, null),
        };

        public SeatPart? SeatPartFor(string lineup, string seat)
        {
            var row = Table[seat];
            string? part = lineup switch { "band" => row.Band, "minimal" => row.Minimal, "quartet" => row.Quartet, _ => throw new ArgumentException(lineup) };
            string own = Seats().Single(s => s.Id == seat).Name;
            bool sameKey = part is not null && !(seat == "eb-bass" && part == "Euphonium");
            return new SeatPart(part, part == own, sameKey);
        }

        public IReadOnlyDictionary<string, string> PartSources(string compositionJson) => Sources;

        public string PartNameNb(string name) => name switch
        {
            "Solo Cornet" => "Solokornett",
            "Solo Horn" => "Solo althorn",
            "Percussion" => "Slagverk",
            "Euphonium" => "Eufonium",
            _ => name,
        };
    }

    private sealed class Announcements : IAnnouncer
    {
        public List<string> Items { get; } = [];
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Items.Add(text);
    }

    private sealed class Inline : IUiDispatcher
    {
        public void Post(Action action) => action();
    }

    private sealed class NoCapture : ICaptureService
    {
        public bool SupportsAppCapture => false;
        public bool IsCapturing => false;
        public event EventHandler<CaptureLevel>? Level { add { } remove { } }
        public event EventHandler<CaptureNotice>? Notice { add { } remove { } }
        public Task<IReadOnlyList<AudioDevice>> ListMicrophonesAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<AudioDevice>>([]);
        public Task<IReadOnlyList<AudioApp>> ListAudioAppsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<AudioApp>>([]);
        public Task StartAsync(CaptureRequest request, CancellationToken ct = default) => throw new InvalidOperationException();
        public Task<CaptureResult> StopAsync(CancellationToken ct = default) => throw new InvalidOperationException();
    }

    private sealed class NoDecoder : IMediaDecoder
    {
        public Task<DecodedMedia> DecodeToWavAsync(string inputPath, string outputPath, int? sampleRate = null, CancellationToken ct = default) =>
            throw new InvalidOperationException();
    }

    private sealed class NoDialogs : IFileDialogs
    {
        public Task<string?> PickOpenAsync(IEnumerable<string> extensions) => Task.FromResult<string?>(null);
        public Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description) => Task.FromResult<SaveTarget?>(null);
    }

    /// <summary>The real .resw strings, in a language of their own (not the machine's).</summary>
    private sealed class LangStrings(ReswStrings inner, string language) : IStrings
    {
        public string this[string key] => inner[key];
        public string Language => language;
    }

    private static IStrings Strings(string lang = "en-US") => new LangStrings(new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", lang, "Resources.resw")))), lang);

    private static (MainViewModel Main, Announcements Said, InMemorySettings Store) Build(ICoreBridge? core = null, bool firstRun = false,
        ScoreLibrary? library = null, Action<InMemorySettings>? setup = null)
    {
        var said = new Announcements();
        var strings = Strings();
        var ui = new Inline();
        core ??= new FakeCore();
        var store = new InMemorySettings();
        if (!firstRun) store.Set("FirstRunDone", true);
        setup?.Invoke(store);
        var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        MainViewModel? main = null;
        main = new MainViewModel(
            new StartViewModel(new NoCapture(), new NoDecoder(), new NoDialogs(), said, strings, ui, Path.GetTempPath()),
            new SourceKindViewModel(strings),
            new TranscriptionViewModel(() => main!.Engine, said, strings, ui),
            new ScoreViewModel(core, new PlayerViewModel(player, said, strings, ui), said, strings),
            new ExportViewModel(new ExportService(), new NoDialogs(), said, strings),
            new OutputOptionsViewModel(core, said, strings),
            new SettingsViewModel(store, said, strings),
            (uri, token) => new EngineClient(new HttpClient(), uri) { Token = token },
            said, strings, core, library);
        return (main, said, store);
    }

    private static ScorePart P(string name, int chromatic = -2, bool percussion = false) => new(name, chromatic, percussion);

    private static readonly ScorePart[] SmallBand =
        [P("Solo Cornet"), P("2nd Cornet"), P("Flugelhorn"), P("Solo Horn", -9), P("1st Trombone", -14), P("Euphonium", -14), P("E♭ Bass", -21), P("B♭ Bass", -26)];

    private static readonly ScorePart[] Quartet = [P("1st Cornet"), P("2nd Cornet"), P("Tenor Horn", -9), P("Euphonium", -14)];

    // ---- which part is yours ----

    [Fact]
    public void Without_an_answer_the_first_solo_part_stays_yours()
    {
        var r = YourPart.Resolve(new FakeCore(), SeatChoice.NotSet, null, [P("Percussion", 0, true), P("Solo Horn", -9), P("Solo Cornet")], null);
        Assert.Equal(1, r.Index);
        Assert.Equal(SeatNotice.None, r.Notice);
    }

    [Fact]
    public void I_conduct_or_listen_has_no_part()
    {
        Assert.Equal(-1, YourPart.Resolve(new FakeCore(), SeatChoice.Conductor, Lineup.FullBand, SmallBand, null).Index);
    }

    [Fact]
    public void A_seat_with_its_own_part_needs_no_notice()
    {
        var r = YourPart.Resolve(new FakeCore(), new SeatChoice("2nd-cornet", null), Lineup.MinimalBand, SmallBand, null);
        Assert.Equal(1, r.Index);
        Assert.Equal(SeatNotice.None, r.Notice);
    }

    [Fact]
    public void A_lineup_without_the_seat_takes_the_cores_closest_part_and_says_so()
    {
        var s = Strings();
        var catalog = new SeatCatalog(new FakeCore(), s);
        var choice = new SeatChoice("1st-baritone", null);
        var r = YourPart.Resolve(new FakeCore(), choice, Lineup.MinimalBand, SmallBand, null);
        Assert.Equal(5, r.Index);
        Assert.Equal(SeatNotice.SameKey, r.Notice);
        Assert.Equal("This small band has no 1st Baritone. Your part here is Euphonium, the closest: the same key and clef.",
            YourPart.Notice(s, catalog, choice, r, SmallBand, n => n));

        var bass = new SeatChoice("eb-bass", null);
        var q = YourPart.Resolve(new FakeCore(), bass, Lineup.Quartet, Quartet, null);
        Assert.Equal(3, q.Index);
        Assert.Equal(SeatNotice.OtherKey, q.Notice);
        Assert.Equal("This quartet has no E♭ Bass. Your part here is Euphonium, written for B♭.", YourPart.Notice(s, catalog, bass, q, Quartet, n => n));

        // Read in bass clef, the key does not matter: every part is at concert pitch.
        Assert.Equal(SeatNotice.SameKey, YourPart.Resolve(new FakeCore(), bass with { Reads = "bass" }, Lineup.Quartet, Quartet, null).Notice);
    }

    [Fact]
    public void Norwegian_notices_have_one_definite_form_per_lineup()
    {
        var s = Strings("nb-NO");
        var catalog = new SeatCatalog(new FakeCore(), s);
        var choice = new SeatChoice("1st-baritone", null);
        var r = YourPart.Resolve(new FakeCore(), choice, Lineup.MinimalBand, SmallBand, null);
        Assert.Equal("Det lille bandet har ingen 1. baryton. Her er stemmen din Eufonium, den nærmeste: samme stemming og nøkkel.",
            YourPart.Notice(s, catalog, choice, r, SmallBand, new FakeCore().PartNameNb));
    }

    [Fact]
    public void The_notice_is_said_once_and_moving_your_part_keeps_it_muted_quietly()
    {
        var (main, said, _) = Build(setup: s => s.Set("Seat", "1st-baritone"));
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        // A small band's Euphonium stands in for the baritone.
        var small = xml.Replace("<part-name>Solo Horn</part-name>", "<part-name>Euphonium</part-name>");
        main.Output.ShowingSaved(Lineup.MinimalBand, null);
        main.Score.Load(small, new Composition { Title = "Test tune" });
        main.Score.Load(small, main.Score.Composition); // as after a changed note
        Assert.Single(said.Items, t => t.StartsWith("This small band has no 1st Baritone."));
        Assert.Equal(1, main.Score.MyPartIndex);

        main.Score.Player.MuteMyPart = true;
        said.Items.Clear();
        main.Score.MakeMine(0);
        Assert.True(main.Score.Player.Parts[0].IsMuted);
        Assert.False(main.Score.Player.Parts[1].IsMuted);
        Assert.True(main.Score.Player.MuteMyPart);
        Assert.Equal(["Solo Cornet is your part in this score."], said.Items);

        // Settings: one change, told once.
        int changes = 0;
        main.Settings.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(SettingsViewModel.SeatChoice)) changes++; };
        main.Settings.SeatChoice = new SeatChoice("euphonium", "bass");
        Assert.Equal(1, changes);
    }

    [Fact]
    public void Percussion_in_the_quartet_opens_every_part()
    {
        var s = Strings();
        var choice = new SeatChoice("percussion", null);
        var r = YourPart.Resolve(new FakeCore(), choice, Lineup.Quartet, Quartet, null);
        Assert.Equal(-1, r.Index);
        Assert.Equal(SeatNotice.NoPart, r.Notice);
        Assert.Equal("This quartet has no Percussion part. Brasscribe opens every part.", YourPart.Notice(s, new SeatCatalog(new FakeCore(), s), choice, r, Quartet, n => n));
    }

    [Fact]
    public void The_part_chosen_for_a_score_wins()
    {
        Assert.Equal(6, YourPart.Resolve(new FakeCore(), new SeatChoice("2nd-cornet", null), Lineup.MinimalBand, SmallBand, "E♭ Bass").Index);
        Assert.Equal(6, YourPart.Resolve(new FakeCore(), SeatChoice.Conductor, Lineup.MinimalBand, SmallBand, "E♭ Bass").Index);
    }

    // ---- the picker ----

    [Fact]
    public void Nothing_is_chosen_for_the_player_and_Continue_says_why()
    {
        var s = Strings();
        var picker = new SeatPickerViewModel(new SeatCatalog(new FakeCore(), s), s);
        Assert.Equal(-1, picker.InstrumentIndex);
        Assert.False(picker.CanContinue);
        Assert.Equal("Choose your instrument, or “I conduct or listen”.", picker.ContinueHint);
        Assert.Equal(["Cornet", "Flugelhorn", "Tenor Horn", "Baritone", "Euphonium", "E♭ Bass", "Percussion"], picker.Tiles.Select(t => t.Label));
        Assert.Equal("Tenor Horn, in E flat", picker.Tiles[2].SpokenLabel);
        Assert.Equal("E flat Bass", picker.Tiles[5].SpokenLabel);

        picker.InstrumentIndex = 0; // Cornet: which part? with nothing chosen
        Assert.True(picker.ShowsParts);
        Assert.Equal(["Solo Cornet", "2nd Cornet", "3rd Cornet"], picker.PartChoices);
        Assert.False(picker.CanContinue);
        Assert.Equal("Choose which part you play.", picker.ContinueHint);
        Assert.False(picker.ShowsReads);
        picker.PartIndex = 2;
        Assert.Equal(new SeatChoice("3rd-cornet", null), picker.Choice);

        picker.InstrumentIndex = 3; // Baritone: the part again, and the clef with the band's own chosen
        Assert.Equal(-1, picker.PartIndex);
        Assert.True(picker.ShowsReads);
        Assert.Equal(["Treble clef in B♭", "Bass clef, as it sounds"], picker.ReadsChoices);
        picker.PartIndex = 0;
        Assert.Equal(new SeatChoice("1st-baritone", null), picker.Choice);
        picker.ReadsIndex = 1;
        Assert.Equal(new SeatChoice("1st-baritone", "bass"), picker.Choice);

        picker.InstrumentIndex = 5;
        Assert.Equal(["Treble clef in E♭", "Bass clef, as it sounds"], picker.ReadsChoices);
        Assert.Equal(new SeatChoice("eb-bass", null), picker.Choice);
    }

    [Fact]
    public void Settings_starts_the_picker_from_the_answer_and_describes_it()
    {
        var s = Strings();
        var catalog = new SeatCatalog(new FakeCore(), s);
        var picker = new SeatPickerViewModel(catalog, s, new SeatChoice("1st-baritone", "bass"));
        Assert.Equal((3, 0, 1), (picker.InstrumentIndex, picker.PartIndex, picker.ReadsIndex));
        Assert.Equal("1st Baritone · bass clef, as it sounds", catalog.Describe(new SeatChoice("1st-baritone", "bass")));
        Assert.Equal("1st Baritone · treble clef in B♭", catalog.Describe(new SeatChoice("1st-baritone", null)));
        Assert.Equal("2nd Cornet", catalog.Describe(new SeatChoice("2nd-cornet", null)));
        Assert.Equal("Not set", catalog.Describe(SeatChoice.NotSet));
        Assert.Equal("I conduct or listen", catalog.Describe(SeatChoice.Conductor));
        Assert.Equal("1. baryton · F-nøkkel, klingende", new SeatCatalog(new FakeCore(), Strings("nb-NO")).Describe(new SeatChoice("1st-baritone", "bass")));
    }

    [Fact]
    public void Without_the_cores_seats_nobody_is_asked()
    {
        var (main, _, _) = Build(new ManagedCoreBridge(), firstRun: true);
        main.GetStartedCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
    }

    // ---- the first run ----

    [Fact]
    public void The_first_run_asks_once_and_saves_only_on_Continue()
    {
        var (main, said, store) = Build(firstRun: true);
        Assert.Equal(Screen.FirstRun, main.Screen);
        main.GetStartedCommand.Execute(null);
        Assert.Equal(Screen.WhatDoYouPlay, main.Screen);
        Assert.Contains("What do you play?", said.Items);
        Assert.False(main.ContinueWithSeatCommand.CanExecute(null));

        main.FirstRunSeat!.InstrumentIndex = 4; // Euphonium: one part
        Assert.True(main.ContinueWithSeatCommand.CanExecute(null));
        Assert.Null(store.Get<string?>("Seat", null)); // nothing until Continue (WCAG 3.2.2)
        main.ContinueWithSeatCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
        Assert.Equal("euphonium", store.Get<string?>("Seat", null));
        Assert.Equal(new SeatChoice("euphonium", null), main.Settings.SeatChoice);
    }

    [Fact]
    public void Not_now_sets_nothing_and_I_conduct_sets_none()
    {
        var (main, _, store) = Build(firstRun: true);
        main.GetStartedCommand.Execute(null);
        main.SkipSeatCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
        Assert.False(main.Settings.SeatChoice.IsSet);
        Assert.True(main.Settings.FirstRunDone);

        var (other, _, _) = Build(firstRun: true);
        other.GetStartedCommand.Execute(null);
        other.ConductOrListenCommand.Execute(null);
        Assert.True(other.Settings.SeatChoice.IsConductor);
    }

    // ---- options to the engine and the arrangers ----

    [Fact]
    public void Without_a_seat_the_options_are_as_before()
    {
        Assert.Equal("""{"lineup":"band","difficulty":"faithful"}""", NativeCoreBridge.ArrangeOptions(ArrangementOptions.Default));
        Assert.Equal("""{"lineup":"minimal","difficulty":"easier","seat":"euphonium","reads":"bass","lead":"seat"}""",
            NativeCoreBridge.ArrangeOptions(new ArrangementOptions("minimal", "easier", Seat: "euphonium", Reads: "bass", Lead: "seat")));
        var layers = JsonNode.Parse(NativeCoreBridge.LayersOptions(null, new ArrangementOptions(Seat: "2nd-cornet")))!.AsObject();
        Assert.Equal("2nd-cornet", layers["seat"]!.GetValue<string>());
        Assert.False(layers.ContainsKey("reads"));
        Assert.False(layers.ContainsKey("lead"));
    }

    [Fact]
    public void A_solo_take_is_written_for_the_seat_with_the_tune_on_it()
    {
        var s = Strings();
        var output = new OutputOptionsViewModel(new FakeCore(), new Announcements(), s) { Seats = new SeatCatalog(new FakeCore(), s) };
        output.PlayerSeat = new SeatChoice("1st-baritone", "bass");
        output.IsSoloTake = true;
        output.BeginTake();
        Assert.Equal(new ArrangementOptions(Seat: "1st-baritone", Reads: "bass", Lead: "seat"), output.Options);
        Assert.True(output.SoloGivesOnePart);
        Assert.False(output.ShowsLineupChoice);
        Assert.True(output.ShowsWhoPlayed);
        output.ShowingMade(output.Options);

        // Settings changes later: this score is not arranged again.
        output.PlayerSeat = new SeatChoice("euphonium", null);
        Assert.Equal(output.Applied, output.Options);

        // "Who played this?": a friend's cornet, written the band's way, arranged on Show the score.
        output.WhoPlayedIndex = output.WhoPlayedSeats.ToList().FindIndex(x => x.Id == "2nd-cornet");
        Assert.Equal(new ArrangementOptions(Seat: "2nd-cornet", Lead: "seat"), output.Options);
        Assert.NotEqual(output.Applied, output.Options);
    }

    [Fact]
    public void Who_plays_the_tune_is_for_band_lineups_only()
    {
        var s = Strings();
        var output = new OutputOptionsViewModel(new FakeCore(), new Announcements(), s) { Seats = new SeatCatalog(new FakeCore(), s) };
        output.PlayerSeat = new SeatChoice("euphonium", null);
        output.BeginTake();
        output.HasSoloist = true;
        Assert.True(output.ShowsTuneChoice);
        Assert.Equal("Solo Cornet (as usual)", output.TuneLineupLabel);
        Assert.Equal("You: Euphonium", output.TuneSeatLabel);
        output.TuneOnMyPart = true;
        Assert.Equal("seat", output.Options.Lead);
        Assert.Equal("your part: Euphonium", output.SmallBandYourPart);

        output.Lineup = Lineup.Quartet;
        Assert.False(output.ShowsTuneChoice);
        Assert.Null(output.Options.Lead);

        // A seat that can't carry a tune, or that is already the lead, is not asked.
        output.Lineup = Lineup.FullBand;
        output.PlayerSeat = new SeatChoice("eb-bass", null);
        output.BeginTake();
        Assert.False(output.ShowsTuneChoice);
        output.PlayerSeat = new SeatChoice("solo-cornet", null);
        output.BeginTake();
        Assert.False(output.ShowsTuneChoice);
    }

    [Fact]
    public void The_key_is_said_for_your_part()
    {
        var output = new OutputOptionsViewModel(new FakeCore(), new Announcements(), Strings());
        var composition = new Composition { Title = "t", Keys = [new KeySig { Fifths = 2 }] };
        output.SetScoreContext(composition, -2, yours: true);
        Assert.Equal("As recorded · E major on your part", output.KeyDetail);
        output.SetScoreContext(composition, -2);
        Assert.Equal("As recorded · E major for B♭ instruments", output.KeyDetail);
        output.Reads = "bass";
        output.SetScoreContext(composition, 0, yours: true);
        Assert.Equal("As recorded · D major, as it sounds", output.KeyDetail);
    }

    // ---- the score follows your part ----

    [Fact]
    public void A_score_opens_on_the_seats_part_and_Make_this_my_part_is_kept()
    {
        var root = Path.Combine(Path.GetTempPath(), "brasscribe-seat-" + Guid.NewGuid().ToString("N"));
        var library = new ScoreLibrary(root);
        var (main, said, _) = Build(library: library, setup: s => s.Set("Seat", "solo-horn"));
        main.OpenScoreFile(TestPaths.Fixture("two-parts.musicxml"));
        var score = main.Score;
        Assert.Equal(1, score.MyPartIndex); // Solo Horn, not the first Solo part
        Assert.True(score.Player.Parts[1].IsMine);

        // Showing another part keeps your part yours.
        score.SelectedPartIndex = 0;
        Assert.Equal(1, score.MyPartIndex);
        Assert.True(score.CanMakeShownMine);
        score.MakeMine(0);
        Assert.Equal(0, score.MyPartIndex);
        Assert.Contains("Solo Cornet is your part in this score.", said.Items);
        Assert.Equal("Solo Cornet", library.Entries.Single().MyPart);

        // Settings changes the seat: the part chosen for this score stays.
        main.Settings.SeatChoice = new SeatChoice("euphonium", null);
        Assert.Equal(0, score.MyPartIndex);

        // Opened again, it is still the part chosen.
        main.OpenScoreFile(TestPaths.Fixture("two-parts.musicxml"));
        Assert.Equal(0, main.Score.MyPartIndex);
        Assert.Equal("Solo Cornet", new ScoreLibrary(root).Entries.Single().MyPart);
    }

    [Fact]
    public void With_I_conduct_or_listen_no_part_is_muted_or_shared_as_yours()
    {
        var (main, _, _) = Build(setup: s => s.Set("Seat", SeatChoice.None));
        main.OpenScoreFile(TestPaths.Fixture("two-parts.musicxml"));
        Assert.Equal(-1, main.Score.MyPartIndex);
        Assert.False(main.Score.HasMyPart);
        Assert.False(main.Score.Stand.HasMyPart);
        Assert.Null(main.Score.Player.PlayAlongPart);

        main.OpenExportCommand.Execute(null);
        Assert.False(main.Export.HasMyPart);
        Assert.Equal(ExportScope.EveryPart, main.Export.Scope);

        // Settings: now a horn player; the score's "your part" follows at once, without arranging.
        main.Settings.SeatChoice = new SeatChoice("solo-horn", null);
        Assert.Equal(1, main.Score.MyPartIndex);
        main.OpenExportCommand.Execute(null);
        Assert.Equal("Solo Horn (you)", main.Export.MyPartLabel);
        Assert.Equal(ExportScope.MyPart, main.Export.Scope);
    }

    [Fact]
    public void Share_says_your_part_not_the_part_shown()
    {
        var (main, _, _) = Build(setup: s => s.Set("Seat", "solo-horn"));
        main.OpenScoreFile(TestPaths.Fixture("two-parts.musicxml"));
        main.Score.SelectedPartIndex = 0;
        main.OpenExportCommand.Execute(null);
        Assert.Equal("Solo Horn (you)", main.Export.MyPartLabel);
    }

    [Fact]
    public void Source_labels_come_from_the_core_and_an_arranged_part_has_its_notice_in_review()
    {
        var core = new FakeCore();
        core.Sources["Solo Cornet"] = PartSource.Recording;
        core.Sources["Solo Horn"] = PartSource.Arranged;
        var (main, said, _) = Build(core, setup: s => s.Set("Seat", "solo-horn"));
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        var composition = new Composition { Title = "Test tune" };
        main.Score.Load(xml, composition);

        var mixer = main.Score.Player.Parts;
        Assert.Equal("From the recording", mixer[0].SourceLabel);
        Assert.Equal(SourceGlyphs.Recording, mixer[0].SourceGlyph);
        Assert.Equal("Arranged from the band's harmony", mixer[1].SourceLabel);
        Assert.Equal(SourceGlyphs.Arranged, mixer[1].SourceGlyph);
        Assert.StartsWith("Nobody played this part on its own", mixer[1].SourceExplanation);
        Assert.False(mixer[2].HasSource);
        Assert.True(main.Score.MyPartSourceIsArranged);

        // The fixture's uncertain notes are all in the Solo Cornet: none are yours.
        main.Review.Load();
        Assert.True(main.Review.ShowsArrangedNotice);
        Assert.False(main.Review.ShowsList);
        Assert.StartsWith("Nobody played the Solo Horn part on its own", main.Review.ArrangedBody);
        Assert.Contains(said.Items, t => t.StartsWith("Your part is arranged. "));
        main.Review.CheckOtherPartsCommand.Execute(null);
        Assert.True(main.Review.ShowsList);
        Assert.Equal(ReviewScope.AllParts, main.Review.Scope);
    }

    [Fact]
    public void Part_names_on_the_mixer_come_from_the_core_in_norwegian()
    {
        var (main, _, _) = Build(setup: s => s.Set("Seat", "solo-horn"));
        main.Score.Language = "nb";
        main.OpenScoreFile(TestPaths.Fixture("two-parts.musicxml"));
        Assert.Equal(["Solokornett", "Solo althorn", "Slagverk"], main.Score.Player.Parts.Select(p => p.Label));
        Assert.Equal(["Solo Cornet", "Solo Horn", "Percussion"], main.Score.Player.Parts.Select(p => p.Name));
        Assert.Equal("Solo althorn", main.Score.MyPartLabel);
    }

    [Fact]
    public void A_saved_score_keeps_the_seat_it_was_written_for()
    {
        var output = new OutputOptionsViewModel(new FakeCore(), new Announcements(), Strings());
        var composition = CompositionJson.Parse("""{"title":"t","voices":[],"arrangement":{"lineup":"band","seat":"euphonium","reads":"bass","lead":"seat"}}""");
        output.ShowingSaved(Lineup.FullBand, null, composition);
        Assert.Equal(new ArrangementOptions(Seat: "euphonium", Reads: "bass", Lead: null), output.Applied with { Lead = null });
        Assert.Equal("euphonium", output.Seat);
        Assert.True(output.TuneOnMyPart);
    }

    [Fact]
    public void Your_part_in_bass_clef_is_as_written_in_bass_clef()
    {
        var (main, _, _) = Build(setup: s => s.Set("Seat", "euphonium"));
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")).Replace("<part-name>Solo Cornet</part-name>", "<part-name>Euphonium</part-name>");
        main.Output.ShowingMade(new ArrangementOptions(Seat: "euphonium", Reads: "bass"));
        main.Score.Load(xml, null);
        main.Score.SelectedPartIndex = 2; // percussion, in C: another part
        Assert.Equal("As written", main.Score.WrittenLabel);
        main.Score.MakeMine(2);
        Assert.Equal("As written (bass clef)", main.Score.WrittenLabel);
    }

    [Fact]
    public void Settings_keep_the_seat_and_reading()
    {
        var store = new InMemorySettings();
        var settings = new SettingsViewModel(store, new Announcements(), Strings());
        Assert.False(settings.SeatChoice.IsSet);
        settings.SeatChoice = new SeatChoice("eb-bass", "bass");
        var again = new SettingsViewModel(store, new Announcements(), Strings());
        Assert.Equal(new SeatChoice("eb-bass", "bass"), again.SeatChoice);
    }

    // ---- the real core ----

    [Fact]
    public void The_core_answers_the_seat_questions()
    {
        if (Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH") is not { Length: > 0 }) return;
        var core = NativeCoreBridge.TryCreate()!;
        var seats = core.Seats();
        Assert.Equal(18, seats.Count);
        Assert.Equal("2nd-cornet", seats[3].Id);
        Assert.Equal(["treble", "bass"], seats.Single(s => s.Id == "euphonium").Reads);
        Assert.Empty(seats.Single(s => s.Id == "percussion").Reads);

        Assert.Equal(new SeatPart("Euphonium", false, true), core.SeatPartFor("minimal", "1st-baritone"));
        Assert.Equal(new SeatPart("Euphonium", false, false), core.SeatPartFor("quartet", "eb-bass"));
        Assert.Equal(new SeatPart(null, false, false), core.SeatPartFor("quartet", "percussion"));
        Assert.Equal("Eufonium", core.PartNameNb("Euphonium"));

        // The picker's instruments, from the core: the four with parts get the app's word, the rest their seat's name.
        var catalog = new SeatCatalog(core, Strings());
        Assert.Equal(["Cornet", "Soprano", "Flugelhorn", "Tenor Horn", "Baritone", "Euphonium", "Trombone", "Bass Trombone", "E♭ Bass", "B♭ Bass", "Percussion"],
            catalog.Tiles.Select(t => t.Label));
        Assert.Equal("E♭ cornet", catalog.Tiles[1].Detail);
        Assert.Equal(["Sopran", "Althorn", "Basstrombone"],
            new SeatCatalog(core, Strings("nb-NO")).Tiles.Where(t => t.Key is "eb-soprano-cornet" or "eb-tenor-horn" or "bass-trombone").Select(t => t.Label));
    }
}
