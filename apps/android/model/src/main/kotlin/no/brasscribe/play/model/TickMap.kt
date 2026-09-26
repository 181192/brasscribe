package no.brasscribe.play.model

import kotlin.math.floor

/**
 * Maps score ticks to bars and to seconds of the original recording.
 *
 * Bar 1 starts at tick 0; a pickup before it is bar 0. Seconds come from the Composition's beat
 * list, extrapolated from the first and last beat interval outside it (the recording can start before
 * tick 0: the golden Mikkel output has `first_downbeat = -4`).
 */
class TickMap(private val composition: Composition) {
    private val tpb = composition.ticksPerBeat
    private val meters = composition.meters.sortedBy { it.tick }.ifEmpty { listOf(Meter(0, 4, 4)) }

    /** Ticks per bar of the meter in force at [tick]. */
    fun ticksPerBar(tick: Int): Int {
        val m = meterAt(tick)
        return m.beats * tpb * 4 / m.beatUnit
    }

    fun meterAt(tick: Int): Meter = meters.lastOrNull { it.tick <= tick } ?: meters.first()

    fun keyAt(tick: Int): KeySig =
        composition.keys.sortedBy { it.tick }.lastOrNull { it.tick <= tick } ?: KeySig(0, 0)

    /** Bar number containing [tick]; 0 for a pickup before tick 0. */
    fun barOf(tick: Int): Int {
        if (tick < 0) return 0
        var bar = 1
        var barStart = 0
        for ((i, m) in meters.withIndex()) {
            val len = m.beats * tpb * 4 / m.beatUnit
            val segEnd = meters.getOrNull(i + 1)?.tick ?: Int.MAX_VALUE
            val segStart = maxOf(barStart, m.tick)
            if (tick < segEnd) return bar + (tick - segStart) / len
            val barsInSeg = (segEnd - segStart + len - 1) / len
            bar += barsInSeg
            barStart = segStart + barsInSeg * len
        }
        return bar
    }

    /** First tick of [bar] (bar 0 is the pickup and starts one bar before tick 0). */
    fun barStart(bar: Int): Int {
        if (bar <= 0) return -ticksPerBar(0)
        var tick = 0
        var b = 1
        while (b < bar) {
            tick += ticksPerBar(tick)
            b++
        }
        return tick
    }

    fun barEnd(bar: Int): Int = barStart(bar) + ticksPerBar(maxOf(0, barStart(bar)))

    /** Number of bars that contain notes, counting from bar 1. */
    val totalBars: Int get() = maxOf(1, barOf(maxOf(0, composition.endTick - 1)))

    /** Seconds in the recording at [tick]. */
    fun secondsAt(tick: Int): Double {
        val beats = composition.beatTimes
        val beat = tick.toDouble() / tpb + composition.firstDownbeat
        if (beats.isEmpty()) return beat * 60.0 / 120.0
        if (beats.size == 1) return beats[0] + beat * 0.5
        return when {
            beat < 0 -> beats[0] + beat * (beats[1] - beats[0])
            beat >= beats.size - 1 -> {
                val last = beats.size - 1
                beats[last] + (beat - last) * (beats[last] - beats[last - 1])
            }
            else -> {
                val i = floor(beat).toInt()
                beats[i] + (beat - i) * (beats[i + 1] - beats[i])
            }
        }
    }

    /** The recording span of [bar] in seconds: what "Listen to this bar" plays. */
    fun barSeconds(bar: Int): ClosedFloatingPointRange<Double> = secondsAt(barStart(bar))..secondsAt(barEnd(bar))

    /** Tick at [seconds] of the recording (inverse of [secondsAt]). */
    fun tickAt(seconds: Double): Int {
        val beats = composition.beatTimes
        if (beats.size < 2) return ((seconds * 2.0 - composition.firstDownbeat) * tpb).toInt()
        val beat = when {
            seconds < beats[0] -> (seconds - beats[0]) / (beats[1] - beats[0])
            seconds >= beats.last() -> {
                val last = beats.size - 1
                last + (seconds - beats[last]) / (beats[last] - beats[last - 1])
            }
            else -> {
                var i = beats.binarySearch(seconds).let { if (it >= 0) it else -it - 2 }
                i = i.coerceIn(0, beats.size - 2)
                i + (seconds - beats[i]) / (beats[i + 1] - beats[i])
            }
        }
        return floor((beat - composition.firstDownbeat) * tpb + 0.5).toInt()
    }
}
