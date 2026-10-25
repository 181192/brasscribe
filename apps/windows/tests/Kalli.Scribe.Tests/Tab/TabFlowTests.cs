using System.Net;
using Kalli.Scribe.Capture;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tests;

/// <summary>A tab app's flow (<see cref="TabFlowViewModel"/>) against a fake computer that writes the guitar-line fixture.</summary>
public class TabFlowTests : TempFolderTest
{
    private sealed class Said : IAnnouncer
    {
        public List<string> Items { get; } = [];
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Items.Add(text);
    }

    /// <summary>The key, and its arguments after it: what the app's words would be made of.</summary>
    private sealed class Keys : IStrings
    {
        public string this[string key] => key;
        public string Format(string key, params object[] args) => args.Length == 0 ? key : $"{key}({string.Join(", ", args)})";
    }

    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    private sealed class NoCapture : ICaptureService
    {
        public bool IsCapturing => false;
        public event EventHandler<CaptureLevel>? Level { add { } remove { } }
        public event EventHandler<CaptureNotice>? Notice { add { } remove { } }
        public Task<IReadOnlyList<AudioDevice>> ListMicrophonesAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<AudioDevice>>([]);
        public Task<IReadOnlyList<AudioApp>> ListAudioAppsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<AudioApp>>([]);
        public Task StartAsync(CaptureRequest request, CancellationToken ct = default) => throw new InvalidOperationException("no device");
        public Task<CaptureResult> StopAsync(CancellationToken ct = default) => throw new InvalidOperationException("not recording");
    }

    private sealed class CopyDecoder : IMediaDecoder
    {
        public Task<DecodedMedia> DecodeToWavAsync(string inputPath, string outputPath, int? sampleRate = null, CancellationToken ct = default)
        {
            File.Copy(inputPath, outputPath, overwrite: true);
            return Task.FromResult(new DecodedMedia(outputPath, TimeSpan.FromSeconds(6), false, 44100, 1));
        }
    }

