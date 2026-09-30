using System.Net;
using System.Xml.Linq;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The whole Play flow through the view models, with the real .resw strings, a fake engine on the
/// wire (HTTP and Server-Sent Events) and alphaTab loading the result: import → "What is this?" →
/// transcription → score, plus the unreachable-engine and cancel paths.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class AppFlowTests
{
    private sealed class Announcements : IAnnouncer
    {
        public List<(string Text, AnnouncementKind Kind)> Items { get; } = [];
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Items.Add((text, kind));
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
        public Task StartAsync(CaptureRequest request, CancellationToken ct = default) => throw new InvalidOperationException("no device");
        public Task<CaptureResult> StopAsync(CancellationToken ct = default) => throw new InvalidOperationException("not recording");
    }

    private sealed class CopyDecoder : IMediaDecoder
    {
        public Task<DecodedMedia> DecodeToWavAsync(string inputPath, string outputPath, int? sampleRate = null, CancellationToken ct = default)
        {
            File.Copy(inputPath, outputPath, overwrite: true);
            return Task.FromResult(new DecodedMedia(outputPath, TimeSpan.FromSeconds(65), false, 44100, 2));
        }
    }

    private sealed class NoDialogs : IFileDialogs
    {
        public Task<string?> PickOpenAsync(IEnumerable<string> extensions) => Task.FromResult<string?>(null);
        public Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description) => Task.FromResult<SaveTarget?>(null);
    }

    private static IStrings Strings() => new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "en-US", "Resources.resw"))));

    private const string JobRunning = """{"id":"j1","profile":"brass-band","status":"running","created":1,"stages":[{"name":"beats","status":"pending"},{"name":"arrange","status":"pending"}]}""";
    private const string JobDone = """{"id":"j1","profile":"brass-band","status":"succeeded","created":1,"stages":[],"outputs":["brass-band.musicxml","composition.json"]}""";

    /// <summary>A fake engine; <paramref name="finalEvent"/> is the job event that ends the stream.</summary>
    private static FakeHandler Engine(string finalEvent, bool reachable = true, Func<HttpRequestMessage, HttpResponseMessage?>? first = null) => new((r, _) =>
    {
        if (!reachable) throw new HttpRequestException("connection refused");
        if (first?.Invoke(r) is { } answer) return answer;
        string path = r.RequestUri!.AbsolutePath;
        return (r.Method.Method, path) switch
        {
            ("GET", "/v1/health") => FakeHandler.Json("""{"version":"0.1.0","device":"mps","auth_required":false}"""),
            ("GET", "/v1/profiles") => FakeHandler.Json("""[{"name":"solo","pipeline":"A-solo","description":"d","validated":false,"stages":[]},{"name":"brass-band","pipeline":"A","description":"d","validated":false,"stages":[]}]"""),
            ("POST", "/v1/audio") => FakeHandler.Json("""{"audio_id":"a1","sha256":"00","filename":"take.wav","bytes":4}""", HttpStatusCode.Created),
            ("POST", "/v1/jobs") => FakeHandler.Json(JobRunning, HttpStatusCode.Accepted),
            ("GET", "/v1/jobs/j1/events") => FakeHandler.Sse(
                "id: 0\nevent: stage\ndata: {\"id\":0,\"run\":\"j1\",\"type\":\"stage\",\"time\":1,\"stage\":\"beats\",\"status\":\"started\",\"fraction\":0.0}\n\n" +
                "id: 1\nevent: stage\ndata: {\"id\":1,\"run\":\"j1\",\"type\":\"stage\",\"time\":2,\"stage\":\"arrange\",\"status\":\"started\",\"fraction\":0.5,\"device\":\"mps\"}\n\n" +
                finalEvent),
            ("GET", "/v1/jobs/j1") => FakeHandler.Json(finalEvent.Contains("succeeded") ? JobDone : JobRunning.Replace("running", "cancelled")),
            ("GET", "/v1/jobs/j1/composition") => FakeHandler.Json("""{"title":"Take","voices":[],"meters":[{"tick":0,"beats":4}],"keys":[{"tick":0,"fifths":0}]}"""),
            ("GET", "/v1/jobs/j1/musicxml") => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"))) },
            ("DELETE", "/v1/jobs/j1") => FakeHandler.Json(JobRunning.Replace("running", "cancelled")),
            _ => new HttpResponseMessage(HttpStatusCode.NotFound),
        };
    });

    private static (MainViewModel Main, Announcements Said) Build(FakeHandler engine, bool firstRun = false, ScoreLibrary? library = null)
    {
        var said = new Announcements();
        var strings = Strings();
        var ui = new Inline();
        var core = new ManagedCoreBridge();
        var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var work = Path.Combine(Path.GetTempPath(), "brasscribe-flow-" + Guid.NewGuid().ToString("N"));
        MainViewModel? main = null;
        main = new MainViewModel(
            new StartViewModel(new NoCapture(), new CopyDecoder(), new NoDialogs(), said, strings, ui, work),
            new SourceKindViewModel(strings),
            new TranscriptionViewModel(() => main!.Engine, said, strings, ui),
            new ScoreViewModel(core, new PlayerViewModel(player, said, strings, ui), said, strings),
            new ExportViewModel(new ExportService(), new NoDialogs(), said, strings),
            new OutputOptionsViewModel(core, said, strings),
            new SettingsViewModel(Settings(firstRun), said, strings),
            (uri, token) => new EngineClient(new HttpClient(engine), uri) { Token = token },
            said, strings, core, library);
        return (main, said);
    }

    private static InMemorySettings Settings(bool firstRun)
    {
        var settings = new InMemorySettings();
        if (!firstRun) settings.Set("FirstRunDone", true);
        return settings;
    }

    private static async Task<string> Take()
    {
        var path = Path.Combine(Path.GetTempPath(), $"take-{Guid.NewGuid():N}.wav");
        await File.WriteAllBytesAsync(path, [1, 2, 3, 4]);
        return path;
    }

    private static async Task Until(Func<bool> condition)
    {
        for (int i = 0; i < 200 && !condition(); i++) await Task.Delay(20);
        Assert.True(condition(), "timed out waiting for the flow");
    }

    [Fact]
    public async Task Computer_scores_list_rename_open_with_evidence_change_a_note_and_delete()
    {
        string title = "Remote tune";
        bool gone = false;
        string Job() => $$"""{"id":"j1","profile":"solo","status":"succeeded","created":{{DateTimeOffset.Now.ToUnixTimeSeconds()}},"stages":[],"audio_id":"a1","title":"{{title}}","outputs":["solo.musicxml","composition.json"]}""";
        var engine = new FakeHandler((r, _) => (r.Method.Method, r.RequestUri!.AbsolutePath) switch
        {
            ("GET", "/v1/jobs") => FakeHandler.Json(gone ? "[]" : $"[{Job()}]"),
            ("GET", "/v1/jobs/j1") => FakeHandler.Json(Job()),
            ("GET", "/v1/jobs/j1/composition") => FakeHandler.Json("""
                {"title":"Remote tune","ticks_per_beat":480,"meters":[{"tick":0,"beats":4}],"keys":[{"tick":0,"fifths":0}],
                 "voices":[{"id":"melody","role":"melody","notes":[{"pitch":68,"start":480,"dur":240,"confidence":0.3,"onset_s":0.44}]}]}
                """),
            ("GET", "/v1/jobs/j1/musicxml") => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"))) },
            ("GET", "/v1/jobs/j1/evidence") => FakeHandler.Json("""
                {"models":[{"model":"swift-f0","name":"SwiftF0"},{"model":"basic-pitch","name":"Basic Pitch"}],
                 "notes":[{"voice":"melody","start":480,"pitch":68,"confidence":0.3,"onset_s":0.44,
                   "models":[{"model":"swift-f0","name":"SwiftF0","pitch":68,"agrees":true},{"model":"basic-pitch","name":"Basic Pitch","pitch":70,"agrees":false}]}]}
                """),
            ("PATCH", "/v1/runs/j1") => Rename(r),
            ("DELETE", "/v1/runs/j1") => Delete(),
            _ => new HttpResponseMessage(HttpStatusCode.NotFound),
        });
        HttpResponseMessage Rename(HttpRequestMessage r)
        {
            title = System.Text.Json.JsonDocument.Parse(r.Content!.ReadAsStringAsync().Result).RootElement.GetProperty("title").GetString()!;
            return FakeHandler.Json(Job());
        }
        HttpResponseMessage Delete()
        {
            gone = true;
            return new HttpResponseMessage(HttpStatusCode.NoContent);
        }
        var library = new ScoreLibrary(Path.Combine(Path.GetTempPath(), "brasscribe-library-" + Guid.NewGuid().ToString("N")));
        var (main, _) = Build(engine, library: library);

        // "Your scores" lists the computer's finished score, with where it is.
        await main.RefreshComputerScoresAsync();
        var remote = Assert.Single(main.LibraryItems);
        Assert.True(remote.OnComputer);
        Assert.Equal("Remote tune", remote.Title);
        Assert.Contains("On your computer", remote.Subtitle);

        // Edit title renames it on the computer, and the list follows.
        Assert.True(await main.RenameLibraryItemAsync(remote, "  Old Hundredth  "));
        Assert.Equal("Old Hundredth", Assert.Single(main.LibraryItems).Title);

        // Check the notes downloads it into this PC's library and opens the review with the evidence.
        await main.OpenLibraryItemAsync(main.LibraryItems[0], review: true);
        Assert.Equal(Screen.Review, main.Screen);
        var local = Assert.Single(main.LibraryItems);
        Assert.False(local.OnComputer);
        var review = main.Review;
        Assert.True(review.HasEvidence);
        Assert.Equal("30%", review.ConfidenceText);
        Assert.Equal("Very uncertain: it could also be a C.", review.LevelLine);
        Assert.Equal([("SwiftF0", "Same, B♭", true), ("Basic Pitch", "C", false)], review.Heard.Select(h => (h.Name, h.Heard, h.Agrees)));
        Assert.Equal(["SwiftF0: B♭", "Basic Pitch: C"], review.ChangeChoices().Select(c => c.Label));
        Assert.Equal("C", review.ChangeLabel(2));

        // Change note… to what Basic Pitch heard: the score, the Composition and the evidence follow; the review
        // stays on the note until Keep.
        Assert.False(review.ChangeNote(0));
        Assert.True(review.ChangeNote(2));
        Assert.Equal(Screen.Review, main.Screen);
        Assert.Equal("Changed to C5 (was B♭4)", review.ChangedText);
        Assert.False(review.Current!.IsKept);

        // The original pitch is kept with the score: reopened, the card still says what Brasscribe wrote,
        // and Listen plays the changed score rather than the recording.
        main.OpenLibraryItemCommand.Execute(Assert.Single(main.LibraryItems));
        Assert.Equal(Screen.Score, main.Screen);
        main.CheckNotesCommand.Execute(null);
        Assert.Equal(Screen.Review, main.Screen);
        Assert.True(review.IsChanged);
        Assert.Equal("Changed to C5 (was B♭4)", review.ChangedText);
        // Written elsewhere now (another band or key): the original is named again from the note as written.
        string id = Assert.Single(library.Entries).Id;
        var (key, kept) = Assert.Single(library.LoadReviewChanges(id));
        Assert.Equal(2, kept.Shift);
        library.SaveReviewChanges(id, new Dictionary<string, ReviewChange> { [key] = kept with { Was = "X9", WrittenMidi = 0 } });
        main.OpenLibraryItemCommand.Execute(Assert.Single(main.LibraryItems));
        main.CheckNotesCommand.Execute(null);
        Assert.Matches(@"^Changed to C5 \(was (B♭|A♯)4\)$", review.ChangedText);
        review.UndoChangeCommand.Execute(null);
        Assert.Equal("", review.ChangedText);
        main.OpenLibraryItemCommand.Execute(Assert.Single(main.LibraryItems));
        main.CheckNotesCommand.Execute(null);
        Assert.False(review.IsChanged); // Undo forgot it with the score too
        Assert.True(review.ChangeNote(2));

        review.KeepCommand.Execute(null);
        Assert.Equal(Screen.Score, main.Screen);
        var entry = Assert.Single(library.Entries);
        Assert.Contains("<step>C</step><octave>5</octave>", File.ReadAllText(entry.MusicXmlPath).Replace(" ", ""));
        var saved = library.LoadEvidence(entry)!.Notes.Single();
        Assert.Equal(70, saved.Pitch);
        Assert.Equal([false, true], saved.Models.Select(m => m.Agrees));

        // Delete on this PC brings back the computer's copy; Delete on that removes the run.
        Assert.True(await main.DeleteLibraryItemAsync(local));
        Assert.Empty(library.Entries);
        Assert.Equal(Screen.Start, main.Screen);
        Assert.True(Assert.Single(main.LibraryItems).OnComputer);
        Assert.True(await main.DeleteLibraryItemAsync(main.LibraryItems[0]));
        Assert.Empty(main.LibraryItems);
        Assert.False(main.HasLibrary);
    }

    [Fact]
    public async Task First_run_then_import_choose_make_check_choose_output_and_score()
    {
        var library = new ScoreLibrary(Path.Combine(Path.GetTempPath(), "brasscribe-library-" + Guid.NewGuid().ToString("N")));
        var (main, said) = Build(Engine("id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n"),
            firstRun: true, library: library);
        Assert.Equal(Screen.FirstRun, main.Screen);
        main.GetStartedCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
        Assert.True(main.Settings.FirstRunDone);
        Assert.False(main.HasLibrary);

        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        Assert.Contains(said.Items, a => a.Text.StartsWith("Opened take-") && a.Text.EndsWith("1 min 5 s"));
        Assert.StartsWith("take-", main.Kind.SourceLine);
        Assert.Equal("Made on this PC. Nothing goes online.", main.Kind.WhereText);
        Assert.False(main.Kind.ContinueCommand.CanExecute(null)); // nothing chosen yet: the app never guesses
        await Until(() => !main.Kind.Options.Single(o => o.Kind == SourceKind.PopRock).IsAvailable); // engine lists no pop-rock

        main.Kind.Selected = main.Kind.Options.Single(o => o.Kind == SourceKind.BrassBand);
        Assert.True(main.Kind.ContinueCommand.CanExecute(null));
        main.Kind.ContinueCommand.Execute(null);

        // One note is marked ?, so the finished score opens on "Check the notes".
        await Until(() => main.Screen == Screen.Review);
        Assert.Equal("Test tune", main.Score.Title);
        Assert.Contains(said.Items, a => a is { Text: "The score is ready", Kind: AnnouncementKind.Important });
        Assert.Contains(said.Items, a => a.Kind == AnnouncementKind.Progress && a.Text.StartsWith("50 percent. Arranging for brass band"));
        Assert.Equal(["Ready", "Beats", "Separate", "Notes", "Arrange", "Layout"], main.Transcription.Steps.Select(x => x.Key));
        Assert.All(main.Transcription.Steps, x => Assert.True(x.IsDone));
        var item = Assert.Single(main.Review.Items);
        Assert.Equal("Bar 1", main.Review.Heading);
        Assert.Equal("Written B♭, eighth note", main.Review.NoteLine);
        Assert.Equal("Finish later (1 left)", main.Review.FinishLaterText);
        Assert.True(main.HasLibrary);
        Assert.Equal("Test tune", main.LibraryItems[0].Title);
        Assert.Contains("Today · 1 to check", main.LibraryItems[0].Subtitle);
        Assert.Equal(main.Review.AllItems.Count, main.Library!.Entries[0].NotesToCheck); // Home says what Review has

        // Keeping the last note goes on to "How should the score be?"; unchanged, it just shows the score.
        main.Review.KeepCommand.Execute(null);
        Assert.True(item.IsKept);
        Assert.Equal(Screen.ChooseOutput, main.Screen);
        await main.Output.ShowScoreCommand.ExecuteAsync(main.Score.Composition);
        Assert.Equal(Screen.Score, main.Screen);
        Assert.Equal(0, main.Score.UncertainLeft);
        Assert.DoesNotContain("to check", main.LibraryItems[0].Subtitle);
        Assert.Equal(3, main.Score.Parts.Count);
        Assert.Equal(5, main.Score.Player.BarCount);
        Assert.Equal("Bar 1 of 5", main.Score.Player.PositionText);

        // Share or print starts with your own part as a PDF.
        main.OpenExportCommand.Execute(null);
        Assert.Equal(ExportScope.MyPart, main.Export.Scope);
        var pdf = main.Export.Formats.Single(f => f.Key == "Pdf");
        Assert.True(pdf is { Available: true, IsSelected: true });
        Assert.All(main.Export.Formats.Where(f => f.Key != "Pdf"), f => Assert.False(f.IsSelected));
        Assert.Equal(1, main.Export.FileCount);
        Assert.True(main.Export.Formats.Single(f => f.Key == "Braille").Available);
        main.Export.Scope = ExportScope.EveryPart;
        Assert.Equal(3, main.Export.FileCount);
        Assert.Equal("Save 3 files…", main.Export.SaveLabel);

        // The part view: back goes to the full score, then Home.
        main.Score.SelectedPartIndex = 0;
        Assert.True(main.Score.IsPartView);
        Assert.True(main.Score.Player.MuteMyPart);
        main.BackCommand.Execute(null);
        Assert.Equal(Screen.Score, main.Screen);
        Assert.False(main.Score.IsPartView);
        main.BackCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
    }

    [Theory]
    [InlineData("first-run", Screen.FirstRun)]
    [InlineData("home", Screen.Start)]
    [InlineData("home-offline", Screen.Start)]
    [InlineData("review-listening", Screen.Review)]
    [InlineData("what-is-this", Screen.SourceKind)]
    [InlineData("transcribing", Screen.Transcribing)]
    [InlineData("error", Screen.Error)]
    [InlineData("review", Screen.Review)]
    [InlineData("choose-output", Screen.ChooseOutput)]
    [InlineData("score", Screen.Score)]
    [InlineData("part", Screen.Score)]
    [InlineData("export", Screen.Score)]
    public void Screenshot_scenes_show_their_screen(string scene, Screen expected)
    {
        var (main, _) = Build(Engine(""), firstRun: true);
        Assert.True(PreviewScenes.Show(main, scene, TestPaths.Fixture("two-parts.musicxml")));
        Assert.Equal(expected, main.Screen);
        if (scene == "part") Assert.True(main.Score.IsPartView);
        if (scene == "review-listening")
        {
            Assert.True(main.Review.IsListening);
            Assert.Equal("Stop", main.Review.ListenLabel);
        }
        if (scene == "review") Assert.Equal("Listen to this bar", main.Review.ListenLabel);
        if (scene == "home") Assert.Equal("Connected to Brasscribe on Studio PC", main.Settings.Connection.StatusText);
        if (scene == "home-offline") Assert.Equal("Connect", main.Settings.Connection.ActionText);
        if (scene == "transcribing")
        {
            Assert.Equal("Writing down the notes", main.Transcription.StepHeading);
            Assert.Equal("STEP 4 OF 6 · SOLOIST WITH ORCHESTRA OR BAND", main.Transcription.Overline);
            Assert.Equal("62%", Screens.Percent(62, "en-US"));
            Assert.Equal("62\u00A0%", Screens.Percent(62, "nb-NO"));
        }
        Assert.All(PreviewScenes.Names, n => Assert.Contains(n, PreviewScenes.Names));
    }

    [Fact]
    public void The_screenshot_fixture_opens_with_notes_to_check()
    {
        var path = TestPaths.RepoFile("apps/fixtures/old-hundredth/brass-band.musicxml");
        Assert.NotNull(path);
        var (main, _) = Build(Engine(""), firstRun: true);
        Assert.True(PreviewScenes.Show(main, "review", path));
        Assert.Equal(Screen.Review, main.Screen);
        Assert.Equal(PreviewScenes.SampleTitle, main.Score.Title);
        Assert.True(main.Score.UncertainLeft > 0);
    }

    [Fact]
    public async Task Finish_later_asks_first_and_check_them_comes_back()
    {
        var (main, _) = Build(Engine("id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n"));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        main.Kind.Selected = main.Kind.Options.Single(o => o.Kind == SourceKind.BrassBand);
        main.Kind.ContinueCommand.Execute(null);
        await Until(() => main.Screen == Screen.Review);

        main.Review.FinishLaterCommand.Execute(null);
        Assert.True(main.Review.IsConfirmingFinish);
        Assert.Equal(Screen.Review, main.Screen);
        Assert.StartsWith("1 note keeps its ? mark.", main.Review.ConfirmText);
        main.Review.CancelFinishCommand.Execute(null);
        Assert.Equal(Screen.Review, main.Screen);
        main.Review.FinishLaterCommand.Execute(null);
        main.Review.ConfirmFinishCommand.Execute(null);
        Assert.Equal(Screen.ChooseOutput, main.Screen);
        main.BackCommand.Execute(null);
        Assert.Equal(Screen.Score, main.Screen);
        Assert.Equal("1 note marked ? (boxed ? = very unsure)", main.Score.UncertainText);

        main.CheckNotesCommand.Execute(null);
        Assert.Equal(Screen.Review, main.Screen);
        main.Review.KeepCommand.Execute(null);
        Assert.Equal(Screen.Score, main.Screen); // from the score, straight back to it
    }

    [Fact]
    public async Task Output_choices_arrange_again_on_the_engine_without_a_new_upload()
    {
        var engine = Engine("id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n");
        var (main, _) = Build(engine);
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        main.Kind.Selected = main.Kind.Options.Single(o => o.Kind == SourceKind.BrassBand);
        main.Kind.ContinueCommand.Execute(null);
        await Until(() => main.Screen == Screen.Review);
        main.Review.KeepCommand.Execute(null);
        Assert.Equal(Screen.ChooseOutput, main.Screen);
        Assert.True(main.Output.HasEngineJob);
        Assert.True(main.Output.DifficultyAvailable && main.Output.KeyAvailable);

        int uploads = engine.Requests.Count(r => r.Request.RequestUri!.AbsolutePath == "/v1/audio");
        main.Output.Lineup = Lineup.MinimalBand;
        main.Output.Difficulty = Difficulty.Easier;
        main.Output.KeyIndex = Array.IndexOf(OutputOptionsViewModel.Keys, "Eb");
        Assert.Equal("E♭ major (concert)", main.Output.KeyLabel);
        Assert.Equal("F major for B♭ instruments", main.Output.KeyDetail); // the part the player plays is in B♭
        main.Output.KeyUpCommand.Execute(null);
        Assert.Equal("E major (concert)", main.Output.KeyLabel);
        main.Output.KeyDownCommand.Execute(null);
        main.Output.KeyDownCommand.Execute(null);
        Assert.Equal("D major (concert)", main.Output.KeyLabel);
        main.Output.KeyUpCommand.Execute(null);
        await main.Output.ShowScoreCommand.ExecuteAsync(main.Score.Composition);
        await Until(() => engine.Requests.Count(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs") == 2);
        await Until(() => main.Screen is Screen.Score or Screen.Review && !main.Transcription.IsRunning);
        // The re-arranged score has its note to check again, then goes straight to the score.
        Assert.Equal(Screen.Review, main.Screen);
        main.Review.KeepCommand.Execute(null);
        Assert.Equal(Screen.Score, main.Screen);

        var second = engine.Requests.Last(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs").Body!;
        Assert.Contains("\"audio_id\":\"a1\"", second);
        Assert.Contains("\"lineup\":\"minimal\"", second);
        Assert.Contains("\"difficulty\":\"easier\"", second);
        Assert.Contains("\"key\":\"Eb\"", second);
        Assert.Contains("\"profile\":\"brass-band\"", second);
        Assert.Equal(uploads, engine.Requests.Count(r => r.Request.RequestUri!.AbsolutePath == "/v1/audio"));
    }

    [Fact]
    public async Task A_quartet_is_sent_as_quartet_and_labelled_quartet_in_the_library_and_share_sheet()
    {
        var engine = Engine("id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n");
        var library = new ScoreLibrary(Path.Combine(Path.GetTempPath(), "brasscribe-lib-" + Guid.NewGuid().ToString("N")));
        var (main, _) = Build(engine, library: library);
        Assert.True(main.Output.TryChooseLineup(Lineup.Quartet));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        main.Kind.Selected = main.Kind.Options.Single(o => o.Kind == SourceKind.BrassBand);
        main.Kind.ContinueCommand.Execute(null);
        await Until(() => main.Screen == Screen.Review);
        main.Review.KeepCommand.Execute(null);

        var job = engine.Requests.Single(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs").Body!;
        Assert.Contains("\"lineup\":\"quartet\"", job);
        Assert.Equal(Lineup.Quartet, main.Output.Lineup);
        Assert.Equal("quartet", library.Entries[0].Lineup);
        Assert.StartsWith("Quartet · ", main.LibraryItems[0].Subtitle);
        Assert.StartsWith("Quartet · ", main.ScoreSubtitle);

        main.Screen = Screen.Score;
        main.OpenExportCommand.Execute(null);
        Assert.Equal("Score (all 4 parts)", main.Export.ConductorLabel);
        Assert.EndsWith(" (you)", main.Export.MyPartLabel);
    }

    [Fact]
    public async Task A_solo_take_goes_back_to_the_band_and_a_refused_quartet_says_why_in_the_apps_words()
    {
        const string detail = "a quartet needs a recording of the whole group: a solo take has no harmony for the other parts";
        var engine = Engine("", first: r => r.Method == HttpMethod.Post && r.RequestUri!.AbsolutePath == "/v1/jobs"
            && (r.Content?.ReadAsStringAsync().Result ?? "").Contains("\"lineup\":\"quartet\"")
                ? FakeHandler.Json($$"""{"detail":"{{detail}}"}""", HttpStatusCode.UnprocessableEntity)
                : null);
        var (main, said) = Build(engine);
        Assert.True(main.Output.TryChooseLineup(Lineup.Quartet));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        var solo = main.Kind.Options.Single(o => o.Kind == SourceKind.Solo);

        // Choosing a solo take puts the band back before the job is sent.
        main.Kind.Selected = solo;
        main.Kind.ContinueCommand.Execute(null);
        await Until(() => engine.Requests.Any(r => r.Request.Method == HttpMethod.Post && r.Request.RequestUri!.AbsolutePath == "/v1/jobs"));
        Assert.Equal(Lineup.FullBand, main.Output.Lineup);
        Assert.False(main.Output.TryChooseLineup(Lineup.Quartet));
        Assert.Contains("\"lineup\":\"full\"", engine.Requests.First(r => r.Request.RequestUri!.AbsolutePath == "/v1/jobs").Body!);
        await Until(() => !main.Transcription.IsRunning);

        // Should a quartet reach the engine for a solo take anyway, its 422 detail is never shown.
        await main.Transcription.RunAsync(main.Kind.Source!, solo, new ArrangementOptions("quartet"));
        Assert.Equal("Needs a recording of the whole group", main.Transcription.ErrorText);
        Assert.Equal(Screen.Error, main.Screen);
        Assert.DoesNotContain(said.Items, i => i.Text.Contains("harmony", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Braille_of_a_part_comes_from_the_engine()
    {
        var handler = new FakeHandler((r, _) => r.RequestUri!.PathAndQuery == "/v1/jobs/j1/braille?part=2"
            ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("⠼⠁") }
            : new HttpResponseMessage(HttpStatusCode.NotFound));
        var engine = new EngineClient(new HttpClient(handler), new Uri("http://e:8765"));
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        var sources = new ExportSources(xml, null, null, engine, "j1", []);
        using var output = new MemoryStream();
        await new ExportService().ExportAsync(ExportFormat.Braille, sources, output, 1, new());
        Assert.Equal("⠼⠁", System.Text.Encoding.UTF8.GetString(output.ToArray()));
    }

    [Fact]
    public async Task Unreachable_engine_shows_the_error_and_lets_the_user_go_back()
    {
        var (main, said) = Build(Engine("", reachable: false));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        main.Kind.Selected = main.Kind.Options[0];
        main.Kind.ContinueCommand.Execute(null);

        await Until(() => main.Screen == Screen.Error);
        Assert.False(main.Transcription.IsRunning);
        Assert.Equal(ErrorKind.ComputerUnreachable, main.Error.Kind);
        Assert.Equal("Can't reach Brasscribe on your computer", main.Error.Title);
        Assert.StartsWith("Your recording is safe.", main.Error.Reason);
        Assert.Equal(3, main.Error.Steps.Count);
        Assert.StartsWith("1. ", main.Error.Steps[0]);
        // Commands and technical messages only in the details, never in the body.
        Assert.DoesNotContain("brasscribe serve", main.Error.Reason + string.Join(" ", main.Error.Steps));
        Assert.Contains("brasscribe serve", main.Error.Details);
        Assert.Contains("could not be reached", main.Error.Details);
        Assert.Contains(said.Items, a => a.Kind == AnnouncementKind.Important && a.Text.StartsWith("Stopped:"));

        // Try again runs the same choice again; it fails the same way here.
        main.Error.TryAgainCommand.Execute(null);
        await Until(() => main.Screen == Screen.Error && !main.Transcription.IsRunning);
        Assert.True(main.BackCommand.CanExecute(null));
        main.BackCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
        Assert.NotNull(main.Kind.Source); // the recording is kept for another try
    }

    [Fact]
    public async Task A_recording_gone_from_the_pc_says_so_instead_of_closing_the_app()
    {
        var (main, said) = Build(Engine(""));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        File.Delete(main.Kind.Source!.WavPath);
        main.Kind.Selected = main.Kind.Options[0];
        main.Kind.ContinueCommand.Execute(null);

        await Until(() => main.Screen == Screen.Error);
        Assert.False(main.Transcription.IsRunning);
        Assert.Equal(ErrorKind.RecordingUnreadable, main.Error.Kind);
        Assert.Equal("The recording can't be read", main.Error.Title);
        Assert.NotEmpty(main.Error.Steps);
        Assert.Contains(said.Items, a => a.Kind == AnnouncementKind.Important && a.Text.StartsWith("Stopped:"));
    }

    [Fact]
    public async Task Cancelled_job_returns_to_the_choice()
    {
        var (main, said) = Build(Engine("id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"cancelled\"}\n\n"));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        main.Kind.Selected = main.Kind.Options[0];
        main.Kind.ContinueCommand.Execute(null);

        await Until(() => main.Screen == Screen.SourceKind && !main.Transcription.IsRunning);
        Assert.Null(main.Transcription.ErrorText);
        Assert.Contains(said.Items, a => a.Text == "Stopped. The recording is kept.");
    }

    [Fact]
    public async Task Links_and_unknown_files_are_refused_in_plain_language()
    {
        var (main, _) = Build(Engine(""));
        await main.Start.OpenPathAsync("https://www.youtube.com/watch?v=abc");
        Assert.StartsWith("Links to streaming sites can't be downloaded", main.Start.ErrorText);
        await main.Start.OpenPathAsync("notes.docx");
        Assert.Equal("notes.docx can't be opened. Try an MP3, WAV, M4A or MP4 file, or a MusicXML score.", main.Start.ErrorText);
        Assert.Equal(Screen.Start, main.Screen);
    }

    [Fact]
    public void The_music_stand_closes_before_the_score_and_follows_the_settings()
    {
        var (main, said) = Build(Engine(""));
        main.OpenScoreFile(TestPaths.Fixture("two-parts.musicxml"));
        Assert.Equal(Screen.Score, main.Screen);
        main.Score.ShowTalkingScore = true;

        main.Settings.StandTurnPages = false;
        Assert.False(main.Score.Stand.TurnPagesWhilePlaying);
        main.Settings.StandKeepControls = true;
        Assert.True(main.Score.Stand.KeepControlsVisible);

        main.Score.Stand.Enter();
        Assert.True(main.Score.Stand.IsOpen);
        Assert.False(main.Score.ShowTalkingScore); // the stand is the music, not the text list
        Assert.Equal(main.Score.MyPartIndex, main.Score.SelectedPartIndex);

        // Back (Alt+Left, the mouse's back button) leaves the stand first, then the score.
        main.BackCommand.Execute(null);
        Assert.False(main.Score.Stand.IsOpen);
        Assert.Equal(Screen.Score, main.Screen);
        Assert.Equal(-1, main.Score.SelectedPartIndex);
        Assert.True(main.Score.ShowTalkingScore);
        Assert.Equal("Music stand closed.", said.Items[^1].Text);
        main.BackCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);

        // Any other screen closes it, quietly.
        main.Screen = Screen.Score;
        main.Score.Stand.Enter();
        main.Screen = Screen.Review;
        Assert.False(main.Score.Stand.IsOpen);

        // The hint, once dismissed, is remembered.
        main.Screen = Screen.Score;
        main.Score.Stand.Enter();
        main.Score.Stand.Tap();
        main.Score.Stand.Tap();
        Assert.True(main.Settings.StandHintSeen);
    }
}
