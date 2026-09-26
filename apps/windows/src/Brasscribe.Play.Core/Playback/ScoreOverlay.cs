using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.Playback;

/// <summary>What an overlay item on the notation is (design/system.md §6; the colours are the Bc score tokens).</summary>
public enum OverlayKind
{
    /// <summary>The bar under the playback cursor: <c>cursor-tint</c>.</summary>
    CursorTint,
    /// <summary>The 3 epx playback cursor line: <c>cursor</c>.</summary>
    CursorLine,
    /// <summary>The repeated bars: <c>loop-tint</c>.</summary>
    LoopTint,
    /// <summary>A bracket at either end of the repeated bars: <c>loop-edge</c>.</summary>
    LoopEdge,
    /// <summary>"Repeat bars 12–13" above the first repeated bar, in <c>loop-edge</c>.</summary>
    LoopLabel,
    /// <summary>Bars without a steady beat: <c>adlib-tint</c>.</summary>
    AdlibTint,
    /// <summary>The italic "ad lib." / "a tempo" text above the staff, in <c>ink</c>.</summary>
    AdlibText,
    /// <summary>A dashed bar line at the edge of the ad lib bars, in <c>staff</c>.</summary>
    DashedBarLine,
    /// <summary>An outline instead of a tint (contrast themes, where no tints are drawn).</summary>
    Outline,
    /// <summary>A "?" above an uncertain note, in <c>uncertain</c>.</summary>
    UncertainMark,
    /// <summary>A boxed "?" above a very uncertain note (confidence below 0.4), in <c>very-uncertain</c>.</summary>
    VeryUncertainMark,
}

public sealed record OverlayItem(OverlayKind Kind, Box Box, string? Text = null);

/// <summary>An uncertain notehead with its level and the top of its staff.</summary>
public sealed record UncertainHead(Box Head, Certainty Level, double StaffTop);

/// <summary>
/// A run of ad lib bars, one box per system line. The arranged score engraves "ad lib." and "a tempo"
/// itself; <see cref="Label"/> and <see cref="EndLabel"/> are only for scores that don't.
/// </summary>
public sealed record AdlibRegion(IReadOnlyList<Box> Boxes, string? Label = null, string? EndLabel = null, Box? EndBar = null);

/// <summary>
/// Plans the overlays drawn over the rendered notation, as plain primitives so the WinUI score view
/// and the Skia preview draw exactly the same thing. The rules (design/system.md §1 and §6):
/// uncertainty is a "?" above the note and a boxed "?" below 0.4, in the note's colour, never rings,
/// diamonds or brackets; tints never stack (inside the repeated bars the loop tint replaces the
/// ad lib and cursor-bar tints, while the ad lib text and dashed bar lines stay); contrast themes
/// get no tints at all, only outlines.
/// </summary>
public static class ScoreOverlay
{
    /// <summary>Height of a "?" mark as a multiple of the notehead height (about one staff space).</summary>
    public const double MarkScale = 1.6;
    public const double MarkGap = 3;
    public const double CursorWidth = 3;
    public const double LoopEdgeWidth = 3;

    public sealed record Input(
        IReadOnlyList<UncertainHead> Uncertain,
        IReadOnlyList<Box> Loop,
        string? LoopLabel,
        IReadOnlyList<AdlibRegion> Adlib,
        Box? CursorBeat,
        Box? CursorBar,
        bool HighContrast);

