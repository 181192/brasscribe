using System.Diagnostics;
using Brasscribe.Play.Core.Playback;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Off-thread, per-page rendering: the caller is never blocked, layout places every page, and a
/// page is drawn only when asked for. On the golden score at 200 % this measures what the UI waits for.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class LazyRenderTests(ITestOutputHelper log)
{
    [Fact]
    public async Task Layout_then_pages_on_request_without_blocking_the_caller()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(File.ReadAllBytes(TestPaths.Fixture("two-parts.musicxml")));
        using var renderer = new LazyScoreRenderer();
        var layout = await renderer.LayoutAsync(player.Score!, [0, 1, 2], 900, 1.0, AlphaTab.LayoutMode.Page);
        Assert.NotEmpty(layout.Pages);
        Assert.True(layout.Height > 0);
        Assert.NotNull(layout.Bounds?.FindMasterBarByIndex(0));
        var png = await renderer.RenderPageAsync(layout.Generation, layout.Pages[0].Id);
        Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47 }, png![..4]);

        // A newer layout makes requests for the old one come back empty.
        var newer = await renderer.LayoutAsync(player.Score!, [0], 900, 2.0, AlphaTab.LayoutMode.Page);
        Assert.Null(await renderer.RenderPageAsync(layout.Generation, layout.Pages[0].Id));
        Assert.NotNull(await renderer.RenderPageAsync(newer.Generation, newer.Pages[0].Id));
    }

    [Fact]
    public async Task At_150_percent_display_scale_pages_have_more_pixels_and_the_same_layout()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(File.ReadAllBytes(TestPaths.Fixture("two-parts.musicxml")));
        using var renderer = new LazyScoreRenderer();
        var plain = await renderer.LayoutAsync(player.Score!, [0, 1, 2], 900, 1.0, AlphaTab.LayoutMode.Page);
        var plainPng = (await renderer.RenderPageAsync(plain.Generation, plain.Pages[0].Id))!;
        var head = plain.Bounds!.FindMasterBarByIndex(1)!.VisualBounds;
        (double X, double Y, double W) plainBar = (head.X, head.Y, head.W);

        var sharp = await renderer.LayoutAsync(player.Score!, [0, 1, 2], 900, 1.0, AlphaTab.LayoutMode.Page, pixelScale: 1.5);
        var before = sharp.Bounds!.FindMasterBarByIndex(1)!.VisualBounds;
        (double X, double Y, double W) beforePaint = (before.X, before.Y, before.W);
        var sharpPng = (await renderer.RenderPageAsync(sharp.Generation, sharp.Pages[0].Id))!;

        // The same page in view units, drawn with 1.5 times the pixels.
        Assert.Equal(plain.Pages.Count, sharp.Pages.Count);
        Assert.InRange(sharp.Width, plain.Width - 2, plain.Width + 2);
        Assert.InRange(sharp.Pages[0].Height, plain.Pages[0].Height - 2, plain.Pages[0].Height + 2);
        var bar = sharp.Bounds!.FindMasterBarByIndex(1)!.VisualBounds;
        Assert.Equal(beforePaint, (bar.X, bar.Y, bar.W)); // painting a page adds no bounds in pixels
        // Bounds come back in view units, on the same system; alphaTab's spacing may differ by a few units.
        double tolerance = plain.Width * 0.05;
        Assert.InRange(bar.X, plainBar.X - tolerance, plainBar.X + tolerance);
        Assert.InRange(bar.Y, plainBar.Y - 2, plainBar.Y + 2);
        Assert.InRange(bar.W, plainBar.W - tolerance, plainBar.W + tolerance);
        static int PngWidth(byte[] png) => png[16] << 24 | png[17] << 16 | png[18] << 8 | png[19];
        Assert.InRange(PngWidth(sharpPng), PngWidth(plainPng) * 1.4, PngWidth(plainPng) * 1.6);
    }

    [SkippableFact]
    public async Task Golden_full_score_at_200_percent_keeps_every_caller_step_short()
    {
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        Skip.If(golden is null, TestPaths.Missing(TestPaths.GoldenMusicXml));
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(File.ReadAllBytes(golden));
        using var renderer = new LazyScoreRenderer();
        var tracks = player.Tracks.Select(t => t.Index).ToList();

        var sw = Stopwatch.StartNew();
        var task = renderer.LayoutAsync(player.Score!, tracks, 1600, 2.0, AlphaTab.LayoutMode.Page);
        long callerLayout = sw.ElapsedMilliseconds;
        var layout = await task;
        long layoutMs = sw.ElapsedMilliseconds;

        // A viewport of about 1400 px shows the first page or two; the view asks for those first.
        var visible = layout.Pages.Where(p => p.Y < 1400).ToList();
        long callerMax = 0, pageMax = 0;
        foreach (var page in visible.Concat(layout.Pages.Skip(visible.Count).Take(4)))
        {
            sw.Restart();
            var t = renderer.RenderPageAsync(layout.Generation, page.Id);
            callerMax = Math.Max(callerMax, sw.ElapsedMilliseconds);
            Assert.NotNull(await t);
            pageMax = Math.Max(pageMax, sw.ElapsedMilliseconds);
        }
        log.WriteLine($"golden full score 200%: caller blocked {callerLayout} ms for layout, layout {layoutMs} ms off-thread, " +
                      $"{layout.Pages.Count} pages, {visible.Count} visible; per page caller {callerMax} ms, page ready in ≤ {pageMax} ms off-thread");
        Assert.True(callerLayout < 100, $"layout blocked the caller {callerLayout} ms");
        Assert.True(callerMax < 100, $"a page request blocked the caller {callerMax} ms");
    }
}
