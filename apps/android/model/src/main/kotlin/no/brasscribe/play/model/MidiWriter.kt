package no.brasscribe.play.model

import java.io.ByteArrayOutputStream
import kotlin.math.floor
import kotlin.math.max

/**
 * Standard MIDI files of timed notes, the form the core's layer arranger reads (like the engine's
 * transcriber outputs): format 0, 120 bpm, 480 ticks per beat, so one second is 960 ticks.
 */
object MidiWriter {
    private const val TPQ = 480
    private const val TICKS_PER_SECOND = 960.0

    fun write(notes: List<TimedNote>, velocity: Int = 80): ByteArray {
        data class Ev(val tick: Long, val on: Boolean, val pitch: Int, val vel: Int)
        val evs = notes.flatMap { n ->
            val a = floor(n.onsetS * TICKS_PER_SECOND + 0.5).toLong()
            val b = max(a + 1, floor(n.offsetS * TICKS_PER_SECOND + 0.5).toLong())
            val v = (velocity * (0.5 + 0.5 * n.confidence.coerceIn(0.0, 1.0))).toInt().coerceIn(1, 127)
            listOf(Ev(a, true, n.pitch, v), Ev(b, false, n.pitch, 0))
        }.sortedWith(compareBy({ it.tick }, { if (it.on) 1 else 0 }))
        val track = ByteArrayOutputStream()
        fun vlq(v: Long) {
            var x = v
            val bytes = ArrayDeque<Int>()
            bytes.addFirst((x and 0x7f).toInt())
            x = x shr 7
            while (x > 0) { bytes.addFirst(((x and 0x7f) or 0x80).toInt()); x = x shr 7 }
            bytes.forEach { track.write(it) }
        }
        // Tempo 120 bpm = 500000 us per beat.
        vlq(0); track.write(byteArrayOf(0xff.toByte(), 0x51, 3, 0x07, 0xa1.toByte(), 0x20))
        var last = 0L
        for (e in evs) {
            vlq(e.tick - last); last = e.tick
            track.write(if (e.on) 0x90 else 0x80)
            track.write(e.pitch.coerceIn(0, 127))
            track.write(if (e.on) e.vel else 0)
        }
        vlq(0); track.write(byteArrayOf(0xff.toByte(), 0x2f, 0))
        val body = track.toByteArray()
        val out = ByteArrayOutputStream()
        out.write("MThd".toByteArray()); out.write(int32(6)); out.write(byteArrayOf(0, 0, 0, 1, (TPQ shr 8).toByte(), (TPQ and 0xff).toByte()))
        out.write("MTrk".toByteArray()); out.write(int32(body.size)); out.write(body)
        return out.toByteArray()
    }

    /** A MIDI file without notes (an empty layer). */
    val EMPTY: ByteArray by lazy { write(emptyList()) }

    private fun int32(v: Int) = byteArrayOf((v shr 24).toByte(), (v shr 16).toByte(), (v shr 8).toByte(), v.toByte())

    /** Beat table text (`time position` per line) for a steady tempo, first beat at [t0]. */
    fun steadyBeats(t0: Double, bpm: Double, untilS: Double, beatsPerBar: Int = 4): String {
        val step = 60.0 / bpm
        val sb = StringBuilder()
        var i = 0
        var t = t0
        while (t <= untilS + step) {
            sb.append("%.4f\t%d\n".format(java.util.Locale.ROOT, t, i % beatsPerBar + 1))
            i++; t = t0 + i * step
        }
        return sb.toString()
    }
}
