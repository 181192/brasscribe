using AlphaTab.Core.EcmaScript;
using AlphaTab.Midi;
using AlphaTab.Model;
using AlphaTab.Rendering.Utils;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Playback;

public readonly record struct Box(double X, double Y, double W, double H)
{
    public static Box From(Bounds b) => new(b.X, b.Y, b.W, b.H);
}

/// <summary>
/// Where things are on the rendered score, from alphaTab's bounds lookup: the focused talking-score
/// event, the playback cursor, bar ranges for loop and ad lib bands, and uncertain noteheads.
/// </summary>
public static class ScoreGeometry
{
    private const double AlphaTabTicksPerQuarter = 960;

    public static Beat? BeatAt(Score score, int track, int barIndex, int tsTick)
    {
        if (track < 0 || track >= score.Tracks.Count) return null;
        var staff = score.Tracks[track].Staves.FirstOrDefault();
        if (staff is null || barIndex < 0 || barIndex >= staff.Bars.Count) return null;
        var voice = staff.Bars[barIndex].Voices.FirstOrDefault();
        if (voice is null || voice.Beats.Count == 0) return null;
        double tick = tsTick * AlphaTabTicksPerQuarter / MusicXmlTalkingScoreBuilder.TicksPerQuarter;
        return voice.Beats.LastOrDefault(b => b.PlaybackStart <= tick + 0.5) ?? voice.Beats[0];
    }

    /// <summary>Bounds of the beat under the talking-score cursor, or of its bar.</summary>
    public static Box? FocusBox(Score score, BoundsLookup bounds, int track, int barIndex, int tsTick)
    {
        var beat = BeatAt(score, track, barIndex, tsTick);
        if (beat is not null && bounds.FindBeat(beat) is { } bb) return Box.From(bb.VisualBounds);
        return BarBox(bounds, barIndex, track);
    }

    /// <summary>Bar area for one track (or the whole system when track is null).</summary>
    public static Box? BarBox(BoundsLookup bounds, int barIndex, int? track = null)
    {
        var mb = bounds.FindMasterBarByIndex(barIndex);
        if (mb is null) return null;
        if (track is { } t)
        {
            var bar = mb.Bars.FirstOrDefault(b => b.Bar?.Staff?.Track is { } tr && (int)tr.Index == t);
            if (bar is not null) return Box.From(bar.VisualBounds);
        }
        return Box.From(mb.VisualBounds);
    }

    /// <summary>One box per system line a bar range spans (for loop and ad lib bands).</summary>
    public static IReadOnlyList<Box> RangeBoxes(BoundsLookup bounds, int firstBar, int lastBar)
    {
        var boxes = new List<Box>();
        Box? current = null;
        double lineY = double.NaN;
        for (int i = firstBar; i <= lastBar; i++)
        {
            var mb = bounds.FindMasterBarByIndex(i);
            if (mb is null) continue;
            var r = Box.From(mb.VisualBounds);
            if (current is { } c && Math.Abs(r.Y - lineY) < 1)
            {
                current = c with { W = r.X + r.W - c.X };
            }
            else
            {
                if (current is { } done) boxes.Add(done);
                current = r;
                lineY = r.Y;
            }
        }
        if (current is { } last) boxes.Add(last);
        return boxes;
    }

    /// <summary>Playback cursor at a MIDI tick: a line at the beat and the bar it is in.</summary>
    public static (Box Beat, Box Bar)? Cursor(MidiTickLookup lookup, BoundsLookup bounds, IEnumerable<int> tracks, double tick)
    {
        var set = new Set<double>();
        foreach (var t in tracks) set.Add(t);
        var found = lookup.FindBeat(set, tick, null!);
        if (found?.Beat is not { } beat || bounds.FindBeat(beat) is not { } bb) return null;
        var bar = bounds.FindMasterBarByIndex(beat.Voice.Bar.Index);
        var beatBox = Box.From(bb.VisualBounds);
        var barBox = bar is null ? beatBox : Box.From(bar.VisualBounds);
        return (beatBox with { W = 3, Y = barBox.Y, H = barBox.H }, barBox);
    }

    /// <summary>Noteheads of uncertain notes with their level and the top of their staff.</summary>
    public static IReadOnlyList<UncertainHead> UncertainHeads(Score score, BoundsLookup bounds, TalkingScoreDocument ts, IEnumerable<int> tracks)
    {
        var result = new List<UncertainHead>();
        foreach (int t in tracks)
        {
            if (t >= ts.Parts.Count) continue;
            var part = ts.Parts[t];
            for (int b = 0; b < part.Bars.Count; b++)
            {
                foreach (var ev in part.Bars[b].Events)
                {
                    if (!ev.IsUncertain) continue;
                    var level = ev.IsVeryUncertain ? Scores.Certainty.VeryUncertain : Scores.Certainty.Uncertain;
                    var beat = BeatAt(score, t, b, ev.Tick);
                    if (beat is null || bounds.FindBeat(beat) is not { } bb) continue;
                    double staffTop = bb.BarBounds?.VisualBounds is { } bar ? bar.Y : bb.VisualBounds.Y;
                    if (bb.Notes is { Count: > 0 } notes)
                        foreach (var n in notes) result.Add(new UncertainHead(Box.From(n.NoteHeadBounds), level, staffTop));
                    else
                        result.Add(new UncertainHead(Box.From(bb.VisualBounds), level, staffTop));
                }
            }
        }
        return ScoreOverlay.OnePerBeat(result);
    }

    /// <summary>A dashed bracket over each open review group of more than one note, from its first to its last note.</summary>
    public static IReadOnlyList<Box> GroupBrackets(Score score, BoundsLookup bounds, TalkingScoreDocument ts, IEnumerable<int> tracks)
    {
        var result = new List<Box>();
        foreach (int t in tracks)
        {
            if (t >= ts.Parts.Count) continue;
            var part = ts.Parts[t];
            for (int b = 0; b < part.Bars.Count; b++)
                foreach (var lead in part.Bars[b].Events.Where(e => e.IsUncertain && e.ReviewLead && e.ReviewNotes > 1))
                {
                    var members = Review.ReviewGroups.Members(part, lead.ReviewGroup)
                        .Select(m => BeatAt(score, t, m.Bar, m.Event.Tick) is { } beat && bounds.FindBeat(beat) is { } bb ? Box.From(bb.VisualBounds) : (Box?)null)
                        .OfType<Box>().ToList();
                    if (members.Count < 2) continue;
                    // One bracket per system line the group spans.
                    foreach (var line in members.GroupBy(m => Math.Round(m.Y / 4)))
                    {
                        double x0 = line.Min(m => m.X), x1 = line.Max(m => m.X + m.W);
                        double top = line.Min(m => m.Y);
                        result.Add(new Box(x0, top - 6, x1 - x0, 6));
                    }
                }
        }
        return result;
    }

    /// <summary>
    /// The ad lib regions of the score as overlay input: the bars of each free-time region, one box per
    /// system line. The arranged score engraves the words itself.
    /// </summary>
    public static IReadOnlyList<AdlibRegion> AdlibRegions(BoundsLookup bounds, TalkingScoreDocument ts)
    {
        var regions = new List<AdlibRegion>();
        foreach (var r in ts.FreeRegions)
        {
            var boxes = RangeBoxes(bounds, r.StartBar - 1, r.EndBar - 1);
            if (boxes.Count > 0) regions.Add(new AdlibRegion(boxes));
        }
        return regions;
    }
}
