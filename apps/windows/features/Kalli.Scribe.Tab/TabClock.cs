using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;

namespace Kalli.Scribe.Tab;

/// <summary>A place in the tab: the bar (counted from 0, as written) and how far into it, in <see cref="TabIndex.Ticks"/> to a quarter note.</summary>
public readonly record struct TabPlace(int Bar, int Tick);

/// <summary>Bars to play again and again, counted from 0 as written, both included.</summary>
public sealed record RepeatBars(int First, int Last);

/// <summary>A stretch of the recording, in seconds, both ends included.</summary>
public readonly record struct SecondsRange(double Start, double End);

/// <summary>
/// Where in the tab the recording is at any second, and the other way round. The computer tracked the recording's
/// beats (<c>beat_times</c>, with <c>first_downbeat</c> the one tick 0 falls on) and counts the notes' ticks from
/// them: one step of <c>beat_times</c> is <c>ticks_per_beat</c> ticks, which the page writes as a quarter note in
/// every time signature (a bar of six-eight is three steps; a song the computer hears in two with its beats divided
/// in three it writes in two-four). The page says how long each of its bars is. Between two tracked beats time runs
/// evenly, and before the first and after the last it runs as between the nearest two, so a recording that speeds
/// up or drags keeps its cursor on the note being played.
/// </summary>
public sealed class TabClock
{
    private readonly IReadOnlyList<double> _beatTimes;
    private readonly int _firstDownbeat;
    private readonly IReadOnlyList<TabMeasure> _measures;
    private readonly int _lead;
    /// <summary>Where each bar starts, from the start of the first, and where the last one ends.</summary>
    private readonly int[] _starts;

    /// <param name="lead">From the start of the first written bar to tick 0, in <see cref="TabIndex.Ticks"/>: what a pickup holds, or the bars before the first downbeat.</param>
    public TabClock(IReadOnlyList<double> beatTimes, int firstDownbeat, IReadOnlyList<TabMeasure> measures, int lead)
    {
        if (beatTimes.Count < 2 || measures.Count == 0) throw new ArgumentException("a clock needs two beats and a bar");
        _beatTimes = beatTimes;
        _firstDownbeat = firstDownbeat;
        _measures = measures;
        _lead = lead;
        _starts = StartsOf(measures);
    }

    private static int[] StartsOf(IReadOnlyList<TabMeasure> measures)
    {
        var s = new int[measures.Count + 1];
        for (int i = 0; i < measures.Count; i++) s[i + 1] = s[i] + measures[i].Length;
        return s;
    }

    public int Bars => _measures.Count;

    private double SecondsOf(int ticks)
    {
        double beat = (double)(ticks - _lead) / TabIndex.Ticks + _firstDownbeat;
        int last = _beatTimes.Count - 1;
        if (beat < 0) return _beatTimes[0] + beat * (_beatTimes[1] - _beatTimes[0]);
        if (beat >= last) return _beatTimes[last] + (beat - last) * (_beatTimes[last] - _beatTimes[last - 1]);
        int i = (int)Math.Floor(beat);
        return _beatTimes[i] + (beat - i) * (_beatTimes[i + 1] - _beatTimes[i]);
    }

    /// <summary>The second of the recording at <paramref name="tick"/> of <paramref name="bar"/>; a bar past the last is the end of the tab.</summary>
    public double SecondsAt(int bar, int tick = 0) => SecondsOf(_starts[Math.Clamp(bar, 0, Bars)] + tick);

    /// <summary>The second the tab ends at.</summary>
    public double End => SecondsOf(_starts[Bars]);

    /// <summary>The seconds <paramref name="repeat"/> covers in the recording: from its first bar's line to the line after its last.</summary>
    public SecondsRange Span(RepeatBars repeat) => new(SecondsAt(repeat.First), SecondsAt(repeat.Last + 1));

    /// <summary>Where the tab is at <paramref name="seconds"/> of the recording: before the first bar is its start, after the last is the last bar's end.</summary>
    public TabPlace PlaceAt(double seconds)
    {
        int last = _beatTimes.Count - 1;
        double beat;
        if (seconds < _beatTimes[0]) beat = (seconds - _beatTimes[0]) / (_beatTimes[1] - _beatTimes[0]);
        else if (seconds >= _beatTimes[last]) beat = last + (seconds - _beatTimes[last]) / (_beatTimes[last] - _beatTimes[last - 1]);
        else
        {
            int i = Math.Clamp(Before(_beatTimes, seconds), 0, last - 1);
            beat = i + (seconds - _beatTimes[i]) / (_beatTimes[i + 1] - _beatTimes[i]);
        }
        // A thousandth of a tick over, so the second a bar starts at is in that bar.
        int ticks = (int)Math.Floor((beat - _firstDownbeat) * TabIndex.Ticks + _lead + 0.001);
        if (ticks <= 0) return new TabPlace(0, 0);
        if (ticks >= _starts[Bars]) return new TabPlace(Bars - 1, _measures[^1].Length);
        int bar = Math.Clamp(Before(_starts, ticks), 0, Bars - 1);
        return new TabPlace(bar, ticks - _starts[bar]);
    }

