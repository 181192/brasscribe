using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>
/// Where the tab is at a second of the recording (<see cref="TabClock"/>), on the recorded fixture
/// (apps/fixtures/bass-line: 15 bars of two-four, the beats as the computer tracked them) and on the hand-written
/// probes (a pickup, six-eight).
/// </summary>
public class TabClockTests
{
    private static (TabIndex Index, TabResult Tab) Read(string name) => (TabIndex.Parse(TabFixtures.MusicXml(name)), TabFixtures.Tab(name));

    private const int T = TabIndex.Ticks;

    [Fact]
    public void The_bars_start_on_the_beats_the_computer_tracked()
    {
        var (index, tab) = Read("bass-line");
        var clock = TabClock.Of(index, tab, null)!;
        Assert.Equal(index.Bars, clock.Bars);
        Assert.Equal(2, index.Measures[0].Beats);
        // Two quarter notes to a bar: bar n starts on the tracked beat 2n.
        for (int bar = 0; bar < clock.Bars; bar++)
        {
            int beat = 2 * bar;
            if (beat < tab.BeatTimes.Count) Assert.Equal(tab.BeatTimes[beat], clock.SecondsAt(bar), 1e-9);
            Assert.Equal(new TabPlace(bar, 0), clock.PlaceAt(clock.SecondsAt(bar)));
        }
        // The tracked beats are not evenly spaced (0.6, 1.2, 1.8, 2.4, 2.98, 3.6 …): the fifth beat is its own second, not a steady 3.0.
        Assert.Equal(2.98, clock.SecondsAt(2), 1e-9);
        Assert.Equal(2.98, clock.SecondsAt(1, 2 * T), 1e-9);
        // Half way between two beats is half way through the quarter note.
        Assert.Equal(new TabPlace(1, T + T / 2), clock.PlaceAt((2.4 + 2.98) / 2));
    }

    [Fact]
    public void Before_the_first_bar_and_after_the_last_the_tab_is_at_its_ends()
    {
        var (index, tab) = Read("bass-line");
        var clock = TabClock.Of(index, tab, null)!;
        // The recording starts 0.6 s before the first bar.
        Assert.Equal(new TabPlace(0, 0), clock.PlaceAt(0.0));
        Assert.Equal(new TabPlace(clock.Bars - 1, index.Measures[^1].Length), clock.PlaceAt(clock.End + 5));
        // Past the last tracked beat time runs on as between the last two.
        int last = tab.BeatTimes.Count - 1;
        double step = tab.BeatTimes[last] - tab.BeatTimes[last - 1];
        Assert.Equal(tab.BeatTimes[last] + step, clock.SecondsAt(0, (last + 1) * T), 1e-9);
    }

    [Fact]
    public void The_beat_of_the_bar_is_counted_by_the_time_signature()
    {
        var (index, tab) = Read("bass-line");
        var clock = TabClock.Of(index, tab, null)!;
        Assert.Equal(1, clock.BeatAt(new TabPlace(3, 0)));
        Assert.Equal(1, clock.BeatAt(new TabPlace(3, T - 1)));
        Assert.Equal(2, clock.BeatAt(new TabPlace(3, T)));
        // The end of the last bar is still its last beat.
        Assert.Equal(2, clock.BeatAt(new TabPlace(clock.Bars - 1, 2 * T)));
        var (six, sixTab) = Read("tab-probes/six-eight");
        var eighths = TabClock.Of(six, sixTab, null)!;
        Assert.Equal(6, six.Measures[0].Beats);
        Assert.Equal(3 * T, six.Measures[0].Length);
        Assert.Equal(4, eighths.BeatAt(new TabPlace(0, 3 * T / 2)));
        // A bar of six-eight is three tracked beats (quarter notes) long.
        Assert.Equal(sixTab.BeatTimes[3], eighths.SecondsAt(1), 1e-9);
    }

    [Fact]
    public void A_pickup_is_the_first_bar_and_ends_on_the_first_downbeat()
    {
        var (index, tab) = Read("tab-probes/pickup");
        Assert.True(index.Measures[0].Pickup);
        Assert.Equal(T, index.Measures[0].Length);
        Assert.Equal(T, TabClock.LeadOf(index, tab, null));
        var clock = TabClock.Of(index, tab, null)!;
        // The first full bar starts on the first downbeat; the pickup's quarter note is one beat before it.
        Assert.Equal(tab.BeatTimes[tab.FirstDownbeat], clock.SecondsAt(1), 1e-9);
        Assert.Equal(tab.BeatTimes[0] - (tab.BeatTimes[1] - tab.BeatTimes[0]), clock.SecondsAt(0), 1e-9);
        Assert.Equal(new TabPlace(0, 0), clock.PlaceAt(clock.SecondsAt(0)));
        // The pickup's one beat is the fourth of the bar it leads into.
        Assert.Equal(4, clock.BeatAt(new TabPlace(0, 0)));
        // Without the tab's data the pickup is read from the page alone.
        Assert.Equal(T, TabClock.LeadOf(index, null, null));
    }

