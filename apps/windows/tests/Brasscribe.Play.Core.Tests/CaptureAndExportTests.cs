using System.Xml.Linq;
using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Tests;

[Collection(AlphaTabCollection.Name)]
public class CaptureAndExportTests
{
    private static CaptureLevel L(double s, float peak, bool silent = false) => new(TimeSpan.FromSeconds(s), peak, silent);

    [Fact]
    public void Silent_buffers_while_the_app_plays_give_the_protected_content_notice()
    {
        var w = new SilenceWatch(TimeSpan.FromSeconds(2)) { SourceReportsPlaying = true };
        Assert.Null(w.Feed(L(0, 0.2f)));
        Assert.Null(w.Feed(L(1, 0, silent: true)));
        Assert.Null(w.Feed(L(2, 0, silent: true)));
        var n = w.Feed(L(3, 0, silent: true));
        Assert.Equal(CaptureNoticeKind.SilenceWhilePlaying, n!.Kind);
        Assert.Null(w.Feed(L(4, 0, silent: true))); // reported once
        Assert.Null(w.Feed(L(5, 0.3f)));
    }

    [Fact]
    public void Silence_without_playback_says_nothing_is_playing_and_clipping_is_reported()
    {
        var w = new SilenceWatch(TimeSpan.FromSeconds(1));
        w.Feed(L(0, 0));
        Assert.Equal(CaptureNoticeKind.NothingPlaying, w.Feed(L(1.5, 0))!.Kind);
        CaptureNotice? clip = null;
        for (int i = 0; i < 10; i++) clip ??= w.Feed(L(2 + i * 0.01, 1f));
        Assert.Equal(CaptureNoticeKind.TooLoud, clip!.Kind);
    }

    [Theory]
    [InlineData(0.5f, InputBand.Good)]
    [InlineData(0.01f, InputBand.Low)]
    [InlineData(0.0001f, InputBand.Silent)]
    [InlineData(1f, InputBand.TooLoud)]
    public void Input_bands(float peak, InputBand band) => Assert.Equal(band, SilenceWatch.Band(peak));

    [Theory]
    [InlineData("C:/m/take.wav", MediaKind.Audio)]
    [InlineData("clip.MP4", MediaKind.Video)]
    [InlineData("score.musicxml", MediaKind.Score)]
    [InlineData("notes.docx", MediaKind.Unsupported)]
    [InlineData("https://www.youtube.com/watch?v=x", MediaKind.Unsupported)]
    public void Media_kinds(string path, MediaKind kind) => Assert.Equal(kind, MediaTypes.Classify(path));

    [Fact]
    public void Part_extraction_keeps_one_part()
    {
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        Assert.Equal(3, MusicXmlParts.List(xml).Count);
        var part = XDocument.Parse(MusicXmlParts.Extract(xml, "P2"));
        Assert.Single(part.Root!.Elements("part"));
        Assert.Equal("Solo Horn", (string?)part.Root!.Element("part-list")!.Element("score-part")!.Element("part-name"));
        Assert.Throws<ArgumentException>(() => MusicXmlParts.Extract(xml, "P9"));
    }

    [Fact]
    public void Talking_score_html_has_headings_per_part_and_bar()
    {
        var doc = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")));
        var html = TalkingScoreExport.ToHtml(doc, new TalkingScoreSettings(), [0]);
        Assert.Contains("<h2>Solo Cornet</h2>", html);
        Assert.Contains("<h3>Bar 1</h3>", html);
        Assert.Contains("<h3>Bars 3–4</h3>", html);
        Assert.Contains("<li>beat 2: B-flat 4, eighth note, uncertain</li>", html);
        var nb = TalkingScoreExport.ToText(doc, new TalkingScoreSettings("nb"), [1]);
        Assert.StartsWith("Test tune\n\nSolo althorn\n", nb);
    }

    [Fact]
    public async Task Offline_export_options_and_writing()
    {
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        var ts = MusicXmlTalkingScoreBuilder.Build(xml);
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(System.Text.Encoding.UTF8.GetBytes(xml));
        var sources = new ExportSources(xml, ts, player, null, null, null);
        var svc = new ExportService();
        var options = svc.Options(sources).ToDictionary(o => o.Format);

        Assert.True(options[ExportFormat.MusicXmlPart].Available);
        Assert.True(options[ExportFormat.Midi].Available);
        Assert.False(options[ExportFormat.Pdf].Available);
        Assert.Equal(ExportService.ReasonNeedsEngine, options[ExportFormat.Pdf].UnavailableReasonKey);
        Assert.False(options[ExportFormat.Braille].Available);
        Assert.Equal(ExportService.ReasonNeedsEngine, options[ExportFormat.Braille].UnavailableReasonKey);

        using var midi = new MemoryStream();
        await svc.ExportAsync(ExportFormat.Midi, sources, midi, null, new TalkingScoreSettings());
        Assert.Equal("MThd"u8.ToArray(), midi.ToArray()[..4]);

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            svc.ExportAsync(ExportFormat.Pdf, sources, new MemoryStream(), null, new TalkingScoreSettings()));
    }

    [Fact]
    public void Sfizz_is_a_seam_until_the_library_ships() =>
        Assert.Equal(SfizzEngine.IsAvailable, SfizzEngine.TryCreate(44100, 512) is { } e && Dispose(e));

    private static bool Dispose(IDisposable d)
    {
        d.Dispose();
        return true;
    }
}
