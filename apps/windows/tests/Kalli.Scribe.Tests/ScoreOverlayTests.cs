using System.Text.RegularExpressions;
using Kalli.Scribe.Playback;
using Kalli.Scribe.Review;
using Kalli.Scribe.Scores;
using Kalli.Scribe.TalkingScore;
using Xunit.Abstractions;

namespace Kalli.Scribe.Tests;

/// <summary>
/// The notation overlays of design/brands/brasscribe/system.md §6: "?" and boxed "?" instead of rings and brackets,
/// tints that never stack, outlines only in contrast themes, and the score tokens. With the golden
/// score present, previews of the full score, the part view and the review snippet are written as PNGs
/// (to SCRIBE_PREVIEW_DIR, or previews/ next to the test binaries) to compare with design/brands/brasscribe/mockups.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class ScoreOverlayTests(ITestOutputHelper log)
{
    private static readonly Box Head = new(100, 60, 10, 8);

    private static ScoreOverlay.Input Input(IReadOnlyList<UncertainHead>? heads = null, IReadOnlyList<Box>? loop = null,
        IReadOnlyList<AdlibRegion>? adlib = null, Box? cursorBar = null, bool contrast = false) =>
        new(heads ?? [], loop ?? [], loop is { Count: > 0 } ? "Repeat bars 12–13" : null, adlib ?? [],
            cursorBar is { } b ? b with { W = 3 } : null, cursorBar, contrast);

    [Fact]
    public void Uncertain_is_a_question_mark_and_very_uncertain_a_boxed_one_above_the_staff()
    {
        var items = ScoreOverlay.Build(Input([new(Head, Certainty.Uncertain, 50), new(Head with { X = 200 }, Certainty.VeryUncertain, 50)]));
        var q = Assert.Single(items, i => i.Kind == OverlayKind.UncertainMark);
        var boxed = Assert.Single(items, i => i.Kind == OverlayKind.VeryUncertainMark);
        Assert.Equal("?", q.Text);
        Assert.Equal("?", boxed.Text);
        // Above the staff top (50), centred on the head, about 1.6 noteheads tall.
        Assert.True(q.Box.Y + q.Box.H <= 50);
        Assert.Equal(Head.X + Head.W / 2, q.Box.X + q.Box.W / 2, 3);
        Assert.Equal(Head.H * ScoreOverlay.MarkScale, q.Box.H, 3);
        // A note above the staff gets its mark above the note.
        var high = ScoreOverlay.Build(Input([new(Head with { Y = 20 }, Certainty.Uncertain, 50)])).Single();
        Assert.True(high.Box.Y + high.Box.H <= 20);
    }

    [Fact]
    public void Confident_notes_get_no_mark_and_a_chord_gets_one()
    {
        Assert.Empty(ScoreOverlay.Build(Input([new(Head, Certainty.Confident, 50)])));
        var chord = ScoreOverlay.OnePerBeat([new(Head, Certainty.Uncertain, 50), new(Head with { Y = 52 }, Certainty.VeryUncertain, 50)]);
        var one = Assert.Single(chord);
        Assert.Equal(Certainty.VeryUncertain, one.Level);
        Assert.Equal(52, one.Head.Y); // the topmost head
        // The same beat on another staff keeps its own mark.
        Assert.Equal(2, ScoreOverlay.OnePerBeat([new(Head, Certainty.Uncertain, 50), new(Head with { Y = 160 }, Certainty.Uncertain, 150)]).Count);
    }

    [Fact]
    public void Inside_the_loop_the_loop_tint_replaces_the_ad_lib_and_cursor_tints()
    {
        var loop = new Box(200, 40, 200, 80);
        var adlib = new AdlibRegion([new Box(100, 40, 250, 80)], "ad lib.", "a tempo", new Box(350, 40, 100, 80));
        var items = ScoreOverlay.Build(Input(loop: [loop], adlib: [adlib], cursorBar: new Box(250, 40, 100, 80)));

        var adlibTint = Assert.Single(items, i => i.Kind == OverlayKind.AdlibTint);
        Assert.Equal(100, adlibTint.Box.X);
        Assert.Equal(100, adlibTint.Box.W); // cut where the loop starts
        Assert.DoesNotContain(items, i => i.Kind == OverlayKind.CursorTint);
        Assert.Single(items, i => i.Kind == OverlayKind.LoopTint);
        Assert.Equal(2, items.Count(i => i.Kind == OverlayKind.LoopEdge));
        Assert.Contains(items, i => i.Kind == OverlayKind.LoopLabel && i.Text == "Repeat bars 12–13");
        // The words and dashed bar lines stay.
        Assert.Contains(items, i => i.Kind == OverlayKind.AdlibText && i.Text == "ad lib.");
        Assert.Contains(items, i => i.Kind == OverlayKind.AdlibText && i.Text == "a tempo");
        Assert.Equal(2, items.Count(i => i.Kind == OverlayKind.DashedBarLine));
        Assert.Contains(items, i => i.Kind == OverlayKind.CursorLine);

        // Outside the loop the cursor bar is tinted, and in an ad lib bar its tint replaces the ad lib one.
        var free = ScoreOverlay.Build(Input(cursorBar: new Box(500, 40, 100, 80),
            adlib: [new AdlibRegion([new Box(400, 40, 300, 80)])]));
        Assert.Contains(free, i => i.Kind == OverlayKind.CursorTint);
        Assert.Equal([400.0, 600.0], free.Where(i => i.Kind == OverlayKind.AdlibTint).Select(i => i.Box.X).Order());
    }

    [Fact]
    public void Contrast_themes_get_outlines_and_no_tints()
    {
        var items = ScoreOverlay.Build(Input(loop: [new Box(200, 40, 200, 80)],
            adlib: [new AdlibRegion([new Box(0, 40, 100, 80)], "ad lib.")], cursorBar: new Box(500, 40, 100, 80), contrast: true,
            heads: [new(Head, Certainty.VeryUncertain, 50)]));
        Assert.DoesNotContain(items, i => i.Kind is OverlayKind.AdlibTint or OverlayKind.LoopTint or OverlayKind.CursorTint);
        Assert.Equal(2, items.Count(i => i.Kind == OverlayKind.Outline));
        Assert.Contains(items, i => i.Kind == OverlayKind.LoopEdge);
        Assert.Contains(items, i => i.Kind == OverlayKind.VeryUncertainMark);
        Assert.Contains(items, i => i.Kind == OverlayKind.CursorLine);
    }

    // Brasscribe's hidden Pink palette recolours the chrome; of the notation only Pink light's very uncertain differs
    // (design/brands/brasscribe/system.md §10). The product hands that colour in; it must be the generated theme's.
    [SkippableFact]
    public void Pink_lights_very_uncertain_matches_the_generated_Pink_theme()
    {
        var theme = TestPaths.RepoFile("design/brands/brasscribe/dist/windows/BrasscribePinkTheme.xaml");
        Skip.If(theme is null, TestPaths.Missing("design/brands/brasscribe/dist/windows/BrasscribePinkTheme.xaml"));
        var product = TestPaths.RepoFile("apps/windows/products/brasscribe/Kalli.Brasscribe/Product.cs");
        Skip.If(product is null, TestPaths.Missing("apps/windows/products/brasscribe/Kalli.Brasscribe/Product.cs"));
        string given = Regex.Match(File.ReadAllText(product), "VeryUncertainLight: \"(#[0-9A-F]{6})\"").Groups[1].Value;
        Assert.NotEqual("", given);
        string xaml = File.ReadAllText(theme);
        foreach (var (key, kind) in new[] { ("Light", ThemeKind.Light), ("Dark", ThemeKind.Dark) })
        {
            var dict = Regex.Match(xaml, $"<ResourceDictionary x:Key=\"{key}\">(.*?)</ResourceDictionary>", RegexOptions.Singleline).Groups[1].Value;
            string Color(string name) => "#" + Regex.Match(dict, $"<Color x:Key=\"(?:Scribe|Bc){name}Color\">#FF([0-9A-F]{{6}})</Color>").Groups[1].Value;
            var pink = UncertaintyPalette.For(kind, given);
            Assert.Equal(Color("VeryUncertain"), pink.VeryUncertain.ToString());
            Assert.Equal(Color("Uncertain"), pink.Uncertain.ToString());
            Assert.Equal(Color("Ink"), pink.Ink.ToString());
            Assert.Equal(pink with { VeryUncertain = UncertaintyPalette.For(kind).VeryUncertain }, UncertaintyPalette.For(kind));
        }
        Assert.NotEqual(UncertaintyPalette.Light.VeryUncertain, UncertaintyPalette.For(ThemeKind.Light, given).VeryUncertain);
        Assert.Same(UncertaintyPalette.Light, UncertaintyPalette.For(ThemeKind.Light, null));
    }

    [SkippableFact]
    public void Score_colours_match_the_generated_theme()
    {
        var theme = TestPaths.RepoFile("design/brands/brasscribe/dist/windows/BrasscribeTheme.xaml");
        Skip.If(theme is null, TestPaths.Missing("design/brands/brasscribe/dist/windows/BrasscribeTheme.xaml"));
        string xaml = File.ReadAllText(theme);
        foreach (var (key, palette) in new[] { ("Light", UncertaintyPalette.Light), ("Dark", UncertaintyPalette.Dark) })
        {
            var dict = Regex.Match(xaml, $"<ResourceDictionary x:Key=\"{key}\">(.*?)</ResourceDictionary>", RegexOptions.Singleline).Groups[1].Value;
            string Color(string name) => "#" + Regex.Match(dict, $"<Color x:Key=\"(?:Scribe|Bc){name}Color\">#FF([0-9A-F]{{6}})</Color>").Groups[1].Value;
            Assert.Equal(Color("Bg"), palette.Background.ToString());
            Assert.Equal(Color("Surface"), palette.Surface.ToString());
            Assert.Equal(Color("Text"), palette.Text.ToString());
            Assert.Equal(Color("TextMuted"), palette.TextMuted.ToString());
            Assert.Equal(Color("Ink"), palette.Ink.ToString());
            Assert.Equal(Color("Line"), palette.Staff.ToString());
            Assert.Equal(Color("Uncertain"), palette.Uncertain.ToString());
            Assert.Equal(Color("VeryUncertain"), palette.VeryUncertain.ToString());
            Assert.Equal(Color("Cursor"), palette.Cursor.ToString());
            Assert.Equal(Color("CursorTint"), palette.CursorTint.ToString());
            Assert.Equal(Color("Focus"), palette.Focus.ToString());
            Assert.Equal(Color("AdlibTint"), palette.AdLibTint.ToString());
            Assert.Equal(Color("LoopTint"), palette.LoopTint.ToString());
            Assert.Equal(Color("LoopEdge"), palette.LoopEdge.ToString());
            Assert.Equal(Color("Error"), palette.Error.ToString());
        }
    }

    [Fact]
    public void Very_uncertain_notes_keep_a_normal_notehead()
    {
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        player.LoadScore(System.Text.Encoding.UTF8.GetBytes(xml));
        var ts = MusicXmlTalkingScoreBuilder.Build(xml);
        foreach (var ev in ts.Parts[0].Bars[0].Events) ev.Confidence = 0.2;
        Assert.True(ScoreStyler.ApplyUncertainty(player.Score!, ts, UncertaintyPalette.Light) > 0);
        Assert.DoesNotContain(player.Score!.Tracks[0].Staves[0].Bars[0].Voices[0].Beats.SelectMany(b => b.Notes), n => n.IsGhost);
    }

    /// <summary>On Windows the "?" marks and the loop label are drawn in Windows' own text face, not in a stand-in.</summary>
    [SkippableFact]
    public void The_preview_finds_the_Windows_text_face()
    {
        Skip.IfNot(OperatingSystem.IsWindows(), "the families are Windows' own");
        string? Resolved(string family)
        {
            using var face = AlphaSkia.AlphaSkiaTypeface.Create(family, (ushort)400, false);
            return face?.FamilyName;
        }
        var families = ScorePreview.SansFamilies;
        foreach (var family in families.Concat(["Segoe UI Variable", "Segoe UI", "No Such Family 4711"]))
            log.WriteLine($"{family} -> {Resolved(family) ?? "(none)"}");
        string? first = Resolved(families[0]), missing = Resolved("No Such Family 4711");
        Assert.True(first is not null && first.StartsWith("Segoe UI Variable", StringComparison.Ordinal) && first != missing,
            $"'{families[0]}' resolves to '{first ?? "(none)"}'; a family that does not exist resolves to '{missing ?? "(none)"}'");
    }

    /// <summary>Full score (bars 9–16 with a loop and the cursor), the solo part and a review snippet, light and dark.</summary>
    [SkippableFact]
    [Trait("Category", "Slow")] // seconds; the fast tier filters it out (docs/shared/dev/verify.md)
    public void Golden_previews()
    {
        var xmlPath = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var compPath = TestPaths.RepoFile(TestPaths.GoldenComposition);
        Skip.If(xmlPath is null, TestPaths.Missing(TestPaths.GoldenMusicXml));
        Skip.If(compPath is null, TestPaths.Missing(TestPaths.GoldenComposition));
        string dir = Environment.GetEnvironmentVariable("SCRIBE_PREVIEW_DIR") is { Length: > 0 } d ? d : TestPaths.Output("previews");
        Directory.CreateDirectory(dir);
        ScorePreview.UseDisplayFont(TestPaths.RepoFile("design/brands/brasscribe/brand/fonts/InstrumentSerif-Italic.ttf") is { } f ? File.ReadAllBytes(f) : null);

        string xml = File.ReadAllText(xmlPath);
        var composition = CompositionJson.Parse(File.ReadAllText(compPath));
        var doc = MusicXmlTalkingScoreBuilder.Build(xml, composition);
        ReviewGroups.Attach(doc, composition);

        foreach (var palette in new[] { UncertaintyPalette.Light, UncertaintyPalette.Dark })
        {
            string theme = palette.Theme.ToString().ToLowerInvariant();
            using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
            player.LoadScore(System.Text.Encoding.UTF8.GetBytes(xml));
            var score = player.Score!;
            ScoreStyler.ApplyUncertainty(score, doc, palette);
            var all = player.Tracks.Select(t => t.Index).ToList();

            // Full score: bars 9–16, repeat bars 12–13, the cursor in bar 13.
            var full = new ScoreRenderService("skia", 0.8, pageLayout: false).WithTheme(palette).Render(score, all, 100000);
            var bounds = full.Bounds!;
            var cursorBar = ScoreGeometry.BarBox(bounds, 12);
            var overlay = ScoreOverlay.Build(new(ScoreGeometry.UncertainHeads(score, bounds, doc, all),
                ScoreGeometry.RangeBoxes(bounds, 11, 12), "Repeat bars 12–13", ScoreGeometry.AdlibRegions(bounds, doc),
                cursorBar is { } cb ? cb with { X = cb.X + cb.W / 3, W = 3 } : null, cursorBar, false));
            Assert.Contains(overlay, i => i.Kind is OverlayKind.UncertainMark or OverlayKind.VeryUncertainMark);
            Write(dir, $"score-{theme}.png", ScorePreview.Compose(full, overlay, palette, viewport: ScorePreview.BarsViewport(full, 8, 15)));
            ScoreRenderService.Release(full);

            // Part view: the solo part, bars 1–9, page layout (the page header is drawn by the app).
            int solo = Math.Max(0, player.Tracks.ToList().FindIndex(t => t.Name.Contains("Solo Cornet", StringComparison.OrdinalIgnoreCase)));
            var partService = new ScoreRenderService("skia", 1.1, pageLayout: true).WithTheme(palette).WithoutHeader();
            var part = partService.Render(score, [solo], 1000);
            var pb = part.Bounds!;
            var partOverlay = ScoreOverlay.Build(new(ScoreGeometry.UncertainHeads(score, pb, doc, [solo]), [], null,
                ScoreGeometry.AdlibRegions(pb, doc), null, ScoreGeometry.BarBox(pb, 3, solo), false)
                { Groups = ScoreGeometry.GroupBrackets(score, pb, doc, [solo]) });
            Write(dir, $"part-{theme}.png", ScorePreview.Compose(part, partOverlay, palette,
                viewport: ScorePreview.BarsViewport(part, 0, 8, above: 60) is { } pv ? pv with { X = 0, W = part.TotalWidth } : null));
            ScoreRenderService.Release(part);

            // Review snippet: two bars of the solo part around the first uncertain note.
            int bar = doc.Parts[solo].Bars.FindIndex(b => b.Events.Any(e => e.IsUncertain && e.ReviewNotes > 1));
            if (bar < 0) bar = doc.Parts[solo].Bars.FindIndex(b => b.Events.Any(e => e.IsUncertain));
            var lead = doc.Parts[solo].Bars[bar].Events.First(e => e.IsUncertain);
            var snippet = new ScoreRenderService("skia", 1.3, pageLayout: false).WithTheme(palette).WithoutHeader().Render(score, [solo], 100000);
            var sb = snippet.Bounds!;
            Write(dir, $"review-{theme}.png", ScorePreview.Compose(snippet,
                ScoreOverlay.Build(new(ScoreGeometry.UncertainHeads(score, sb, doc, [solo]), [], null, [], null, null, false)
                {
                    Groups = ScoreGeometry.GroupBrackets(score, sb, doc, [solo]),
                    Selection = ScoreGeometry.FocusBox(score, sb, solo, bar, lead.Tick) is { } note && ScoreGeometry.BarBox(sb, bar, solo) is { } staff ? (note, staff) : null,
                }), palette, pad: 16,
                viewport: ScorePreview.BarsViewport(snippet, bar, bar + 1)));
            ScoreRenderService.Release(snippet);
        }
        log.WriteLine($"previews in {dir}");
    }

    private static bool Covers(Box a, Box b) =>
        a.X < b.X + b.W && b.X < a.X + a.W && a.Y < b.Y + b.H && b.Y < a.Y + a.H;

    /// <summary>
    /// alphaTab's "alphaTab.net" mark must stay visible. Whatever the loop, the cursor, the groups and the "?" marks are,
    /// nothing planned is drawn over its area.
    /// </summary>
    [Fact]
    public void Nothing_is_drawn_over_the_attribution()
    {
        var area = new Box(300, 10, 78, 40);
        // A loop over the whole first line, a bar tint and a cursor inside the area, "?" marks in and beside it, a group
        // bracket across it, and an ad lib region over it.
        var loopBox = new Box(0, 10, 378, 130);
        var heads = new List<UncertainHead>
        {
            new(new Box(320, 60, 10, 8), Certainty.Uncertain, 50),
            new(new Box(340, 62, 10, 8), Certainty.VeryUncertain, 50),
            new(new Box(100, 60, 10, 8), Certainty.Uncertain, 50),
        };
        var input = new ScoreOverlay.Input(heads, [loopBox], "Repeat bars 1–4", [new AdlibRegion([new Box(250, 10, 128, 130)], "ad lib.")],
            new Box(330, 10, 3, 130), new Box(250, 10, 128, 130), false)
        {
            Groups = [new Box(310, 20, 60, 100)],
            Selection = (new Box(335, 55, 10, 8), new Box(300, 50, 78, 40)),
            Attribution = area,
        };
        var items = ScoreOverlay.Build(input).Concat(ScoreOverlay.Cursor(new Box(330, 10, 3, 130), new Box(250, 10, 128, 130), [], false, area)).ToList();
        Assert.NotEmpty(items);
        Assert.DoesNotContain(items, i => Covers(i.Box, area));
        // Marks and labels are kept (lifted), not dropped; the "?" of the head beside the area stays where it was.
        Assert.Equal(3, items.Count(i => i.Kind is OverlayKind.UncertainMark or OverlayKind.VeryUncertainMark));
        Assert.Equal(1, items.Count(i => i.Kind == OverlayKind.LoopLabel));
        // Cutting leaves the rest of a bracket: the loop's right edge (x 375) is cut above the area's bottom, not removed.
        Assert.Equal(2, items.Count(i => i.Kind == OverlayKind.LoopEdge));
        Assert.Contains(items, i => i.Kind == OverlayKind.LoopEdge && i.Box.X > 370 && i.Box.Y >= area.Y + area.H);
    }

    /// <summary>An overlay that is clear of the area is left exactly as it was.</summary>
    [Fact]
    public void Overlays_clear_of_the_attribution_are_unchanged()
    {
        var plain = ScoreOverlay.Build(Input([new(Head, Certainty.Uncertain, 50)], loop: [new Box(0, 40, 90, 80)]));
        var kept = ScoreOverlay.Build(Input([new(Head, Certainty.Uncertain, 50)], loop: [new Box(0, 40, 90, 80)]) with { Attribution = new Box(300, 10, 78, 40) });
        Assert.Equal(plain, kept);
    }

    /// <summary>The area follows the first system's last bar and the notation scale; short scores have none.</summary>
    [SkippableFact]
    public void The_attribution_area_is_at_the_end_of_the_first_system()
    {
        var path = TestPaths.RepoFile("apps/fixtures/old-hundredth/brass-band.musicxml");
        Skip.If(path is null, TestPaths.Missing("apps/fixtures/old-hundredth/brass-band.musicxml"));
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(File.ReadAllBytes(path!));
        var score = player.Score!;
        Assert.True(score.MasterBars.Count > 10);
        var all = player.Tracks.Select(t => t.Index).ToList();
        foreach (double scale in new[] { 1.0, 1.5 })
        {
            var result = new ScoreRenderService("skia", scale, pageLayout: true).Render(score, all, 100000);
            var bounds = result.Bounds!;
            var area = ScoreGeometry.AttributionArea(score, bounds, all.Count, scale);
            Assert.NotNull(area);
            var system = bounds.StaffSystems[0];
            var lastBar = system.Bars[^1];
            Assert.Equal(lastBar.RealBounds.X + lastBar.RealBounds.W, area!.Value.X + area.Value.W, 3);
            Assert.Equal(78 * scale, area.Value.W, 3);
            Assert.Equal(system.VisualBounds.Y, area.Value.Y, 3);
            Assert.True(area.Value.H > 0, "the band above the top staff has room for the mark");
            ScoreRenderService.Release(result);
        }
        // Ten bars on two parts or fewer carry no mark.
        var shortXml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        using var small = new AlphaTabScorePlayer(new BufferedSynthOutput());
        small.LoadScore(System.Text.Encoding.UTF8.GetBytes(shortXml));
        if (small.Score!.MasterBars.Count <= 10)
        {
            var r = new ScoreRenderService("skia", 1.0, pageLayout: true).Render(small.Score, small.Tracks.Select(t => t.Index).Take(2).ToList(), 100000);
            Assert.Null(ScoreGeometry.AttributionArea(small.Score, r.Bounds!, 2, 1.0));
            ScoreRenderService.Release(r);
        }
    }

    private static void Write(string dir, string name, byte[] png)
    {
        Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47 }, png[..4]);
        File.WriteAllBytes(Path.Combine(dir, name), png);
    }
}