    [Fact]
    public void A_saved_song_has_the_same_clock_from_its_saved_notes()
    {
        var (index, tab) = Read("bass-line");
        var saved = CompositionJson.Parse(TabFixtures.Text("bass-line", "composition.json"));
        var fromTab = TabClock.Of(index, tab, null)!;
        var fromSaved = TabClock.Of(index, null, saved);
        Assert.NotNull(fromSaved);
        for (int bar = 0; bar <= fromTab.Bars; bar++) Assert.Equal(fromTab.SecondsAt(bar), fromSaved.SecondsAt(bar), 1e-9);
        // Neither: there is nothing to follow the recording by.
        Assert.Null(TabClock.Of(index, null, null));
        Assert.Null(TabClock.Of(TabIndex.Parse("<not-a-score/>"), tab, null));
    }

    [Fact]
    public void A_repeat_covers_its_bars_from_line_to_line()
    {
        var (index, tab) = Read("bass-line");
        var clock = TabClock.Of(index, tab, null)!;
        var span = clock.Span(new RepeatBars(2, 3));
        Assert.Equal(clock.SecondsAt(2), span.Start, 1e-9);
        Assert.Equal(clock.SecondsAt(4), span.End, 1e-9);
        Assert.Equal(clock.End, clock.Span(new RepeatBars(0, clock.Bars - 1)).End, 1e-9);
    }

    [Fact]
    public void The_speed_moves_in_steps_of_five_and_stops_at_its_ends()
    {
        Assert.Equal(95, PracticeSpeed.Slower(100));
        Assert.Equal(105, PracticeSpeed.Faster(100));
        Assert.Equal(PracticeSpeed.Min, PracticeSpeed.Slower(PracticeSpeed.Min));
        Assert.Equal(PracticeSpeed.Max, PracticeSpeed.Faster(PracticeSpeed.Max));
    }

    /// <summary>A page of <paramref name="bars"/> full bars of <paramref name="beats"/> over <paramref name="unit"/>, as the clock needs it.</summary>
    private static List<TabMeasure> Measures(int bars, int beats = 4, int unit = 4) =>
        [.. Enumerable.Range(0, bars).Select(i => new TabMeasure((i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture), beats * T * 4 / unit, beats, T * 4 / unit))];

    [Fact]
    public void A_tempo_change_is_followed_beat_by_beat()
    {
        // Four beats at 120 a minute, then four at 60: the second bar is twice as long as the first.
        var clock = new TabClock([1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0], 0, Measures(2), 0);
        Assert.Equal(1.0, clock.SecondsAt(0), 1e-9);
        Assert.Equal(3.0, clock.SecondsAt(1), 1e-9);
        Assert.Equal(7.0, clock.End, 1e-9);
        // Half a second into each bar: the second beat of the first, half way through the first beat of the second.
        Assert.Equal(new TabPlace(0, T), clock.PlaceAt(1.5));
        Assert.Equal(new TabPlace(1, T / 2), clock.PlaceAt(3.5));
        Assert.Equal(1, clock.BeatAt(clock.PlaceAt(3.9)));
        Assert.Equal(2, clock.BeatAt(clock.PlaceAt(4.0)));
        // There and back, all the way through.
        for (int bar = 0; bar <= 1; bar++)
            for (int tick = 0; tick < 4 * T; tick += 97)
                Assert.Equal(new TabPlace(bar, tick), clock.PlaceAt(clock.SecondsAt(bar, tick)));
    }

