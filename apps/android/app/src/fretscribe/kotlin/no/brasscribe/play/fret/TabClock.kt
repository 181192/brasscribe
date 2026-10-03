package no.brasscribe.play.fret

import no.brasscribe.play.engine.Tab
import no.brasscribe.play.model.Composition
import kotlin.math.floor

/** A place in the tab: the bar (counted from 0, as written) and how far into it, in [TabIndex.TICKS] to a quarter note. */
data class TabPlace(val bar: Int, val tick: Int)

/** Bars to play again and again, counted from 0 as written, both included. */
data class RepeatBars(val first: Int, val last: Int)

/**
 * Where in the tab the recording is at any second, and the other way round. The computer tracked the
 * recording's beats (`beat_times`, with `first_downbeat` the one tick 0 falls on) and counts the notes'
 * ticks from them: one step of `beat_times` is `ticks_per_beat` ticks, which the page writes as a quarter
 * note in every time signature (a bar of six-eight is three steps; a song the computer hears in two with
 * its beats divided in three it writes in two-four). The page says how long each of its bars is. Between
 * two tracked beats time runs evenly, and before the first and after the last it runs as between the
 * nearest two, so a recording that speeds up or drags keeps its cursor on the note being played.
 */
class TabClock(
    private val beatTimes: List<Double>,
    private val firstDownbeat: Int,
    private val measures: List<TabMeasure>,
    /** From the start of the first written bar to tick 0, in [TabIndex.TICKS]: what a pickup holds, or the bars before the first downbeat. */
    private val lead: Int,
) {
    init {
        require(beatTimes.size >= 2 && measures.isNotEmpty())
    }

    /** Where each bar starts, from the start of the first, and where the last one ends. */
    private val starts = IntArray(measures.size + 1).also { s -> measures.forEachIndexed { i, m -> s[i + 1] = s[i] + m.length } }

    val bars: Int get() = measures.size

    private fun secondsOf(ticks: Int): Double {
        val beat = (ticks - lead).toDouble() / TabIndex.TICKS + firstDownbeat
        val last = beatTimes.size - 1
        return when {
            beat < 0 -> beatTimes[0] + beat * (beatTimes[1] - beatTimes[0])
            beat >= last -> beatTimes[last] + (beat - last) * (beatTimes[last] - beatTimes[last - 1])
            else -> floor(beat).toInt().let { i -> beatTimes[i] + (beat - i) * (beatTimes[i + 1] - beatTimes[i]) }
        }
    }

    /** The second of the recording at [tick] of [bar]; a bar past the last is the end of the tab. */
    fun secondsAt(bar: Int, tick: Int = 0): Double = secondsOf(starts[bar.coerceIn(0, bars)] + tick)

    /** The second the tab ends at. */
    val end: Double get() = secondsOf(starts[bars])

    /** The seconds [repeat] covers in the recording: from its first bar's line to the line after its last. */
    fun span(repeat: RepeatBars): ClosedFloatingPointRange<Double> = secondsAt(repeat.first)..secondsAt(repeat.last + 1)

    /** Where the tab is at [seconds] of the recording: before the first bar is its start, after the last is the last bar's end. */
    fun placeAt(seconds: Double): TabPlace {
        val last = beatTimes.size - 1
        val beat = when {
            seconds < beatTimes[0] -> (seconds - beatTimes[0]) / (beatTimes[1] - beatTimes[0])
            seconds >= beatTimes[last] -> last + (seconds - beatTimes[last]) / (beatTimes[last] - beatTimes[last - 1])
            else -> {
                val i = beatTimes.binarySearch(seconds).let { if (it >= 0) it else -it - 2 }.coerceIn(0, last - 1)
                i + (seconds - beatTimes[i]) / (beatTimes[i + 1] - beatTimes[i])
            }
        }
        // A thousandth of a tick over, so the second a bar starts at is in that bar.
        val ticks = floor((beat - firstDownbeat) * TabIndex.TICKS + lead + 0.001).toInt()
        if (ticks <= 0) return TabPlace(0, 0)
        if (ticks >= starts[bars]) return TabPlace(bars - 1, measures.last().length)
        val bar = starts.binarySearch(ticks).let { if (it >= 0) it else -it - 2 }.coerceIn(0, bars - 1)
        return TabPlace(bar, ticks - starts[bar])
    }

    /** The beat of its bar [place] is in, 1 the first. */
    fun beatAt(place: TabPlace): Int = measures[place.bar.coerceIn(0, bars - 1)].beatAt(place.tick)

    companion object {
        /**
         * [seconds] as the millisecond a player is sent to: the first whole one at or after it, so the place there
         * is not before the place at [seconds] (a bar's line that falls between two milliseconds is reached, not
         * stopped short of).
         */
        fun millisAt(seconds: Double): Long = Math.ceil(seconds * 1000 - 1e-6).toLong().coerceAtLeast(0)

        /**
         * The clock of a tab: from the tab's data when the computer gave it, else from the notes saved with the
         * song (the same beats). Null when neither has the recording's beats, or the page has no bars.
         */
        fun of(index: TabIndex, tab: Tab?, saved: Composition?): TabClock? {
            val beats = tab?.beatTimes ?: saved?.beatTimes ?: return null
            if (beats.size < 2 || index.measures.isEmpty() || beats.zipWithNext().any { (a, b) -> b <= a }) return null
            return TabClock(beats, tab?.firstDownbeat ?: saved?.firstDownbeat ?: 0, index.measures, leadOf(index, tab, saved))
        }

        /**
         * How far the first written bar starts before tick 0. Read off the page where the tab's data is there:
         * each note's start in the data against where its first piece is written, as most notes have it (a
         * note moved to the grid is written a little off). Else by the rule the page is written by: a pickup
         * shorter than a bar is the first measure, and a longer one starts on a bar line.
         */
        internal fun leadOf(index: TabIndex, tab: Tab?, saved: Composition?): Int {
            val starts = IntArray(index.measures.size + 1).also { s -> index.measures.forEachIndexed { i, m -> s[i + 1] = s[i] + m.length } }
            if (tab != null && tab.ticksPerBeat > 0) {
                val leads = index.pieces.filter { it.first && it.staff == index.markStaff && it.bar < index.measures.size }.mapNotNull { p ->
                    tab.notes.getOrNull(p.note)?.let { n -> starts[p.bar] + p.onset - n.start * TabIndex.TICKS / tab.ticksPerBeat }
                }
                leads.groupingBy { it }.eachCount().maxByOrNull { it.value }?.let { return it.key }
            }
            val first = index.measures.first()
            if (first.pickup) return first.length
            val earliest = saved?.takeIf { it.ticksPerBeat > 0 }?.let { it.startTick * TabIndex.TICKS / it.ticksPerBeat } ?: 0
            return if (earliest >= 0) 0 else (-earliest + first.length - 1) / first.length * first.length
        }
    }
}

/** The speeds the recording is played at, in per cent of its own: steps of five, the pitch kept. */
object PracticeSpeed {
    const val MIN = 25
    const val MAX = 150
    const val STEP = 5
    const val FULL = 100
    /** Slow enough to hear each note of a bar being checked: the bar of a doubtful note repeats at this speed (design/fretscribe/flows.md). */
    const val SLOW = 60

    fun slower(percent: Int): Int = (percent - STEP).coerceAtLeast(MIN)
    fun faster(percent: Int): Int = (percent + STEP).coerceAtMost(MAX)
}

/**
 * A stretch that starts at [start] seconds can be played again when the recording, [duration] seconds long
 * (0 while that is not known), has reached its end: it starts before that end. A tab can be longer than its
 * recording, and a repeat of bars past the recording's end has nothing to play.
 */
fun turnsBack(start: Double, duration: Double): Boolean = duration <= 0.0 || start < duration - 0.05
