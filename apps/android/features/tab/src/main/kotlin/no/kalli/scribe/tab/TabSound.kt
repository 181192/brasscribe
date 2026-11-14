package no.kalli.scribe.tab

import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin

/** A note of the tab as it sounds: from [start] to [end], in seconds of the recording, at the MIDI [pitch]. */
data class SoundNote(val start: Double, val end: Double, val pitch: Int)

/** A beat of the metronome, at [at] seconds of the recording; [first] is the first beat of its bar. */
data class SoundBeat(val at: Double, val first: Boolean)

/**
 * The tab as sound, on the recording's own time: every note starts where the recording plays it, because
 * both are placed by the beats the computer tracked ([TabClock]). So the tab's sound, the metronome and
 * the recording can play together, and one cursor follows all three.
 */
class TabSoundScore(val notes: List<SoundNote>, val beats: List<SoundBeat>, val end: Double) {
    companion object {
        /** The notes the page writes on the staff its marks stand on, and a beat for every beat of every bar. */
        fun of(index: TabIndex, clock: TabClock): TabSoundScore {
            val notes = index.pieces.filter { it.staff == index.markStaff && it.bar < clock.bars }.groupBy { it.note }.values.mapNotNull { pieces ->
                val first = pieces.firstOrNull { it.first } ?: pieces.first()
                val last = pieces.maxBy { clock.secondsAt(it.bar, it.onset + it.length) }
                val start = clock.secondsAt(first.bar, first.onset)
                val end = clock.secondsAt(last.bar, last.onset + last.length)
                // A grace note is written without a length: it sounds for a moment.
                SoundNote(start, maxOf(end, start + GRACE_SECONDS), first.pitch)
            }.sortedBy { it.start }
            val beats = ArrayList<SoundBeat>()
            for (bar in 0 until clock.bars) {
                val m = clock.measure(bar)
                val (count, ticks) = counted(m)
                // A pickup holds the last beats of a bar: its beats are counted back from its end.
                val before = if (m.pickup) m.beats * m.beatTicks - m.length else 0
                for (beat in 0 until count) {
                    val tick = beat * ticks - before
                    if (tick >= 0) beats += SoundBeat(clock.secondsAt(bar, tick), beat == 0)
                }
            }
            return TabSoundScore(notes, beats, clock.end)
        }

        private const val GRACE_SECONDS = 0.08

        /**
         * How a bar of [measure] is counted: how many beats, and how long each is in [TabIndex.TICKS]. A bar written in
         * eighths in threes (six-eight, nine-eight, twelve-eight) is counted in its dotted quarters: two, three or four.
         */
        fun counted(measure: TabMeasure): Pair<Int, Int> =
            if (measure.beatTicks < TabIndex.TICKS && measure.beats >= 6 && measure.beats % 3 == 0) measure.beats / 3 to 3 * measure.beatTicks
            else measure.beats to measure.beatTicks
    }
}

/**
 * The level the tab's sound goes out at: half (6 dB down), so a full chord with a click over it, and the recording
 * beside it in the phone's mixer, have room; and above [THRESHOLD] the same bend towards [CEILING] as the band's
 * output stage has, so nothing ever clips.
 */
object TabSoundLevel {
    const val GAIN = 0.5f
    const val THRESHOLD = 0.8f
    const val CEILING = 0.98f

    fun limit(x: Float): Float {
        val a = kotlin.math.abs(x)
        if (a <= THRESHOLD) return x
        val knee = CEILING - THRESHOLD
        return Math.copySign(THRESHOLD + knee * kotlin.math.tanh((a - THRESHOLD) / knee), x)
    }

    /** The gain, then the limiter, in place over the first [count] samples. */
    fun process(samples: FloatArray, count: Int = samples.size) {
        for (i in 0 until count) samples[i] = limit(samples[i] * GAIN)
    }
}

/** The instrument's voices: what sounds a note. Stereo, interleaved. Used from one thread. */
interface TabVoices {
    fun on(pitch: Int)
    fun off(pitch: Int)

    /** Every note stops at once: the song jumped. */
    fun silence()

    /** Writes the next [frames] frames of what sounds into [out] from frame [at], over what is there. */
    fun render(out: FloatArray, at: Int, frames: Int)
}

/**
 * Plays a [TabSoundScore]: the notes through [voices] and the metronome's beats as short clicks, at any
 * speed (a slower song has the same notes, later), over a stretch again and again, and after a count-in
 * of one bar. It renders sound a block at a time and keeps the second of the recording it is at, so what
 * hears it (a phone's sound output, or a test) decides when. Used from one thread.
 */
class TabSynth(private val score: TabSoundScore, private val voices: TabVoices, private val sampleRate: Int) {
    private class Event(val at: Double, val pitch: Int, val on: Boolean)

    // A note's end comes before another note's start at the same moment: a repeated note is struck again.
    private val events = score.notes.flatMap { listOf(Event(it.start, it.pitch, true), Event(it.end, it.pitch, false)) }
        .sortedWith(compareBy<Event> { it.at }.thenBy { it.on })
    private var nextEvent = 0
    private var nextBeat = 0
    private val sounding = HashSet<Int>()

