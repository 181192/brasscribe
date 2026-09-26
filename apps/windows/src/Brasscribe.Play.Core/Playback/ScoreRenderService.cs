using AlphaTab;
using AlphaTab.Model;
using AlphaTab.Rendering;
using AlphaTab.Rendering.Utils;
using Brasscribe.Play.Core.Review;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Playback;

/// <summary>One rendered piece of the score: its position in the whole and the engine's result.</summary>
public sealed record RenderedPartial(double X, double Y, double Width, double Height, int FirstBar, int LastBar, object Result);

public sealed record RenderOutput(double TotalWidth, double TotalHeight, IReadOnlyList<RenderedPartial> Partials, BoundsLookup? Bounds);

/// <summary>
/// Renders a loaded alphaTab score with the chosen engine: "svg" (text output, used by tests) or
/// "skia" (bitmaps via AlphaSkia, used by the Windows app, because WinUI's SVG image source does not
/// draw the music font's text glyphs). Rendering runs synchronously on the calling thread.
/// </summary>
public sealed class ScoreRenderService
{
    public Settings Settings { get; } = new();

    public ScoreRenderService(string engine = "svg", double scale = 1.0, bool pageLayout = true)
    {
        Settings.Core.Engine = engine;
        Settings.Core.EnableLazyLoading = false;
        Settings.Core.IncludeNoteBounds = true;
        Settings.Display.Scale = Math.Clamp(scale, 0.5, 4.0);
        Settings.Display.LayoutMode = pageLayout ? LayoutMode.Page : LayoutMode.Horizontal;
        Settings.Player.EnableCursor = false;
    }

    /// <summary>Notation zoom, 50 to 400 percent.</summary>
    public double Scale
    {
        get => Settings.Display.Scale;
        set => Settings.Display.Scale = Math.Clamp(value, 0.5, 4.0);
    }

    /// <summary>Glyph, staff and bar-line colours of a theme.</summary>
    public ScoreRenderService WithTheme(Review.UncertaintyPalette palette)
    {
        ScoreStyler.ApplyTheme(Settings, palette);
        return this;
    }

    /// <summary>No title, subtitle or credits above the music (the app shows its own page header).</summary>
    public ScoreRenderService WithoutHeader()
    {
        ScoreStyler.HideHeader(Settings);
        return this;
    }

    /// <summary>Renders only bars <paramref name="first"/> (1-based) to first + count - 1.</summary>
    public ScoreRenderService WithBars(int first, int count)
    {
        Settings.Display.StartBar = Math.Max(1, first);
        Settings.Display.BarCount = Math.Max(1, count);
        return this;
    }

    public RenderOutput Render(Score score, IReadOnlyList<int> trackIndexes, double width)
    {
        var renderer = new ScoreRenderer(Settings) { Width = width };
        var partials = new List<RenderedPartial>();
        double totalW = 0, totalH = 0;
        Exception? error = null;
        renderer.PartialRenderFinished.On((RenderFinishedEventArgs e) =>
        {
            if (e.RenderResult is not null)
                partials.Add(new RenderedPartial(e.X, e.Y, e.Width, e.Height, (int)e.FirstMasterBarIndex, (int)e.LastMasterBarIndex, e.RenderResult));
        });
        renderer.RenderFinished.On((RenderFinishedEventArgs e) =>
        {
            totalW = e.TotalWidth;
            totalH = e.TotalHeight;
        });
        renderer.Error.On((Exception e) => error = e);
        renderer.RenderScore(score, trackIndexes.Select(i => (double)i).ToList(), null!);
        if (error is not null) throw new InvalidOperationException("alphaTab could not render the score", error);
        var bounds = renderer.BoundsLookup;
        renderer.Destroy();
        return new RenderOutput(totalW, totalH, partials, bounds);
    }

    /// <summary>PNG bytes of a Skia partial (what the WinUI view shows); null for other engines.</summary>
    public static byte[]? ToPng(object renderResult) => renderResult switch
    {
        AlphaTab.Platform.Skia.AlphaSkiaBridge.AlphaSkiaImage bridge => bridge.Image.ToPng(),
        AlphaSkia.AlphaSkiaImage image => image.ToPng(),
        _ => null,
    };

    /// <summary>Releases native Skia images of a render.</summary>
    public static void Release(RenderOutput output)
    {
        foreach (var p in output.Partials)
            if (p.Result is IDisposable d) d.Dispose();
    }
}