    private sealed class NoDialogs : IFileDialogs
    {
        public Task<string?> PickOpenAsync(IEnumerable<string> extensions) => Task.FromResult<string?>(null);
        public Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description) => Task.FromResult<SaveTarget?>(null);
    }

    private sealed class SilentPlayers : IRecordingPlayers
    {
        public List<string> Opened { get; } = [];
        public IRecordingPlayer Open(string path, IRecordingPlayerListener listener) { Opened.Add(path); return new Silent(); }
        private sealed class Silent : IRecordingPlayer
        {
            public bool Playing => false;
            public bool Asked => false;
            public double Position => 0;
            public double Duration => 6;
            public double Speed { get; set; } = 1;
            public SecondsRange? Repeat { get; set; }
            public void Play() { }
            public void Pause() { }
            public void SeekTo(double seconds) { }
            public void Dispose() { }
        }
    }

    private const string Done = "id: 1\nevent: job\ndata: {\"id\":1,\"run\":\"guitar-line\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n";

    /// <summary>A computer that has the tab profile and writes every recording down as the guitar-line fixture.</summary>
    private static FakeHandler Computer(string profiles = """[{"name":"tab","target":"fretted","pipeline":"tab","description":"d","validated":false,"stages":[]},{"name":"solo","target":"brass","pipeline":"A-solo","description":"d","validated":false,"stages":[]}]""") =>
        new((r, _) => (r.Method.Method, r.RequestUri!.AbsolutePath) switch
        {
            ("GET", "/v1/health") => FakeHandler.Json(FakeHandler.CurrentHealth),
            ("GET", "/v1/profiles") => FakeHandler.Json(profiles),
            ("POST", "/v1/audio") => FakeHandler.Json("""{"audio_id":"a1","sha256":"00","filename":"take.wav","bytes":4}""", HttpStatusCode.Created),
            ("POST", "/v1/jobs") => FakeHandler.Json(TabFixtures.Text("guitar-line", "job.json").Replace("\"succeeded\"", "\"running\""), HttpStatusCode.Accepted),
            ("GET", "/v1/jobs/guitar-line/events") => FakeHandler.Sse(Done),
            ("GET", "/v1/jobs/guitar-line") => FakeHandler.Json(TabFixtures.Text("guitar-line", "job.json")),
            ("GET", "/v1/jobs/guitar-line/composition") => FakeHandler.Json(TabFixtures.Text("guitar-line", "composition.json")),
            ("GET", "/v1/jobs/guitar-line/musicxml") => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TabFixtures.MusicXml("guitar-line")) },
            ("GET", "/v1/jobs/guitar-line/tab") => FakeHandler.Json(TabFixtures.Text("guitar-line", "tab.json")),
            ("GET", "/v1/jobs/guitar-line/artifacts/tab.txt") => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TabFixtures.Text("guitar-line", "tab.txt")) },
            _ => new HttpResponseMessage(HttpStatusCode.NotFound),
        });

    /// <summary>Where Share or print saves: the files it was asked to write, by name.</summary>
    private sealed class SavingDialogs(string dir) : IFileDialogs
    {
        public List<string> Saved { get; } = [];
        public Task<string?> PickOpenAsync(IEnumerable<string> extensions) => Task.FromResult<string?>(null);
        public Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description)
        {
            string path = Path.Combine(dir, suggestedName);
            Saved.Add(path);
            return Task.FromResult<SaveTarget?>(new SaveTarget(File.Create(path), suggestedName));
        }
    }

    private SavingDialogs? _dialogs;
    private SavingDialogs Dialogs => _dialogs ??= new SavingDialogs(Dir);

    private (TabFlowViewModel Flow, FakeHandler Computer, SilentPlayers Players) Build(FakeHandler computer, bool firstRun = false)
    {
        var strings = new Keys();
        var said = new Said();
        var ui = new Inline();
        var store = new InMemorySettings();
        if (!firstRun) store.Set("FirstRunDone", true);
        var settings = new SettingsViewModel(store, said, strings, new FakeBrowse(() => []),
            clients: (uri, token) => new EngineClient(new HttpClient(computer), uri) { Token = token });
        var players = new SilentPlayers();
        var practice = new PracticeModel(new PracticeRecordings(Path.Combine(Dir, "recordings")), new PracticePlaces(Path.Combine(Dir, "places")), players);
        TabFlowViewModel? flow = null;
        flow = new TabFlowViewModel(Target.Fretted,
            new StartViewModel(new NoCapture(), new CopyDecoder(), new NoDialogs(), said, strings, ui, Path.Combine(Dir, "work")),
            new TranscriptionViewModel(() => flow!.Engine, said, strings, ui), settings, new YourInstrumentStore(store), practice,
            new TabExportViewModel(Dialogs, null, said, strings),
            (uri, token) => new EngineClient(new HttpClient(computer), uri) { Token = token }, said, strings,
            new ScoreLibrary(Path.Combine(Dir, "library")));
        return (flow, computer, players);
    }

    private async Task<string> Take()
    {
        var path = Path.Combine(Dir, $"take-{Guid.NewGuid():N}.wav");
        await File.WriteAllBytesAsync(path, [1, 2, 3, 4]);
        return path;
    }

    private static async Task Until(Func<bool> condition)
    {
        for (int i = 0; i < 300 && !condition(); i++) await Task.Delay(20);
        Assert.True(condition(), "timed out waiting for the flow");
    }

    [Fact]
    public void The_first_run_asks_for_the_instrument_and_then_goes_home()
    {
        var (flow, _, _) = Build(Computer(), firstRun: true);
        Assert.Equal(TabScreen.FirstRun, flow.Screen);
        flow.GetStartedCommand.Execute(null);
        Assert.Equal(TabScreen.YourInstrument, flow.Screen);
        flow.Instrument.SelectedInstrument = flow.Instrument.Instruments.Single(i => i.Value == Instrument.Bass);
        flow.Instrument.SaveCommand.Execute(null);
        Assert.Equal(TabScreen.Home, flow.Screen);
        Assert.Equal(FrettedInstrument.Bass4, flow.Instrument.Stored.Kind);
        Assert.True(flow.Settings.FirstRunDone);
    }

    [Fact]
    public async Task A_recording_is_written_down_as_a_tab_checked_and_shown_with_its_recording()
    {
        var (flow, computer, players) = Build(Computer());
        flow.Settings.Connection.Show(ConnectionState.Connected, Wire.ServerNamePrefix + "Studio PC");
        await flow.Start.OpenPathAsync(await Take());
        await Until(() => flow.Screen == TabScreen.WhatIsThis && flow.WhatIsThis.Missing != "Tab_What_Asking");

        // A guitar starts with nothing chosen; Continue says why it can't go on.
        Assert.Equal("Tab_What_ChooseOne", flow.WhatIsThis.Missing);
        Assert.False(flow.WhatIsThis.ContinueCommand.CanExecute(null));
        flow.WhatIsThis.ChooseCommand.Execute(flow.WhatIsThis.Choices.Single(c => c.Recording == Recording.Song));
        Assert.Null(flow.WhatIsThis.Missing);
        flow.WhatIsThis.ContinueCommand.Execute(null);

        await Until(() => flow.Screen == TabScreen.CheckTheSong && !flow.Check.IsReading);
        var job = computer.Requests.Single(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs").Body!;
        Assert.Contains("\"profile\":\"tab\"", job);
        Assert.Contains("\"instrument\":\"guitar-6\"", job);
        Assert.Contains("\"recording\":\"song\"", job);
        Assert.DoesNotContain("\"seat\"", job);
        Assert.Null(flow.Check.MissingText);
        Assert.Contains(flow.Check.Rows, r => r.Tag == "tuning");
        Assert.Single(flow.LibraryView.Items);

        // Show the tab: the page with its marks, and the recording in hand to practise with.
        flow.Check.ShowCommand.Execute(null);
        await Until(() => flow.TabPage.IsReady);
        Assert.Equal(TabScreen.Tab, flow.Screen);
        Assert.NotNull(flow.TabPage.Clock);
        Assert.StartsWith("Tab_Chip(", flow.TabPage.Chip);
        await Until(() => players.Opened.Count == 1);
        Assert.True(flow.TabPage.CanPlay);

        // Full screen: only Play and Leave over the tab; a tap brings the header and the player back, a second hides them.
        var page = flow.TabPage;
        Assert.True(page.ChromeShown);
        page.FullScreenCommand.Execute(null);
        Assert.False(page.ChromeShown);
        Assert.True(page.MinimalShown);
        page.TapTab();
        Assert.True(page.ChromeShown);
        Assert.False(page.ControlsHide); // nothing plays
        page.TapTab();
        Assert.True(page.MinimalShown);
        page.Assistive = true; // with a screen reader the controls stay up
        Assert.True(page.ChromeShown);
        Assert.False(page.MinimalShown);
        page.Assistive = false;
        page.IsFullScreen = false;
        Assert.True(page.ChromeShown);
        Assert.False(page.MinimalShown);

        // Back from the tab goes to Check the song for a song just written, and the sound stops.
        flow.BackCommand.Execute(null);
        Assert.Equal(TabScreen.CheckTheSong, flow.Screen);
        Assert.Equal(RecordingState.Looking, flow.TabPage.Practice.Recording);
    }

    [Fact]
    public async Task A_change_on_Check_the_song_writes_the_same_upload_down_again()
    {
        var (flow, computer, _) = Build(Computer());
        flow.Settings.Connection.Show(ConnectionState.Connected, Wire.ServerNamePrefix + "Studio PC");
        await flow.Start.OpenPathAsync(await Take());
        await Until(() => flow.Screen == TabScreen.WhatIsThis && flow.WhatIsThis.Missing != "Tab_What_Asking");
        flow.WhatIsThis.ChooseCommand.Execute(flow.WhatIsThis.Choices.Single(c => c.Recording == Recording.Instrument));
        flow.WhatIsThis.ContinueCommand.Execute(null);
        await Until(() => flow.Screen == TabScreen.CheckTheSong && !flow.Check.IsReading);

        var capo = flow.Check.Rows.Single(r => r.Tag == "capo").Change!;
        flow.Check.Choose(capo, 3);
        await Until(() => computer.Requests.Count(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs") == 2);
        await Until(() => flow.Screen == TabScreen.CheckTheSong && !flow.Transcription.IsRunning);
        var again = computer.Requests.Last(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs").Body!;
        Assert.Contains("\"capo\":3", again);
        Assert.Equal(1, computer.Requests.Count(r => r.Request.RequestUri!.AbsolutePath == "/v1/audio"));
    }

    [Fact]
    public async Task A_computer_without_the_tab_profile_is_not_sent_a_guitar()
    {
        var (flow, computer, _) = Build(Computer(profiles: """[{"name":"bass-tab","target":"fretted","pipeline":"tab","description":"d","validated":false,"stages":[]}]"""));
        flow.Settings.Connection.Show(ConnectionState.Connected, Wire.ServerNamePrefix + "Studio PC");
        await flow.Start.OpenPathAsync(await Take());
        await Until(() => flow.Screen == TabScreen.WhatIsThis && flow.WhatIsThis.Missing != "Tab_What_Asking");
        flow.WhatIsThis.ChooseCommand.Execute(flow.WhatIsThis.Choices.Single(c => c.Recording == Recording.Song));
        Assert.Equal("Tab_TooOld_Guitar", flow.WhatIsThis.Missing);
        Assert.False(flow.WhatIsThis.ContinueCommand.CanExecute(null));
        Assert.DoesNotContain(computer.Requests, r => r.Request.RequestUri!.AbsolutePath == "/v1/audio");
    }

    [Fact]
    public async Task Without_the_computer_What_is_this_says_to_connect_it_first()
    {
        var (flow, _, _) = Build(Computer());
        await flow.Start.OpenPathAsync(await Take());
        await Until(() => flow.Screen == TabScreen.WhatIsThis);
        Assert.Equal("Tab_What_ConnectFirst", flow.WhatIsThis.Missing);
    }

    [Fact]
    public async Task Every_sample_scene_shows_its_screen_from_the_fixture()
    {
        string fixture = TestPaths.RepoFile("apps/fixtures/guitar-line/tab.musicxml") is { } xml ? Path.GetDirectoryName(xml)! : throw new FileNotFoundException("guitar-line");
        foreach (var scene in TabSampleScenes.Names)
        {
            var (flow, computer, _) = Build(Computer(), firstRun: scene == "first-run");
            Assert.True(await TabSampleScenes.ShowAsync(flow, scene, fixture), scene);
            var expected = scene switch
            {
                "first-run" => TabScreen.FirstRun,
                "your-instrument" => TabScreen.YourInstrument,
                "home" or "home-offline" or "home-update" => TabScreen.Home,
                "what-is-this" or "what-is-this-offline" => TabScreen.WhatIsThis,
                "transcribing" => TabScreen.Transcribing,
                "check-the-song" => TabScreen.CheckTheSong,
                "tab" or "tab-full-screen" or "export" => TabScreen.Tab,
                _ => TabScreen.Error,
            };
            Assert.Equal(expected, flow.Screen);
            if (scene == "tab") Assert.True(flow.TabPage.IsReady && flow.TabPage.Marks.Count >= 0);
            if (scene == "tab-full-screen") Assert.True(flow.TabPage.MinimalShown);
            // The computer is there and has the tab profile: Check the song offers its changes, What is this? its Continue.
            if (scene == "check-the-song") Assert.Contains(flow.Check.Rows, r => r.HasChange);
            if (scene == "what-is-this") Assert.Null(flow.WhatIsThis.Missing);
            if (scene == "what-is-this-offline") Assert.Equal("Tab_What_ConnectFirst", flow.WhatIsThis.Missing);
            // The scenes never talk to a computer.
            Assert.Empty(computer.Requests);
        }
        Assert.False(await TabSampleScenes.ShowAsync(Build(Computer()).Flow, "tab", fixture: null));
    }

    [Fact]
    public async Task Share_or_print_offers_what_the_job_wrote_and_saves_it()
    {
        var (flow, _, _) = Build(Computer());
        flow.Settings.Connection.Show(ConnectionState.Connected, ServerNames.Prefix + "Studio PC");
        await flow.Start.OpenPathAsync(await Take());
        await Until(() => flow.Screen == TabScreen.WhatIsThis && flow.WhatIsThis.Missing != "Tab_What_Asking");
        flow.WhatIsThis.ChooseCommand.Execute(flow.WhatIsThis.Choices.Single(c => c.Recording == Recording.Instrument));
        flow.WhatIsThis.ContinueCommand.Execute(null);
        await Until(() => flow.Screen == TabScreen.CheckTheSong && !flow.Check.IsReading);
        flow.Check.ShowCommand.Execute(null);
        await Until(() => flow.CanExport);

        flow.PrepareExport();
        var options = flow.Export.Options.ToDictionary(o => o.Format);
        // The guitar-line job wrote no PDF and no MIDI (no MuseScore on the computer that made it).
        Assert.True(options[TabExportFormat.MusicXml].IsAvailable);
        Assert.True(options[TabExportFormat.TextTab].IsAvailable);
        Assert.True(options[TabExportFormat.Instructions].IsAvailable);
        Assert.False(options[TabExportFormat.Pdf].IsAvailable);
        Assert.Equal("Tab_Export_NotMade", options[TabExportFormat.Pdf].Reason);
        Assert.False(flow.Export.CanPrint);

        await flow.Export.SaveCommand.ExecuteAsync(options[TabExportFormat.TextTab]);
        await flow.Export.SaveCommand.ExecuteAsync(options[TabExportFormat.MusicXml]);
        Assert.Equal(TabFixtures.Text("guitar-line", "tab.txt"), await File.ReadAllTextAsync(Dialogs.Saved[0]));
        Assert.EndsWith(".musicxml", Dialogs.Saved[1]);
        Assert.Contains("<score-partwise", await File.ReadAllTextAsync(Dialogs.Saved[1]));
        Assert.StartsWith("Tab_Export_Saved(", flow.Export.StatusText);

        // Without the computer, only this PC's MusicXML can be had.
        flow.Settings.Connection.Show(ConnectionState.Offline, ServerNames.Prefix + "Studio PC");
        flow.PrepareExport();
        Assert.Equal([TabExportFormat.MusicXml], flow.Export.Options.Where(o => o.IsAvailable).Select(o => o.Format));
        Assert.Equal("Tab_Export_NeedsComputer", flow.Export.Options.First(o => o.Format == TabExportFormat.TextTab).Reason);
    }
}
