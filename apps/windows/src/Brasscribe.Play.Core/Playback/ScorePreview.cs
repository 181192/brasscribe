using AlphaSkia;
using Brasscribe.Play.Core.Review;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// Draws rendered notation and its overlays into one PNG with Skia: the same primitives the WinUI
/// score view draws (<see cref="ScoreOverlay"/>), on the theme's paper. Used for the review snippet's
/// image and to look at the score view off Windows. Tints go under the notation (they are opaque
/// token colours), lines, words and "?" marks over it.
/// </summary>
public static class ScorePreview
{
    private static string[] _sans = ["Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial"];
    private static string[] _serif = ["Instrument Serif", "Georgia", "Times New Roman"];
    private static bool _fontsReady;

    /// <summary>Registers the display face (for "ad lib." and "a tempo") when its file is available.</summary>
    public static void UseDisplayFont(byte[]? italic)
    {
        if (italic is null) return;
        var face = AlphaSkiaTypeface.Register(italic);
        if (face is not null) _serif = [face.FamilyName, .. _serif];
    }

    /// <summary>
    /// The notation of <paramref name="output"/> with its overlays. <paramref name="viewport"/> crops to a
    /// part of the score (in score coordinates), as the score view's scroll position does; alphaTab's own
    /// bar range can't be used for that, because ties that leave the range break its layout.
    /// </summary>
    public static byte[] Compose(RenderOutput output, IReadOnlyList<OverlayItem> overlay, UncertaintyPalette palette, double pad = 24, Box? viewport = null)
    {
        EnsureFonts();
        var view = viewport ?? new Box(0, 0, output.TotalWidth, output.TotalHeight);
        int w = (int)Math.Ceiling(view.W + 2 * pad), h = (int)Math.Ceiling(view.H + 2 * pad);
        using var canvas = new AlphaSkiaCanvas();
        canvas.BeginRender(w, h, 1);
        Fill(canvas, palette.Background, 0, 0, w, h);
        float ox = (float)(pad - view.X), oy = (float)(pad - view.Y);

        foreach (var item in overlay.Where(i => i.Kind is OverlayKind.AdlibTint or OverlayKind.LoopTint or OverlayKind.CursorTint))
        {
            var c = item.Kind switch { OverlayKind.AdlibTint => palette.AdLibTint, OverlayKind.LoopTint => palette.LoopTint, _ => palette.CursorTint };
            Fill(canvas, c, ox + item.Box.X, oy + item.Box.Y, item.Box.W, item.Box.H);
        }

        foreach (var p in output.Partials)
        {
            if (p.X > view.X + view.W || p.X + p.Width < view.X || p.Y > view.Y + view.H || p.Y + p.Height < view.Y) continue;
            if (viewport is not null && p.FirstBar < 0) continue; // alphaTab's credit line under the last system
            var png = ScoreRenderService.ToPng(p.Result);
            if (png is null) continue;
            using var image = AlphaSkiaImage.Decode(png);
            if (image is null) continue;
            canvas.DrawImage(image, ox + (float)p.X, oy + (float)p.Y, (float)p.Width, (float)p.Height);
        }

        foreach (var item in overlay)
        {
            var b = item.Box;
            float x = ox + (float)b.X, y = oy + (float)b.Y;
            switch (item.Kind)
            {
                case OverlayKind.CursorLine:
                    Fill(canvas, palette.Cursor, x, y, b.W, b.H);
                    break;
                case OverlayKind.LoopEdge:
                    Fill(canvas, palette.LoopEdge, x, y, b.W, b.H);
                    // bracket feet
                    bool left = overlay.Any(o => o.Kind == OverlayKind.LoopEdge && o.Box.Y == b.Y && o.Box.X > b.X);
                    Fill(canvas, palette.LoopEdge, left ? x : x - 5, y, 8, 3);
                    Fill(canvas, palette.LoopEdge, left ? x : x - 5, y + (float)b.H - 3, 8, 3);
                    break;
                case OverlayKind.LoopLabel:
                    Text(canvas, item.Text!, _sans, 600, false, 12, palette.LoopEdge, x, y + 14);
                    break;
                case OverlayKind.AdlibText:
                    Text(canvas, item.Text!, _serif, 400, true, 17, palette.Ink, x, y + 16);
                    break;
                case OverlayKind.DashedBarLine:
                    for (double d = 0; d < b.H; d += 7)
                        Fill(canvas, palette.Staff, x - 0.5f, y + (float)d, 1, Math.Min(4, b.H - d));
                    break;
                case OverlayKind.Outline:
                    Stroke(canvas, palette.Ink, x, y, b.W, b.H, 1);
                    break;
                case OverlayKind.UncertainMark:
                    Text(canvas, "?", _sans, 700, false, (float)b.H, palette.Uncertain, x + (float)b.W / 2, y + (float)b.H * 0.85f, AlphaSkiaTextAlign.Center);
                    break;
                case OverlayKind.VeryUncertainMark:
                    Stroke(canvas, palette.VeryUncertain, x, y, b.W, b.H, 1.5);
                    Text(canvas, "?", _sans, 700, false, (float)b.H * 0.8f, palette.VeryUncertain, x + (float)b.W / 2, y + (float)b.H * 0.78f, AlphaSkiaTextAlign.Center);
                    break;
            }
        }
        using var result = canvas.EndRender() ?? throw new InvalidOperationException("Skia could not draw the preview");
        return result.ToPng() ?? throw new InvalidOperationException("Skia could not encode the preview");
    }