    private val high = click(1760.0)
    private val low = click(1320.0)
    /** The clicks sounding now, in a fixed number of places (nothing is made while it renders): each one's wave, and how far into it. */
    private val clickWave = arrayOfNulls<FloatArray>(CLICKS)
    private val clickFrom = IntArray(CLICKS)

    private fun click(wave: FloatArray, from: Int) {
        val free = clickWave.indexOfFirst { it == null }
        if (free >= 0) { clickWave[free] = wave; clickFrom[free] = from }
    }
    /** A count-in under way: the frames until each of its beats still to come, and until the song starts. */
    private var counting: IntArray? = null
    private var countFrame = 0

    /** The second of the recording the sound is at. */
    var position = 0.0
        private set

    /** 1 is the recording's own speed. */
    var speed = 1.0

    /** The notes sound. */
    var notes = true
        set(value) {
            if (field && !value) quiet()
            field = value
        }

    /** The metronome sounds. */
    var metronome = false

    /** The stretch to play again and again, in seconds; null plays on to the end. */
    var repeat: ClosedFloatingPointRange<Double>? = null

    /** Times the stretch has turned back to its start. */
    var turns = 0
        private set

    /** Counting in: the song has not started to move yet. */
    val countingIn: Boolean get() = counting != null

    /** The end of the tab has been reached (with nothing to repeat). */
    val ended: Boolean get() = repeat == null && position >= score.end

    fun seek(seconds: Double) {
        quiet()
        counting = null
        position = seconds.coerceAtLeast(0.0)
        nextEvent = events.indexOfFirst { it.at >= position }.let { if (it < 0) events.size else it }
        nextBeat = score.beats.indexOfFirst { it.at >= position }.let { if (it < 0) score.beats.size else it }
    }

    /** [beats] clicks, [beatSeconds] apart at the speed it plays at, before the song moves on from where it is. */
    fun countIn(beats: Int, beatSeconds: Double) {
        val step = (beatSeconds / speed * sampleRate).toInt().coerceAtLeast(1)
        counting = IntArray(beats.coerceAtLeast(1) + 1) { it * step }
        countFrame = 0
    }

    private fun quiet() {
        voices.silence()
        sounding.clear()
    }

    /** Writes [frames] frames into [out] (stereo, interleaved) and moves on by them. False once the tab's end is reached. */
    fun render(out: FloatArray, frames: Int): Boolean {
        var at = 0
        while (at < frames) {
            val block = minOf(BLOCK, frames - at)
            val count = counting
            if (count != null) {
                voices.render(out, at, block)
                for (i in 0 until count.size - 1) if (count[i] >= countFrame && count[i] < countFrame + block) click(if (i == 0) high else low, countFrame - count[i])
                countFrame += block
                if (countFrame >= count.last()) counting = null
            } else if (ended) {
                // What still sounds is let go, and rings out.
                sounding.forEach(voices::off)
                sounding.clear()
                voices.render(out, at, block)
            } else {
                val again = repeat
                val until = position + block.toDouble() / sampleRate * speed
                // Nothing past the end of the stretch is struck: the first note of the bar after it is not part of it.
                val within = if (again != null) minOf(until, again.endInclusive) else until
                while (nextEvent < events.size && events[nextEvent].at < within) {
                    val e = events[nextEvent++]
                    if (!notes) continue
                    if (e.on) { voices.on(e.pitch); sounding += e.pitch } else if (sounding.remove(e.pitch)) voices.off(e.pitch)
                }
                while (nextBeat < score.beats.size && score.beats[nextBeat].at < within) {
                    val b = score.beats[nextBeat++]
                    if (metronome) click(if (b.first) high else low, 0)
                }
                voices.render(out, at, block)
                position = until
                if (again != null && position >= again.endInclusive) {
                    seek(again.start)
                    turns++
                }
            }
            mix(out, at, block)
            at += block
        }
        return !ended
    }

    /** Adds the clicks that sound to the block, and moves them on. */
    private fun mix(out: FloatArray, at: Int, frames: Int) {
        for (slot in 0 until CLICKS) {
            val wave = clickWave[slot] ?: continue
            val from = clickFrom[slot]
            var i = maxOf(0, -from)
            while (i < frames && from + i < wave.size) {
                out[2 * (at + i)] += wave[from + i]
                out[2 * (at + i) + 1] += wave[from + i]
                i++
            }
            if (from + frames >= wave.size) clickWave[slot] = null else clickFrom[slot] = from + frames
        }
    }

    /** A short click: a tone that dies away in a few hundredths of a second. */
    private fun click(hz: Double): FloatArray = FloatArray((CLICK_SECONDS * sampleRate).toInt()) { i ->
        val t = i.toDouble() / sampleRate
        (CLICK_LEVEL * sin(2 * PI * hz * t) * exp(-t / (CLICK_SECONDS / 5))).toFloat()
    }

    companion object {
        /** Frames rendered at a time: a note starts within a thousandth or two of a second of its place. */
        const val BLOCK = 64
        private const val CLICK_SECONDS = 0.05
        private const val CLICK_LEVEL = 0.5
        /** Clicks that can sound at once: more than ever do (a click is over long before the next beat). */
        private const val CLICKS = 8
    }
}