/// <summary>
/// Paints the notation in the theme's colours before rendering: glyphs in <c>ink</c>, staff and bar
/// lines in <c>staff</c>, and uncertain notes (head, accidentals, stem and flag) in the colour of their
/// level. The shape that carries the level (a "?" above the note, boxed below 0.4) is drawn over the
/// notation from the note bounds (<see cref="ScoreOverlay"/>); noteheads keep their normal shape.
/// </summary>
public static class ScoreStyler
{
    private const double AlphaTabTicksPerQuarter = 960;

    /// <summary>Returns how many noteheads were styled.</summary>
    public static int ApplyUncertainty(Score score, TalkingScoreDocument ts, UncertaintyPalette palette)
    {
        // The arranged MusicXML carries its own marks for print ("?" words above the note, note colours).
        // On screen the overlay draws them, and a note the player kept loses its mark, so the file's
        // versions are removed first.
        foreach (var track in score.Tracks)
            foreach (var staff in track.Staves)
                foreach (var bar in staff.Bars)
                    foreach (var voice in bar.Voices)
                        foreach (var beat in voice.Beats)
                        {
                            if (beat.Text?.Trim() == "?") beat.Text = null!;
                            beat.Style = null!;
                            foreach (var note in beat.Notes) note.Style = null!;
                        }
        int styled = 0;
        for (int t = 0; t < Math.Min(score.Tracks.Count, ts.Parts.Count); t++)
        {
            var part = ts.Parts[t];
            var staff = score.Tracks[t].Staves.FirstOrDefault();
            if (staff is null) continue;
            for (int b = 0; b < Math.Min(staff.Bars.Count, part.Bars.Count); b++)
            {
                var voice = staff.Bars[b].Voices.FirstOrDefault();
                if (voice is null) continue;
                foreach (var ev in part.Bars[b].Events)
                {
                    if (ev.Confidence is not { } conf || ev.Checked) continue;
                    var level = Scores.Note.CertaintyOf(conf);
                    if (level == Scores.Certainty.Confident) continue;
                    double tick = ev.Tick * AlphaTabTicksPerQuarter / MusicXmlTalkingScoreBuilder.TicksPerQuarter;
                    var beat = voice.Beats.FirstOrDefault(x => Math.Abs(x.PlaybackStart - tick) < 1);
                    if (beat is null) continue;
                    var rgb = level == Scores.Certainty.VeryUncertain ? palette.VeryUncertain : palette.Uncertain;
                    beat.Style = new BeatStyle();
                    beat.Style.Colors.Set(BeatSubElement.StandardNotationStem, ToColor(rgb));
                    beat.Style.Colors.Set(BeatSubElement.StandardNotationFlags, ToColor(rgb));
                    foreach (var note in beat.Notes)
                    {
                        note.Style = new NoteStyle();
                        note.Style.Colors.Set(NoteSubElement.StandardNotationNoteHead, ToColor(rgb));
                        note.Style.Colors.Set(NoteSubElement.StandardNotationAccidentals, ToColor(rgb));
                        styled++;
                    }
                }
            }
        }
        return styled;
    }

    /// <summary>Hides the score's title block; the screen puts the title in the display face itself.</summary>
    public static void HideHeader(Settings settings)
    {
        foreach (var e in new[] { NotationElement.ScoreTitle, NotationElement.ScoreSubTitle, NotationElement.ScoreArtist, NotationElement.ScoreAlbum,
                     NotationElement.ScoreWords, NotationElement.ScoreMusic, NotationElement.ScoreWordsAndMusic, NotationElement.ScoreCopyright })
            settings.Notation.Elements.Set(e, false);
    }

    /// <summary>Glyph, staff and bar-line colours of the theme, for a renderer's settings.</summary>
    public static void ApplyTheme(Settings settings, UncertaintyPalette palette)
    {
        var r = settings.Display.Resources;
        r.MainGlyphColor = ToColor(palette.Ink);
        r.SecondaryGlyphColor = ToColor(palette.TextMuted);
        r.StaffLineColor = ToColor(palette.Staff);
        r.BarSeparatorColor = ToColor(palette.Staff);
        r.BarNumberColor = ToColor(palette.TextMuted);
        r.ScoreInfoColor = ToColor(palette.Ink);
    }

    private static Color ToColor(Rgb c) => new(c.R, c.G, c.B, 255);
}