    /// <summary>The index of the last value at or before <paramref name="value"/> in a sorted list (-1 when none is).</summary>
    private static int Before<T>(IReadOnlyList<T> sorted, T value) where T : IComparable<T>
    {
        int lo = 0, hi = sorted.Count - 1;
        while (lo <= hi)
        {
            int mid = (lo + hi) >>> 1;
            int c = sorted[mid].CompareTo(value);
            if (c == 0) return mid;
            if (c < 0) lo = mid + 1; else hi = mid - 1;
        }
        return lo - 1;
    }

    /// <summary>The beat of its bar <paramref name="place"/> is in, 1 the first.</summary>
    public int BeatAt(TabPlace place) => _measures[Math.Clamp(place.Bar, 0, Bars - 1)].BeatAt(place.Tick);

    /// <summary>
    /// <paramref name="seconds"/> as the millisecond a player is sent to: the first whole one at or after it, so the
    /// place there is not before the place at <paramref name="seconds"/> (a bar's line that falls between two
    /// milliseconds is reached, not stopped short of).
    /// </summary>
    public static long MillisAt(double seconds) => Math.Max((long)Math.Ceiling(seconds * 1000 - 1e-6), 0);

    /// <summary>
    /// A stretch that starts at <paramref name="start"/> seconds can be played again when the recording,
    /// <paramref name="duration"/> seconds long (0 while that is not known), has reached its end: it starts before that
    /// end. A tab can be longer than its recording, and a repeat of bars past the recording's end has nothing to play.
    /// </summary>
    public static bool TurnsBack(double start, double duration) => duration <= 0.0 || start < duration - 0.05;

    /// <summary>
    /// The clock of a tab: from the tab's data when the computer gave it, else from the notes saved with the song (the
    /// same beats). Null when neither has the recording's beats, or the page has no bars.
    /// </summary>
    public static TabClock? Of(TabIndex index, TabResult? tab, Composition? saved)
    {
        IReadOnlyList<double>? beats = tab?.BeatTimes ?? saved?.BeatTimes;
        if (beats is null || beats.Count < 2 || index.Measures.Count == 0) return null;
        for (int i = 1; i < beats.Count; i++) if (beats[i] <= beats[i - 1]) return null;
        return new TabClock(beats, tab?.FirstDownbeat ?? saved?.FirstDownbeat ?? 0, index.Measures, LeadOf(index, tab, saved));
    }

    /// <summary>
    /// How far the first written bar starts before tick 0. Read off the page where the tab's data is there: each note's
    /// start in the data against where its first piece is written, as most notes have it (a note moved to the grid is
    /// written a little off). Else by the rule the page is written by: a pickup shorter than a bar is the first
    /// measure, and a longer one starts on a bar line.
    /// </summary>
    public static int LeadOf(TabIndex index, TabResult? tab, Composition? saved)
    {
        var starts = StartsOf(index.Measures);
        if (tab is { TicksPerBeat: > 0 })
        {
            var leads = index.Pieces.Where(p => p.First && p.Staff == index.MarkStaff && p.Bar < index.Measures.Count && p.Note >= 0 && p.Note < tab.Notes.Count)
                .Select(p => starts[p.Bar] + p.Onset - tab.Notes[p.Note].Start * TabIndex.Ticks / tab.TicksPerBeat)
                .GroupBy(l => l).MaxBy(g => g.Count());
            if (leads is not null) return leads.Key;
        }
        var first = index.Measures[0];
        if (first.Pickup) return first.Length;
        int earliest = saved is { TicksPerBeat: > 0 } s ? StartTick(s) * TabIndex.Ticks / s.TicksPerBeat : 0;
        return earliest >= 0 ? 0 : (-earliest + first.Length - 1) / first.Length * first.Length;
    }

    /// <summary>The first note's start, or 0 when none starts before tick 0.</summary>
    private static int StartTick(Composition c) => Math.Min(0, c.Voices.SelectMany(v => v.Notes).Select(n => n.Start).DefaultIfEmpty(0).Min());
}

/// <summary>The speeds the recording is played at, in per cent of its own: steps of five, the pitch kept.</summary>
public static class PracticeSpeed
{
    public const int Min = 25;
    public const int Max = 150;
    public const int Step = 5;
    public const int Full = 100;
    /// <summary>Slow enough to hear each note of a bar being checked: the bar of a doubtful note repeats at this speed.</summary>
    public const int Slow = 60;

    public static int Slower(int percent) => Math.Max(percent - Step, Min);
    public static int Faster(int percent) => Math.Min(percent + Step, Max);
}
