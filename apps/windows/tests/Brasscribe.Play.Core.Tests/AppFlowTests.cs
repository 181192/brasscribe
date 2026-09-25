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
    private static FakeHandler Engine(string finalEvent, bool reachable = true) => new((r, _) =>
    {
        if (!reachable) throw new HttpRequestException("connection refused");
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

    private static (MainViewModel Main, Announcements Said) Build(FakeHandler engine)
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
            new SettingsViewModel(new InMemorySettings(), said, strings),
            (uri, token) => new EngineClient(new HttpClient(engine), uri) { Token = token },
            said, strings, core);
        return (main, said);
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
    public async Task Import_choose_transcribe_and_score()
    {
        var (main, said) = Build(Engine("id: 2\nevent: job\ndata: {\"id\":2,\"run\":\"j1\",\"type\":\"job\",\"time\":3,\"status\":\"succeeded\"}\n\n"));
        Assert.Equal(Screen.Start, main.Screen);

        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        Assert.Contains(said.Items, a => a.Text.StartsWith("Imported take-") && a.Text.EndsWith("1 min 5 s"));
        Assert.False(main.Kind.ContinueCommand.CanExecute(null)); // nothing chosen yet: the app never guesses
        await Until(() => !main.Kind.Options.Single(o => o.Kind == SourceKind.PopRock).IsAvailable); // engine lists no pop-rock

        main.Kind.Selected = main.Kind.Options.Single(o => o.Kind == SourceKind.BrassBand);
        Assert.True(main.Kind.ContinueCommand.CanExecute(null));
        main.Kind.ContinueCommand.Execute(null);

        await Until(() => main.Screen == Screen.Score);
        Assert.Equal("Test tune", main.Score.Title);
        Assert.Equal(3, main.Score.Parts.Count);
        Assert.Equal(5, main.Score.Player.BarCount);
        Assert.Equal("Bar 1 of 5", main.Score.Player.PositionText);
        Assert.Equal("1 uncertain notes to check", main.Score.UncertainText);
        Assert.Contains(said.Items, a => a is { Text: "The score is ready", Kind: AnnouncementKind.Important });
        Assert.Contains(said.Items, a => a.Kind == AnnouncementKind.Progress && a.Text.StartsWith("50 percent. Arranging for brass band"));

        // The score keys drive the talking score; the export dialog offers what works offline and via the engine.
        Assert.True(main.Score.Execute(ScoreCommand.NextUncertain));
        Assert.Equal("beat 2: B-flat 4, eighth note, uncertain", main.Score.Announcement);
        main.OpenExportCommand.Execute(null);
        var pdf = main.Export.Formats.Single(f => f.Format == ExportFormat.Pdf);
        Assert.True(pdf.Available);
        var brf = main.Export.Formats.Single(f => f.Format == ExportFormat.Braille);
        Assert.False(brf.Available);
        Assert.StartsWith("Braille export is not available yet", brf.Reason);

        main.BackCommand.Execute(null);
        Assert.Equal(Screen.Start, main.Screen);
    }

    [Fact]
    public async Task Unreachable_engine_shows_the_error_and_lets_the_user_go_back()
    {
        var (main, said) = Build(Engine("", reachable: false));
        await main.Start.OpenPathAsync(await Take());
        await Until(() => main.Screen == Screen.SourceKind);
        main.Kind.Selected = main.Kind.Options[0];
        main.Kind.ContinueCommand.Execute(null);

        await Until(() => main.Transcription.ErrorText is not null);
        Assert.Equal(Screen.Transcribing, main.Screen);
        Assert.False(main.Transcription.IsRunning);
        Assert.Contains("could not be reached", main.Transcription.ErrorText);
        Assert.Contains(said.Items, a => a.Kind == AnnouncementKind.Important && a.Text.StartsWith("Transcription stopped:"));
        Assert.True(main.BackCommand.CanExecute(null));
        main.BackCommand.Execute(null);
        Assert.Equal(Screen.SourceKind, main.Screen);
        Assert.NotNull(main.Kind.Source); // the recording is kept for another try
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
        Assert.Contains(said.Items, a => a.Text == "Transcription cancelled");
    }

    [Fact]
    public async Task Links_and_unknown_files_are_refused_in_plain_language()
    {
        var (main, _) = Build(Engine(""));
        await main.Start.OpenPathAsync("https://www.youtube.com/watch?v=abc");
        Assert.StartsWith("Links are not downloaded", main.Start.ErrorText);
        await main.Start.OpenPathAsync("notes.docx");
        Assert.Equal("notes.docx is not an audio, video or MusicXML file.", main.Start.ErrorText);
        Assert.Equal(Screen.Start, main.Screen);
    }
}