    public static IReadOnlyList<OverlayItem> Build(Input input)
    {
        var items = new List<OverlayItem>();
        bool tints = !input.HighContrast;

        // The cursor-bar tint is drawn outside the repeated bars only, and replaces the ad lib tint in its bar.
        Box? cursorTint = input.CursorBar is { } cursorBar && tints && !input.Loop.Any(l => Overlaps(l, cursorBar)) ? cursorBar : null;
        var covered = cursorTint is { } ct ? input.Loop.Append(ct).ToList() : input.Loop;

        // Ad lib: the tint only outside the repeated bars; the words and dashed bar lines always.
        foreach (var region in input.Adlib)
        {
            foreach (var box in region.Boxes)
            {
                if (tints)
                    foreach (var piece in Subtract(box, covered)) items.Add(new(OverlayKind.AdlibTint, piece));
                else
                    items.Add(new(OverlayKind.Outline, box));
                items.Add(new(OverlayKind.DashedBarLine, new Box(box.X, box.Y, 0, box.H)));
                items.Add(new(OverlayKind.DashedBarLine, new Box(box.X + box.W, box.Y, 0, box.H)));
            }
            if (region.Boxes.Count > 0 && region.Label is { } label)
            {
                var first = region.Boxes[0];
                items.Add(new(OverlayKind.AdlibText, new Box(first.X + 6, first.Y - 22, first.W, 20), label));
            }
            if (region.EndLabel is { } end && region.EndBar is { } after)
                items.Add(new(OverlayKind.AdlibText, new Box(after.X + 6, after.Y - 22, after.W, 20), end));
        }

        // Loop: tint (or outline), a bracket at each end and the label.
        for (int i = 0; i < input.Loop.Count; i++)
        {
            var box = input.Loop[i];
            items.Add(new(tints ? OverlayKind.LoopTint : OverlayKind.Outline, box));
            items.Add(new(OverlayKind.LoopEdge, new Box(box.X, box.Y, LoopEdgeWidth, box.H)));
            items.Add(new(OverlayKind.LoopEdge, new Box(box.X + box.W - LoopEdgeWidth, box.Y, LoopEdgeWidth, box.H)));
            if (i == 0 && input.LoopLabel is { } label)
                items.Add(new(OverlayKind.LoopLabel, new Box(box.X + 8, box.Y - 20, box.W, 18), label));
        }

        items.AddRange(Cursor(input.CursorBeat, input.CursorBar, input.Loop, input.HighContrast));

        // Uncertainty: above whichever is higher, the staff or the notehead, centred on the head.
        foreach (var head in input.Uncertain)
        {
            if (head.Level == Certainty.Confident) continue;
            double size = Math.Max(10, head.Head.H * MarkScale);
            double bottom = Math.Min(head.StaffTop, head.Head.Y) - MarkGap;
            double cx = head.Head.X + head.Head.W / 2;
            var kind = head.Level == Certainty.VeryUncertain ? OverlayKind.VeryUncertainMark : OverlayKind.UncertainMark;
            items.Add(new(kind, new Box(cx - size / 2, bottom - size, size, size), "?"));
        }
        return items;
    }

    /// <summary>
    /// The playback cursor alone, for redrawing it as it moves: the 3 epx line, and the bar tint only
    /// outside the repeated bars and never in contrast themes. Drawn over the ad lib tint, the opaque
    /// cursor tint replaces it in that bar.
    /// </summary>
    public static IReadOnlyList<OverlayItem> Cursor(Box? beat, Box? bar, IReadOnlyList<Box> loop, bool highContrast)
    {
        var items = new List<OverlayItem>(2);
        if (bar is { } b && !highContrast && !loop.Any(l => Overlaps(l, b))) items.Add(new(OverlayKind.CursorTint, b));
        if (beat is { } line) items.Add(new(OverlayKind.CursorLine, line with { W = CursorWidth }));
        return items;
    }

    /// <summary>Marks of heads that share a beat on one staff are drawn once: a chord gets one "?", at its most uncertain level.</summary>
    public static IReadOnlyList<UncertainHead> OnePerBeat(IEnumerable<UncertainHead> heads) =>
        heads.GroupBy(h => (Math.Round(h.Head.X / 2), Math.Round(h.StaffTop)))
            .Select(g => g.OrderBy(h => h.Head.Y).First() with { Level = g.Max(h => h.Level) })
            .ToList();

    private static bool Overlaps(Box a, Box b) =>
        a.X < b.X + b.W && b.X < a.X + a.W && a.Y < b.Y + b.H && b.Y < a.Y + a.H;

    /// <summary>The parts of a box left and right of the boxes it overlaps on the same line.</summary>
    internal static IEnumerable<Box> Subtract(Box box, IReadOnlyList<Box> holes)
    {
        var pieces = new List<Box> { box };
        foreach (var hole in holes)
        {
            var next = new List<Box>();
            foreach (var p in pieces)
            {
                if (!Overlaps(p, hole)) { next.Add(p); continue; }
                if (hole.X > p.X) next.Add(p with { W = hole.X - p.X });
                double right = hole.X + hole.W;
                if (right < p.X + p.W) next.Add(p with { X = right, W = p.X + p.W - right });
            }
            pieces = next;
        }
        return pieces.Where(p => p.W > 0.5);
    }
}
