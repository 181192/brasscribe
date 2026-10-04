using Brasscribe.ScreenCheck;

namespace Brasscribe.ScreenCheck.Tests;

/// <summary>The catalogues' picture checks, each shown passing and failing on a picture made for it.</summary>
public class ScreenCheckTests
{
    private const uint White = 0xFFFFFFFF, Black = 0xFF000000;

    /// <summary>A line of "text": a 2-pixel stroke in <paramref name="ink"/> with anti-aliased shades beside it.</summary>
    private static Picture Text(uint ground, uint ink, int width = 40, int height = 16)
    {
        var p = Picture.Blank(width, height, ground);
        p.Fill(new Box(10, 4, 20, 2), ink);
        p.Fill(new Box(10, 6, 20, 1), Mix(ground, ink));
        return p;
    }

    private static uint Mix(uint a, uint b) => 0xFF000000
        | (((a >> 16 & 0xFF) + (b >> 16 & 0xFF)) / 2) << 16 | (((a >> 8 & 0xFF) + (b >> 8 & 0xFF)) / 2) << 8 | ((a & 0xFF) + (b & 0xFF)) / 2;

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    public void Png_reads_back_what_it_writes_with_every_filter(byte filter)
    {
        var p = Picture.Blank(7, 5, 0xFF336699);
        p[3, 2] = 0xFFFEDCBA;
        p[0, 4] = Black;
        var back = Png.Decode(Png.Encode(p, filter));
        Assert.True(back.SameAs(p));
    }

    [Fact]
    public void Png_refuses_a_file_without_its_header_or_too_large()
    {
        var good = Png.Encode(Picture.Blank(2, 2));
        var noHeader = good[..8].Concat(good[33..]).ToArray(); // the signature, then IDAT: IHDR left out
        Assert.Throws<InvalidDataException>(() => Png.Decode(noHeader));
        var huge = (byte[])good.Clone();
        huge[16] = 0x7F; // the width's top byte: about two thousand million
        Assert.Throws<InvalidDataException>(() => Png.Decode(huge));
    }

    [Fact]
    public void Contrast_follows_wcag_for_known_pairs()
    {
        Assert.Equal(21, Contrast.Ratio(White, Black), 2);
        Assert.Equal(4.54, Contrast.Ratio(White, 0xFF767676), 2);
        // Light's warning on a dark panel: Bandroom's status icon before it took Dark's colours.
        Assert.True(Contrast.Ratio(0xFF8A5A00, 0xFF202020) < 3);
        Assert.True(Contrast.Ratio(0xFFE0B65C, 0xFF202020) >= 3);
    }

    [Fact]
    public void Measure_takes_the_ground_and_the_ink_not_the_anti_aliased_shades()
    {
        var m = Contrast.Measure(Text(White, 0xFF1B1A17), new Box(0, 0, 40, 16));
        Assert.NotNull(m);
        Assert.Equal(White, m.Value.Ground);
        Assert.Equal(0xFF1B1A17u, m.Value.Text);
    }

    [Fact]
    public void Nothing_is_measured_where_nothing_is_drawn() =>
        Assert.Null(Contrast.Measure(Picture.Blank(10, 10, White), new Box(0, 0, 10, 10)));

    [Fact]
    public void Body_text_under_4_5_and_icons_under_3_are_findings()
    {
        var grey = Text(White, 0xFF777777); // 4.48:1
        Assert.Single(Contrast.Check("s", grey, [new ScreenText("Hello", new Box(0, 0, 40, 16), TextKind.Normal)]));
        Assert.Empty(Contrast.Check("s", grey, [new ScreenText("Hello", new Box(0, 0, 40, 16), TextKind.Large)]));
        Assert.Empty(Contrast.Check("s", Text(White, 0xFF767676), [new ScreenText("Hello", new Box(0, 0, 40, 16), TextKind.Normal)]));
        var icon = Text(0xFF202020, 0xFF8A5A00);
        var f = Assert.Single(Contrast.Check("flyout--dark", icon, [new ScreenText("", new Box(0, 0, 40, 16), TextKind.Icon)]));
        Assert.Equal("contrast", f.Check);
        Assert.Equal("icon U+E7BA", f.What);
        Assert.Contains("#8A5A00 on #202020", f.Detail);
    }

