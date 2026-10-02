package no.brasscribe.play.fret

import no.brasscribe.play.engine.Tab
import no.brasscribe.play.model.BrasscribeJson
import no.brasscribe.play.model.CompositionJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * Where the tab is at a second of the recording ([TabClock]), on the recorded fixture
 * (apps/fixtures/bass-line: 15 bars of two-four, the beats as the computer tracked them) and on the
 * hand-written probes (a pickup, six-eight).
 */
class TabClockTest {
    private val root: File? = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }

    private fun dir(name: String): File {
        val dir = root?.resolve("apps/fixtures/$name")
        assumeTrue("apps/fixtures/$name is not in this checkout", dir?.isDirectory == true)
        return dir!!
    }

    private fun tab(name: String): Pair<TabIndex, Tab> =
        TabIndex.parse(File(dir(name), "tab.musicxml").readText()) to BrasscribeJson.decodeFromString(Tab.serializer(), File(dir(name), "tab.json").readText())

    @Test
    fun theBarsStartOnTheBeatsTheComputerTracked() {
        val (index, tab) = tab("bass-line")
        val clock = TabClock.of(index, tab, null)!!
        assertEquals(index.bars, clock.bars)
        assertEquals(2, index.measures.first().beats)
        // Two quarter notes to a bar: bar n starts on the tracked beat 2n.
        for (bar in 0 until clock.bars) {
            val beat = 2 * bar
            if (beat < tab.beatTimes.size) assertEquals("bar $bar", tab.beatTimes[beat], clock.secondsAt(bar), 1e-9)
            assertEquals(TabPlace(bar, 0), clock.placeAt(clock.secondsAt(bar)))
        }
        // The tracked beats are not evenly spaced (0.6, 1.2, 1.8, 2.4, 2.98, 3.6 …): the fifth beat is its own second, not a steady 3.0.
        assertEquals(2.98, clock.secondsAt(2), 1e-9)
        assertEquals(2.98, clock.secondsAt(1, 2 * TabIndex.TICKS), 1e-9)
        // Half way between two beats is half way through the quarter note.
        assertEquals(TabPlace(1, TabIndex.TICKS + TabIndex.TICKS / 2), clock.placeAt((2.4 + 2.98) / 2))
    }

    @Test
    fun beforeTheFirstBarAndAfterTheLastTheTabIsAtItsEnds() {
        val (index, tab) = tab("bass-line")
        val clock = TabClock.of(index, tab, null)!!
        // The recording starts 0.6 s before the first bar.
        assertEquals(TabPlace(0, 0), clock.placeAt(0.0))
        assertEquals(TabPlace(clock.bars - 1, index.measures.last().length), clock.placeAt(clock.end + 5))
        // Past the last tracked beat time runs on as between the last two.
        val last = tab.beatTimes.size - 1
        val step = tab.beatTimes[last] - tab.beatTimes[last - 1]
        assertEquals(tab.beatTimes[last] + step, clock.secondsAt(0, (last + 1) * TabIndex.TICKS), 1e-9)
    }

    @Test
    fun theBeatOfTheBarIsCountedByTheTimeSignature() {
        val (index, tab) = tab("bass-line")
        val clock = TabClock.of(index, tab, null)!!
        assertEquals(1, clock.beatAt(TabPlace(3, 0)))
        assertEquals(1, clock.beatAt(TabPlace(3, TabIndex.TICKS - 1)))
        assertEquals(2, clock.beatAt(TabPlace(3, TabIndex.TICKS)))
        // The end of the last bar is still its last beat.
        assertEquals(2, clock.beatAt(TabPlace(clock.bars - 1, 2 * TabIndex.TICKS)))
        val (six, sixTab) = tab("tab-probes/six-eight")
        val eighths = TabClock.of(six, sixTab, null)!!
        assertEquals(6, six.measures.first().beats)
        assertEquals(3 * TabIndex.TICKS, six.measures.first().length)
        assertEquals(4, eighths.beatAt(TabPlace(0, 3 * TabIndex.TICKS / 2)))
        // A bar of six-eight is three tracked beats (quarter notes) long.
        assertEquals(sixTab.beatTimes[3], eighths.secondsAt(1), 1e-9)
    }

    @Test
    fun aPickupIsTheFirstBarAndEndsOnTheFirstDownbeat() {
        val (index, tab) = tab("tab-probes/pickup")
        assertEquals(true, index.measures.first().pickup)
        assertEquals(TabIndex.TICKS, index.measures.first().length)
        assertEquals(TabIndex.TICKS, TabClock.leadOf(index, tab, null))
        val clock = TabClock.of(index, tab, null)!!
        // The first full bar starts on the first downbeat; the pickup's quarter note is one beat before it.
        assertEquals(tab.beatTimes[tab.firstDownbeat], clock.secondsAt(1), 1e-9)
        assertEquals(tab.beatTimes[0] - (tab.beatTimes[1] - tab.beatTimes[0]), clock.secondsAt(0), 1e-9)
        assertEquals(TabPlace(0, 0), clock.placeAt(clock.secondsAt(0)))
        // The pickup's one beat is the fourth of the bar it leads into.
        assertEquals(4, clock.beatAt(TabPlace(0, 0)))
        // Without the tab's data the pickup is read from the page alone.
        assertEquals(TabIndex.TICKS, TabClock.leadOf(index, null, null))
    }

    @Test
    fun aSavedSongHasTheSameClockFromItsSavedNotes() {
        val (index, tab) = tab("bass-line")
        val saved = CompositionJson.decode(File(dir("bass-line"), "composition.json").readText())
        val fromTab = TabClock.of(index, tab, null)!!
        val fromSaved = TabClock.of(index, null, saved)
        assertNotNull(fromSaved)
        for (bar in 0..fromTab.bars) assertEquals(fromTab.secondsAt(bar), fromSaved!!.secondsAt(bar), 1e-9)
        // Neither: there is nothing to follow the recording by.
        assertNull(TabClock.of(index, null, null))
        assertNull(TabClock.of(TabIndex.parse("<not-a-score/>"), tab, null))
    }

    @Test
    fun aRepeatCoversItsBarsFromLineToLine() {
        val (index, tab) = tab("bass-line")
        val clock = TabClock.of(index, tab, null)!!
        val span = clock.span(RepeatBars(2, 3))
        assertEquals(clock.secondsAt(2), span.start, 1e-9)
        assertEquals(clock.secondsAt(4), span.endInclusive, 1e-9)
        assertEquals(clock.end, clock.span(RepeatBars(0, clock.bars - 1)).endInclusive, 1e-9)
    }

    @Test
    fun theSpeedMovesInStepsOfFiveAndStopsAtItsEnds() {
        assertEquals(95, PracticeSpeed.slower(100))
        assertEquals(105, PracticeSpeed.faster(100))
        assertEquals(PracticeSpeed.MIN, PracticeSpeed.slower(PracticeSpeed.MIN))
        assertEquals(PracticeSpeed.MAX, PracticeSpeed.faster(PracticeSpeed.MAX))
    }

    /** A page of [bars] full bars of [beats] over [unit], as the clock needs it. */
    private fun measures(bars: Int, beats: Int = 4, unit: Int = 4) = List(bars) { TabMeasure((it + 1).toString(), beats * TabIndex.TICKS * 4 / unit, beats, TabIndex.TICKS * 4 / unit) }

    @Test
    fun aTempoChangeIsFollowedBeatByBeat() {
        // Four beats at 120 a minute, then four at 60: the second bar is twice as long as the first.
        val beats = listOf(1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0)
        val clock = TabClock(beats, 0, measures(2), 0)
        assertEquals(1.0, clock.secondsAt(0), 1e-9)
        assertEquals(3.0, clock.secondsAt(1), 1e-9)
        assertEquals(7.0, clock.end, 1e-9)
        // Half a second into each bar: the second beat of the first, half way through the first beat of the second.
        assertEquals(TabPlace(0, TabIndex.TICKS), clock.placeAt(1.5))
        assertEquals(TabPlace(1, TabIndex.TICKS / 2), clock.placeAt(3.5))
        assertEquals(1, clock.beatAt(clock.placeAt(3.9)))
        assertEquals(2, clock.beatAt(clock.placeAt(4.0)))
        // There and back, all the way through.
        for (bar in 0..1) for (tick in 0 until 4 * TabIndex.TICKS step 97) assertEquals(TabPlace(bar, tick), clock.placeAt(clock.secondsAt(bar, tick)))
    }

    @Test
    fun aTabLongerThanItsTrackedBeatsRunsOnAtTheLastTempo() {
        // Six beats were tracked, and the page has four bars of four: the bars past them are where the last tempo puts them.
        val beats = listOf(0.5, 1.0, 1.5, 2.0, 2.5, 3.1)
        val clock = TabClock(beats, 0, measures(4), 0)
        assertEquals(2.5, clock.secondsAt(1), 1e-9)
        assertEquals(3.1 + 3 * 0.6, clock.secondsAt(2), 1e-9)
        assertEquals(3.1 + 11 * 0.6, clock.end, 1e-9)
        assertEquals(TabPlace(3, 0), clock.placeAt(clock.secondsAt(3)))
        // A repeat of bars past the end of a recording of 4 seconds has nothing to play, and is not turned back to.
        assertEquals(true, turnsBack(clock.span(RepeatBars(1, 1)).start, 4.0))
        assertEquals(false, turnsBack(clock.span(RepeatBars(2, 3)).start, 4.0))
        assertEquals(false, turnsBack(4.98, 5.0))
        // Before the recording has been read its length is not known: nothing is held back.
        assertEquals(true, turnsBack(100.0, 0.0))
    }

    @Test
    fun aJumpToABarIsInThatBarThoughPlayersCountInMilliseconds() {
        // Beats that fall between milliseconds: 0.1234567 s apart.
        val beats = List(40) { 0.3333333 + it * 0.1234567 }
        val clock = TabClock(beats, 0, measures(9), 0)
        for (bar in 0 until clock.bars) {
            val ms = TabClock.millisAt(clock.secondsAt(bar))
            assertEquals("bar $bar at $ms ms", TabPlace(bar, 0).bar, clock.placeAt(ms / 1000.0).bar)
            assertEquals(true, ms / 1000.0 - clock.secondsAt(bar) < 0.001)
        }
        // A second that is a whole millisecond stays where it is.
        assertEquals(2980L, TabClock.millisAt(2.98))
        assertEquals(600L, TabClock.millisAt(0.6))
        assertEquals(0L, TabClock.millisAt(-0.2))
    }

    /** Every note is, by the clock, at the second the tab's own ticks put it: the tracked beat `first_downbeat + start / ticks_per_beat`. */
    private fun assertEveryNoteIsAtItsOwnSecond(name: String) {
        val (index, tab) = tab(name)
        val clock = TabClock.of(index, tab, null)!!
        fun byTicks(start: Int): Double {
            val beat = start.toDouble() / tab.ticksPerBeat + tab.firstDownbeat
            val step = tab.beatTimes[1] - tab.beatTimes[0]
            return if (beat < 0) tab.beatTimes[0] + beat * step else { val i = beat.toInt().coerceAtMost(tab.beatTimes.size - 2); tab.beatTimes[i] + (beat - i) * (tab.beatTimes[i + 1] - tab.beatTimes[i]) }
        }
        var checked = 0
        var moved = 0
        for (piece in index.pieces.filter { it.first && it.staff == index.markStaff }) {
            val note = tab.notes[piece.note]
            val off = Math.abs(byTicks(note.start) - clock.secondsAt(piece.bar, piece.onset))
            // A note moved to the grid is written a little off its tick; the others are exactly there.
            if (off > 1e-6) moved++
            checked++
        }
        assertEquals("$name: notes checked", true, checked > 0)
        assertEquals("$name: notes not at their second ($moved of $checked), beyond the ones the page says it moved", true, moved <= tab.adjustedNotes)
    }

    @Test
    fun everyNoteIsAtItsOwnSecondInEveryMetre() {
        // Six-eight among them: one step of the tracked beats is a written quarter there too, so a bar is three steps.
        for (name in listOf("bass-line", "bass-line-marks", "tab-probes/six-eight", "tab-probes/pickup", "tab-probes/triplets", "tab-probes/tie-over-the-bar", "tab-probes/chords", "tab-probes/capo")) {
            assertEveryNoteIsAtItsOwnSecond(name)
        }
        val (six, sixTab) = tab("tab-probes/six-eight")
        val clock = TabClock.of(six, sixTab, null)!!
        // The first note of each bar of six-eight is three quarter notes after the first of the bar before.
        val firsts = six.pieces.filter { it.first && it.onset == 0 && it.staff == six.markStaff }
        assertEquals(true, firsts.size >= 2)
        for (p in firsts) assertEquals(3 * p.bar * TabIndex.TICKS / (TabIndex.TICKS / sixTab.ticksPerBeat), sixTab.notes[p.note].start)
        for (p in firsts) assertEquals(sixTab.beatTimes[3 * p.bar + sixTab.firstDownbeat], clock.secondsAt(p.bar), 1e-9)
    }
}
