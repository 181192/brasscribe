package no.brasscribe.play.model

import kotlin.math.floor
import kotlin.math.max

/**
 * Minimal quantizer for one monophonic line: snaps onsets and ends to a sixteenth grid at a given
 * tempo, with the first note's beat as the first downbeat. The engine's quantizer (metrical-level
 * selection, free-time regions) replaces this through the Rust core.
 */
object SoloQuantizer {
    private const val TPB = Composition.DEFAULT_TICKS_PER_BEAT
    private const val GRID = TPB / 4

    fun quantize(notes: List<TimedNote>, bpm: Double, title: String): Composition {
        val sorted = notes.sortedBy { it.onsetS }
        val beatS = 60.0 / bpm
        val t0 = sorted.firstOrNull()?.onsetS ?: 0.0
        fun toTick(s: Double): Int = (floor((s - t0) / beatS * TPB / GRID + 0.5) * GRID).toInt()

        val placed = mutableListOf<Note>()
        for (n in sorted) {
            val start = toTick(n.onsetS)
            val end = max(start + GRID, toTick(n.offsetS))
            val prev = placed.lastOrNull()
            if (prev != null && prev.start == start) {
                // Two onsets on one grid point: keep the more confident note.
                if (prev.confidence >= n.confidence) continue
                placed.removeAt(placed.size - 1)
            }
            val last = placed.lastOrNull()
            if (last != null && last.end > start) placed[placed.size - 1] = last.copy(dur = start - last.start)
            placed += Note(
                pitch = n.pitch, start = start, dur = end - start, confidence = n.confidence, sources = n.sources,
                onsetS = n.onsetS, offsetS = n.offsetS,
                performedDur = (floor((n.offsetS - n.onsetS) / beatS * TPB + 0.5)).toInt(),
            )
        }
        val lastEnd = placed.maxOfOrNull { it.end } ?: 0
        val beats = (lastEnd / TPB) + 8
        val composition = Composition(
            title = title,
            voices = listOf(Voice("solo", VoiceRole.MELODY, placed, instrumentHint = "solo", layer = "solo")),
            meters = listOf(Meter(0, 4, 4)),
            keys = listOf(KeySig(0, 0)),
            beatTimes = List(beats) { t0 + it * beatS },
            firstDownbeat = 0,
        )
        return composition.copy(keys = listOf(KeySig(0, KeyEstimator.estimate(placed))))
    }
}

/**
 * Tempo of a note stream from the autocorrelation of its onset train (10 ms bins), searched between
 * 60 and 160 bpm. Returns [fallback] for fewer than four notes.
 */
object TempoEstimator {
    fun estimate(onsetsS: List<Double>, fallback: Double = 100.0): Double {
        if (onsetsS.size < 4) return fallback
        val t0 = onsetsS.min()
        val bins = ((onsetsS.max() - t0) * 100).toInt() + 2
        val train = DoubleArray(bins)
        for (s in onsetsS) {
            val i = ((s - t0) * 100).toInt()
            for (d in -2..2) if (i + d in 0 until bins) train[i + d] += 1.0 - kotlin.math.abs(d) * 0.3
        }
        var bestLag = 0
        var best = 0.0
        for (lag in 38..100) { // 0.38 s (158 bpm) .. 1.0 s (60 bpm)
            var sum = 0.0
            for (i in 0 until bins - lag) sum += train[i] * train[i + lag]
            // Mild preference for tempos near 100 bpm, so a half-tempo peak does not win on ties.
            val weighted = sum * (1.0 - 0.15 * kotlin.math.abs(kotlin.math.ln(lag / 60.0)))
            if (weighted > best) { best = weighted; bestLag = lag }
        }
        return if (bestLag == 0) fallback else floor(6000.0 / bestLag + 0.5)
    }
}

/** Duration-weighted pitch-class profile correlated with the Krumhansl–Kessler major profile. */
object KeyEstimator {
    private val MAJOR = doubleArrayOf(6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)

    fun estimate(notes: List<Note>): Int {
        if (notes.isEmpty()) return 0
        val hist = DoubleArray(12)
        notes.forEach { hist[Math.floorMod(it.pitch, 12)] += max(1, it.dur).toDouble() }
        var best = 0
        var bestScore = Double.NEGATIVE_INFINITY
        for (tonic in 0 until 12) {
            val score = correlation(hist) { MAJOR[Math.floorMod(it - tonic, 12)] }
            if (score > bestScore) { bestScore = score; best = tonic }
        }
        // Tonic pitch class to fifths, folded to -5..6 (prefer flats for F, B-flat, E-flat, A-flat, D-flat).
        val fifths = Math.floorMod(best * 7, 12)
        return if (fifths > 6) fifths - 12 else fifths
    }

    private inline fun correlation(x: DoubleArray, y: (Int) -> Double): Double {
        val mx = x.average()
        val ys = DoubleArray(12) { y(it) }
        val my = ys.average()
        var num = 0.0; var dx = 0.0; var dy = 0.0
        for (i in 0 until 12) {
            num += (x[i] - mx) * (ys[i] - my); dx += (x[i] - mx) * (x[i] - mx); dy += (ys[i] - my) * (ys[i] - my)
        }
        return if (dx == 0.0 || dy == 0.0) 0.0 else num / kotlin.math.sqrt(dx * dy)
    }
}
