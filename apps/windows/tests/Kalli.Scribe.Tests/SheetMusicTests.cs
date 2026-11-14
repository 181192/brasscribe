using System.Net;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tests;

/// <summary>Sheet music from a picture: the pages in hand, sending them, and what goes wrong in the app's words.</summary>
public class SheetMusicTests
{
    private static readonly byte[] Png = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13];

    private static IStrings Strings(string lang = "en-US") => new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "products", "brasscribe", "Kalli.Brasscribe", "Strings", lang, "Resources.resw"))));

    private sealed class Said : IAnnouncer
    {
        public List<string> Lines { get; } = [];
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Lines.Add(text);
    }

    private sealed class Picks(IReadOnlyList<string> files) : IFileDialogs
    {
        public Task<string?> PickOpenAsync(IEnumerable<string> extensions) => Task.FromResult<string?>(files.FirstOrDefault());
        public Task<IReadOnlyList<string>> PickOpenManyAsync(IEnumerable<string> extensions) => Task.FromResult(files);
        public Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description) => Task.FromResult<SaveTarget?>(null);
    }

    private static string File(string name, byte[] bytes)
    {
        string dir = Path.Combine(Path.GetTempPath(), "pages-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        string path = Path.Combine(dir, name);
        System.IO.File.WriteAllBytes(path, bytes);
        return path;
    }

    [Fact]
    public void A_page_is_told_by_its_first_bytes_and_one_over_50_MB_is_refused()
    {
        Assert.Equal("png", Pages.FormatOf(Png));
        Assert.Equal("jpeg", Pages.FormatOf([0xFF, 0xD8, 0xFF, 0xE0]));
        Assert.Equal("webp", Pages.FormatOf("RIFF\0\0\0\0WEBPVP8 "u8));
        Assert.Equal("pdf", Pages.FormatOf("%PDF-1.7"u8));
        Assert.Null(Pages.FormatOf("RIFF\0\0\0\0WAVEfmt "u8));
        Assert.Null(Pages.Check(File("a.png", Png)));
        // An iPhone's HEIC named .jpg is still not a page the engine reads.
        Assert.Equal(PageRefusal.NotAPage, Pages.Check(File("IMG_1.jpg", "\0\0\0\u0018ftypheic"u8.ToArray())));
        string big = File("big.pdf", "%PDF-1.7"u8.ToArray());
        using (var f = new FileStream(big, FileMode.Open)) f.SetLength(Pages.MaxPageBytes + 1);
        Assert.Equal(PageRefusal.TooLarge, Pages.Check(big));
    }

    /// <summary>Every way the engine says pages were not read, and every code it refuses them with, is one the app knows.
    /// (Windows' checkout ends the engine's lines with CRLF.)</summary>
    [Fact]
    public void The_readers_words_codes_and_limits_are_the_engines()
    {
        string sheet = System.IO.File.ReadAllText(TestPaths.RepoFile("engine/src/scribe_engine/sheet.py")!).ReplaceLineEndings("\n");
        string pages = System.IO.File.ReadAllText(TestPaths.RepoFile("engine/src/scribe_engine/pages.py")!).ReplaceLineEndings("\n");
        var said = Regex.Matches(sheet, @"^(?:NO_MUSIC|NOT_READ|ONLY_TAB) = ""([^""]+)""|^ {4}""\w+"": f?""([^""]+)"",$", RegexOptions.Multiline)
            .Select(m => (m.Groups[1].Success ? m.Groups[1].Value : m.Groups[2].Value).Replace("{pages.MAX_PAGES}", Pages.MaxPages.ToString()))
            .ToHashSet();
        Assert.Equal(said, Pages.Failures.Select(f => f.Words).ToHashSet());
        var codes = Regex.Matches(sheet + pages, @"^(?:NOT_A_PAGE|WRONG_INPUT|PAGE_TOO_LARGE|TOO_MANY_PAGES|READER_MISSING) = ""(\w+)""$", RegexOptions.Multiline)
            .Select(m => m.Groups[1].Value).ToHashSet();
        Assert.Equal(codes, new HashSet<string> { Pages.NotAPage, Pages.WrongInput, Pages.PageTooLarge, Pages.TooManyPages, Pages.ReaderMissing });
        Assert.Contains($"MAX_PAGES = {Pages.MaxPages} ", pages);
        Assert.Contains("MAX_PAGE_BYTES = 50 * 1024 * 1024", pages);
    }

    /// <summary>Each refusal and each failed read has its own words in both languages, never the engine's English.</summary>
    [Theory]
    [InlineData("en-US")]
    [InlineData("nb-NO")]
    public void Every_refusal_and_failed_read_is_said_in_the_apps_words(string lang)
    {
        var s = Strings(lang);
        var keys = new List<string>();
        foreach (var code in new[] { Pages.NotAPage, Pages.WrongInput, Pages.PageTooLarge, Pages.TooManyPages, Pages.ReaderMissing })
            keys.Add(EngineErrors.Key(new EngineException("refused", HttpStatusCode.RequestEntityTooLarge, code: code)));
        foreach (var (words, _) in Pages.Failures)
            keys.Add(EngineErrors.Key(new EngineException($"read: StageFailed: read: {words}", code: EngineException.JobFailed)));
        Assert.All(keys, k => Assert.StartsWith("Error_Pages_", k));
        Assert.All(keys, k => Assert.NotEqual(k, s[k]));
        Assert.Equal("Error_Pages_NoMusic", EngineErrors.Key(new EngineException(
            "read: StageFailed: read: no notes were found on the page\nTraceback (most recent call last):", code: EngineException.JobFailed)));
        Assert.Equal("Transcribe_Failed", EngineErrors.Key(new EngineException("beats: ValueError: no downbeat", code: EngineException.JobFailed)));
    }

    [Fact]
    public async Task The_pages_go_in_order_to_the_pages_endpoint_and_a_refusal_keeps_its_code()
    {
        string first = File("b.png", [.. Png, .. "first page"u8.ToArray()]);
        string second = File("a.pdf", "%PDF-1.7 second page"u8.ToArray());
        bool refuse = false;
        var h = new FakeHandler((r, _) => refuse
            ? FakeHandler.Json("""{"detail":"41 files: a job reads 40 pages at most","code":"too_many_pages"}""", HttpStatusCode.RequestEntityTooLarge)
            : FakeHandler.Json("""{"id":"j1","profile":"sheet","target":"brass","input":"pages","status":"queued","created":1,"stages":[]}""", HttpStatusCode.Accepted))
        { Health = FakeHandler.CurrentHealth };
        var c = new EngineClient(new HttpClient(h), new Uri("http://engine.local:8765"));

        var job = await c.CreateJobFromPagesAsync([first, second], "sheet", "Hymn");

        Assert.Equal("pages", job.Input);
        var (request, body) = h.Requests.Single();
        Assert.Equal("/v1/jobs/pages", request.RequestUri!.AbsolutePath);
        Assert.True(body!.IndexOf("first page", StringComparison.Ordinal) < body.IndexOf("second page", StringComparison.Ordinal));
        Assert.Equal(2, Regex.Matches(body, "name=\"?files\"?").Count);
        Assert.Contains("page-001.png", body);
        Assert.Contains("page-002.pdf", body);
        Assert.Matches("name=\"?profile\"?\\r\\n(.*\\r\\n)*\\r\\nsheet\\r\\n", body);
        // No audio of a score read from its notes is played: none is rendered.
        Assert.Matches("name=\"?render_audio\"?\\r\\n(.*\\r\\n)*\\r\\nfalse\\r\\n", body);

        refuse = true;
        var e = await Assert.ThrowsAsync<EngineException>(() => c.CreateJobFromPagesAsync([first], "sheet", null));
        Assert.Equal(Pages.TooManyPages, e.Code);
        Assert.Equal("Error_Pages_TooManyPages", EngineErrors.Key(e));
    }

    [Fact]
    public async Task Pages_are_kept_in_order_moved_removed_and_what_is_no_page_is_left_out()
    {
        var said = new Said();
        string one = File("one.png", Png), two = File("two.pdf", "%PDF-1.7"u8.ToArray()), song = File("take.wav", "RIFF\0\0\0\0WAVEfmt "u8.ToArray());
        var vm = new PagesViewModel(new Picks([one, song, two]), said, Strings());
        Assert.False(vm.ReadCommand.CanExecute(null));

        await vm.AddCommand.ExecuteAsync(null);

        Assert.Equal(["one.png", "two.pdf"], vm.Pages.Select(p => p.Name));
        Assert.StartsWith("One file is not a PNG, JPEG or WebP picture or a PDF", vm.StatusText);
        Assert.Equal(["Page 1", "Page 2"], vm.Pages.Select(p => p.Place));
        Assert.Equal("Move page 2 up", vm.Pages[1].MoveUpName);
        Assert.True(vm.Pages[0].IsFirst && vm.Pages[1].IsLast);
        // Read the notes waits for the computer.
        Assert.False(vm.ReadCommand.CanExecute(null));
        vm.ComputerThere = true;
        Assert.True(vm.ReadCommand.CanExecute(null));

        vm.MoveUpCommand.Execute(vm.Pages[1]);
        Assert.Equal(["two.pdf", "one.png"], vm.Pages.Select(p => p.Name));
        Assert.Equal("Page 2 is now page 1.", said.Lines.Last());
        Assert.Equal("Move page 1 down", vm.Pages[0].MoveDownName);

        IReadOnlyList<string>? sent = null;
        vm.ReadRequested += (_, pages) => sent = pages;
        vm.ReadCommand.Execute(null);
        Assert.Equal([two, one], sent);

        vm.RemoveCommand.Execute(vm.Pages[0]);
        Assert.Equal(["one.png"], vm.Pages.Select(p => p.Name));
        Assert.Equal("Page 1 is removed.", said.Lines.Last());

        vm.Add(Enumerable.Repeat(one, Pages.MaxPages + 1).ToList());
        Assert.Equal(Pages.MaxPages, vm.Pages.Count);
        Assert.Equal("At most 40 pages can be read at once. The rest were left out.", vm.StatusText);
    }

    [Fact]
    public void A_pages_run_has_its_own_steps()
    {
        Assert.Equal(["SendPages", "Read", "Layout"], TranscriptionViewModel.StepKeys(TranscriptionViewModel.PagesProfile));
        Assert.Equal("Read", TranscriptionViewModel.StepOf("read"));
        var s = Strings();
        foreach (var key in new[] { "Transcribe_Step_SendPages", "Transcribe_Step_Read", "Transcribe_Stage_SendPages", "Transcribe_Stage_Read" })
            Assert.NotEqual(key, s[key]);
    }
}