    [Fact]
    public void Cut_off_text_is_a_finding()
    {
        var f = Assert.Single(Contrast.Check("s", Text(White, Black), [new ScreenText("A long title", new Box(0, 0, 40, 16), TextKind.Normal, Trimmed: true)]));
        Assert.Equal("clipped", f.Check);
    }

    [Theory]
    [InlineData(24, 400, null, TextKind.Large)]
    [InlineData(20, 600, null, TextKind.Large)]
    [InlineData(20, 400, null, TextKind.Normal)]
    [InlineData(14, 400, "Segoe Fluent Icons", TextKind.Icon)]
    [InlineData(16, 400, "Segoe MDL2 Assets", TextKind.Icon)]
    public void Text_kinds(double size, int weight, string? family, TextKind kind) =>
        Assert.Equal(kind, ScreenText.KindOf(size, weight, family));

    [Fact]
    public void Boxes_scale_from_dips_outwards_and_stay_in_the_picture()
    {
        Assert.Equal(new Box(15, 15, 16, 16), Box.FromDips(10.2, 10.2, 10.4, 10.4, 1.5));
        Assert.Equal(new Box(0, 0, 5, 5), new Box(-5, -5, 10, 10).Within(20, 20));
    }

    [Fact]
    public void A_dialog_drawn_on_top_covers_the_window_where_it_is_opaque()
    {
        var window = Picture.Blank(4, 4, White);
        var dialog = new Picture(2, 1, [0, 0, 0, 255, /* transparent */ 0, 0, 0, 0]);
        window.Compose(dialog, 1, 1);
        Assert.Equal(Black, window[1, 1]);
        Assert.Equal(White, window[2, 1]);
    }

    [Fact]
    public void Diff_ignores_rounding_and_edge_shades_but_counts_new_marks()
    {
        var a = Text(White, Black);
        Assert.Equal(0, ImageDiff.Of(a, a).Changed);
        var rounding = Text(White, Black);
        rounding[0, 0] = 0xFFFDFDFD;
        Assert.Equal(0, ImageDiff.Of(a, rounding).Changed);
        var stop = Text(White, Black);
        stop.Fill(new Box(32, 10, 3, 3), Black); // a full stop: 9 pixels
        Assert.Equal(9, ImageDiff.Of(a, stop).Changed);
        Assert.True(ImageDiff.Of(a, stop).Changed > ImageDiff.FloorPixels);
    }

    [Fact]
    public void Report_lists_changed_new_and_gone_screens_and_writes_its_result_last()
    {
        string root = Directory.CreateTempSubdirectory().FullName;
        string before = Path.Combine(root, "before"), after = Path.Combine(root, "after"), report = Path.Combine(root, "report");
        Directory.CreateDirectory(before);
        Directory.CreateDirectory(after);
        Png.Save(Path.Combine(before, "home--light.png"), Text(White, Black));
        Png.Save(Path.Combine(after, "home--light.png"), Text(White, 0xFF2E6B3F));
        Png.Save(Path.Combine(before, "same--light.png"), Text(White, Black));
        Png.Save(Path.Combine(after, "same--light.png"), Text(White, Black));
        Png.Save(Path.Combine(before, "gone--light.png"), Text(White, Black));
        Png.Save(Path.Combine(after, "new--light.png"), Text(White, Black));
        var r = ScreenshotReport.Write(before, after, report, Png.Load, Png.Save);
        Assert.Equal(["home--light.png"], r.Changed);
        Assert.Equal(["new--light.png"], r.Added);
        Assert.Equal(["gone--light.png"], r.Gone);
        Assert.True(File.Exists(Path.Combine(report, "images", "home--light-diff.png")));
        Assert.Contains("\"any\": true", File.ReadAllText(Path.Combine(report, "result.json")));
    }