    [Fact]
    public void A_tab_longer_than_its_tracked_beats_runs_on_at_the_last_tempo()
    {
        // Six beats were tracked, and the page has four bars of four: the bars past them are where the last tempo puts them.
        var clock = new TabClock([0.5, 1.0, 1.5, 2.0, 2.5, 3.1], 0, Measures(4), 0);
        Assert.Equal(2.5, clock.SecondsAt(1), 1e-9);
        Assert.Equal(3.1 + 3 * 0.6, clock.SecondsAt(2), 1e-9);
        Assert.Equal(3.1 + 11 * 0.6, clock.End, 1e-9);
        Assert.Equal(new TabPlace(3, 0), clock.PlaceAt(clock.SecondsAt(3)));
        // A repeat of bars past the end of a recording of 4 seconds has nothing to play, and is not turned back to.
        Assert.True(TabClock.TurnsBack(clock.Span(new RepeatBars(1, 1)).Start, 4.0));
        Assert.False(TabClock.TurnsBack(clock.Span(new RepeatBars(2, 3)).Start, 4.0));
        Assert.False(TabClock.TurnsBack(4.98, 5.0));
        // Before the recording has been read its length is not known: nothing is held back.
        Assert.True(TabClock.TurnsBack(100.0, 0.0));
    }

    [Fact]
    public void A_jump_to_a_bar_is_in_that_bar_though_players_count_in_milliseconds()
    {
        // Beats that fall between milliseconds: 0.1234567 s apart.
        var clock = new TabClock([.. Enumerable.Range(0, 40).Select(i => 0.3333333 + i * 0.1234567)], 0, Measures(9), 0);
        for (int bar = 0; bar < clock.Bars; bar++)
        {
            long ms = TabClock.MillisAt(clock.SecondsAt(bar));
            Assert.Equal(bar, clock.PlaceAt(ms / 1000.0).Bar);
            Assert.True(ms / 1000.0 - clock.SecondsAt(bar) < 0.001);
        }
        // A second that is a whole millisecond stays where it is.
        Assert.Equal(2980L, TabClock.MillisAt(2.98));
        Assert.Equal(600L, TabClock.MillisAt(0.6));
        Assert.Equal(0L, TabClock.MillisAt(-0.2));
    }

    /// <summary>Every note is, by the clock, at the second the tab's own ticks put it: the tracked beat <c>first_downbeat + start / ticks_per_beat</c>.</summary>
    private static void AssertEveryNoteIsAtItsOwnSecond(string name)
    {
        var (index, tab) = Read(name);
        var clock = TabClock.Of(index, tab, null)!;
        double ByTicks(int start)
        {
            double beat = (double)start / tab.TicksPerBeat + tab.FirstDownbeat;
            double step = tab.BeatTimes[1] - tab.BeatTimes[0];
            if (beat < 0) return tab.BeatTimes[0] + beat * step;
            int i = Math.Min((int)beat, tab.BeatTimes.Count - 2);
            return tab.BeatTimes[i] + (beat - i) * (tab.BeatTimes[i + 1] - tab.BeatTimes[i]);
        }
        int checkedNotes = 0, moved = 0;
        foreach (var piece in index.Pieces.Where(p => p.First && p.Staff == index.MarkStaff))
        {
            var note = tab.Notes[piece.Note];
            double off = Math.Abs(ByTicks(note.Start) - clock.SecondsAt(piece.Bar, piece.Onset));
            // A note moved to the grid is written a little off its tick; the others are exactly there.
            if (off > 1e-6) moved++;
            checkedNotes++;
        }
        Assert.True(checkedNotes > 0, $"{name}: no notes checked");
        Assert.True(moved <= tab.AdjustedNotes, $"{name}: notes not at their second ({moved} of {checkedNotes}), beyond the ones the page says it moved");
    }

    [Fact]
    public void Every_note_is_at_its_own_second_in_every_metre()
    {
        // Six-eight among them: one step of the tracked beats is a written quarter there too, so a bar is three steps.
        foreach (var name in new[] { "bass-line", "bass-line-marks", "tab-probes/six-eight", "tab-probes/pickup", "tab-probes/triplets",
                     "tab-probes/tie-over-the-bar", "tab-probes/chords", "tab-probes/capo" })
            AssertEveryNoteIsAtItsOwnSecond(name);
        var (six, sixTab) = Read("tab-probes/six-eight");
        var clock = TabClock.Of(six, sixTab, null)!;
        // The first note of each bar of six-eight is three quarter notes after the first of the bar before.
        var firsts = six.Pieces.Where(p => p.First && p.Onset == 0 && p.Staff == six.MarkStaff).ToList();
        Assert.True(firsts.Count >= 2);
        foreach (var p in firsts) Assert.Equal(3 * p.Bar * T / (T / sixTab.TicksPerBeat), sixTab.Notes[p.Note].Start);
        foreach (var p in firsts) Assert.Equal(sixTab.BeatTimes[3 * p.Bar + sixTab.FirstDownbeat], clock.SecondsAt(p.Bar), 1e-9);
    }
}