    /// <summary>The rectangle holding bars <paramref name="first"/> to <paramref name="last"/> (0-based), with room above for marks.</summary>
    public static Box? BarsViewport(RenderOutput output, int first, int last, double above = 40, double below = 16)
    {
        if (output.Bounds is not { } bounds) return null;
        double x0 = double.MaxValue, y0 = double.MaxValue, x1 = 0, y1 = 0;
        for (int i = first; i <= last; i++)
        {
            if (bounds.FindMasterBarByIndex(i) is not { } mb) continue;
            var r = mb.VisualBounds;
            x0 = Math.Min(x0, r.X); y0 = Math.Min(y0, r.Y);
            x1 = Math.Max(x1, r.X + r.W); y1 = Math.Max(y1, r.Y + r.H);
        }
        if (x1 <= 0) return null;
        return new Box(Math.Max(0, x0 - 8), Math.Max(0, y0 - above), x1 - x0 + 16, y1 - y0 + above + below);
    }

    private static void EnsureFonts()
    {
        if (_fontsReady) return;
        AlphaSkiaCanvas.SwitchToOperatingSystemFonts();
        _fontsReady = true;
    }

    private static void Fill(AlphaSkiaCanvas c, Rgb color, double x, double y, double w, double h)
    {
        c.Color = AlphaSkiaCanvas.RgbaToColor(color.R, color.G, color.B, 255);
        c.FillRect((float)x, (float)y, (float)w, (float)h);
    }

    private static void Stroke(AlphaSkiaCanvas c, Rgb color, double x, double y, double w, double h, double width)
    {
        c.Color = AlphaSkiaCanvas.RgbaToColor(color.R, color.G, color.B, 255);
        c.LineWidth = (float)width;
        c.StrokeRect((float)x, (float)y, (float)w, (float)h);
    }

    private static void Text(AlphaSkiaCanvas c, string text, string[] families, ushort weight, bool italic, float size, Rgb color,
        float x, float baseline, AlphaSkiaTextAlign align = AlphaSkiaTextAlign.Left)
    {
        c.Color = AlphaSkiaCanvas.RgbaToColor(color.R, color.G, color.B, 255);
        using var style = new AlphaSkiaTextStyle(families, weight, italic);
        c.FillText(text, style, size, x, baseline, align, AlphaSkiaTextBaseline.Alphabetic);
    }
}