    [Fact]
    public void Without_a_catalogue_at_the_base_nothing_counts_as_new()
    {
        string root = Directory.CreateTempSubdirectory().FullName;
        Directory.CreateDirectory(Path.Combine(root, "after"));
        Png.Save(Path.Combine(root, "after", "home--light.png"), Text(White, Black));
        var r = ScreenshotReport.Write(Path.Combine(root, "before"), Path.Combine(root, "after"), Path.Combine(root, "report"), Png.Load, Png.Save);
        Assert.False(r.Any);
        Assert.Contains("no screen catalogue", r.Summary);
    }

    [Fact]
    public void Screens_that_did_not_keep_still_are_not_compared()
    {
        string root = Directory.CreateTempSubdirectory().FullName;
        foreach (var (dir, ink) in new[] { ("before", Black), ("after", 0xFF2E6B3Fu) })
        {
            Directory.CreateDirectory(Path.Combine(root, dir));
            Png.Save(Path.Combine(root, dir, "transcribing--light.png"), Text(White, ink));
        }
        var r = ScreenshotReport.Write(Path.Combine(root, "before"), Path.Combine(root, "after"), Path.Combine(root, "report"), Png.Load, Png.Save,
            new HashSet<string> { "transcribing--light" });
        Assert.False(r.Any);
    }

    [Fact]
    public void Verdict_exit_codes_known_findings_and_stale_entries()
    {
        var run = new CatalogueRun { Shots = ["home--light", "home--dark"] };
        Assert.Equal(0, Verdict.Of([run], []).ExitCode);
        run.Findings.Add(new Finding("home--dark", "contrast", "\"Hello\"", "2.10:1"));
        Assert.Equal(2, Verdict.Of([run], []).ExitCode);
        var known = new KnownFinding("contrast", "home--.*", "\"Hello\"", 1, "tracked");
        var v = Verdict.Of([run], [known, new KnownFinding("clipped", "home--light", ".*", 2, "fixed since")]);
        Assert.Equal(0, v.ExitCode);
        Assert.Single(v.Known);
        Assert.Equal("clipped", Assert.Single(v.Stale).Check);
        run.Failed.Add("score: TimeoutException");
        Assert.Equal(3, Verdict.Of([run], [known]).ExitCode);
        Assert.Equal(3, Verdict.Of([], []).ExitCode); // nothing taken is never a pass
    }

    [Fact]
    public void A_known_finding_without_its_issue_is_refused()
    {
        string path = Path.Combine(Directory.CreateTempSubdirectory().FullName, "known.json");
        File.WriteAllText(path, """[{ "check": "contrast", "shot": "a", "what": "b", "why": "c" }]""");
        Assert.Throws<InvalidDataException>(() => CatalogueRun.LoadKnown(path));
        File.WriteAllText(path, """[{ "check": "contrast", "shot": "a", "what": "b", "issue": 273, "why": "c" }]""");
        Assert.Equal(273, Assert.Single(CatalogueRun.LoadKnown(path)).Issue);
    }

    [Fact]
    public void Runs_round_trip_through_their_file()
    {
        string path = Path.Combine(Directory.CreateTempSubdirectory().FullName, "catalogue-en.json");
        new CatalogueRun { Shots = ["a--light"], Unsteady = ["a--light"], Findings = [new Finding("a--light", "keyboard", "Button \"Go\"", "Tab never reaches it")] }.Save(path);
        var back = CatalogueRun.Load(path);
        Assert.Equal(["a--light"], back.Shots);
        Assert.Equal("Tab never reaches it", Assert.Single(back.Findings).Detail);
    }
}
