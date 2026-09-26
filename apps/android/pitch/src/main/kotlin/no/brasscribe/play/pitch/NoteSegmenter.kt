package no.brasscribe.play.pitch

import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.log2
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/** A note found in a pitch track: seconds and a fitted pitch in Hz. */
data class PitchNote(val start: Double, val end: Double, val pitchHz: Double, val confidence: Double) {
    val midi: Int get() = floor(69 + 12 * log2(pitchHz / 440.0) + 0.5).toInt()
}

/**
 * Port of `swift_f0.segment_notes`: splits frames into notes and gaps with the smallest total cost
 * J = Σ notes [β + Σ frames (offpitch + unvoiced + quiet)], solved exactly by dynamic programming.
 * β = pitchHoldMs / 16 ms. See https://swift-f0.github.io/how/#how-notes.
 */
object NoteSegmenter {
    fun segment(track: PitchTrack, pitchHoldMs: Double = 80.0): List<PitchNote> {
        val n = track.size
        if (n == 0) return emptyList()
        val pitch = track.pitchHz
        val valid = BooleanArray(n) { pitch[it].isFinite() && pitch[it] > 0 }
        if (valid.none { it }) return emptyList()
        val m = DoubleArray(n) { if (valid[it]) 69.0 + 12.0 * log2(pitch[it] / 440.0) else 0.0 }
        val w = DoubleArray(n) { if (valid[it]) track.confidence[it] else 0.0 }
        val level = track.loudnessDb
        // Symmetric padding by 4, then the max over 5 frames to the left and to the right of each frame.
        val padded = DoubleArray(n + 8) { i ->
            val j = i - 4
            when {
                j < 0 -> level[min(n - 1, -j - 1)]
                j >= n -> level[max(0, 2 * n - j - 1)]
                else -> level[j]
            }
        }
        val q = DoubleArray(n) { t ->
            var left = Double.NEGATIVE_INFINITY
            var right = Double.NEGATIVE_INFINITY
            for (j in 0 until 5) {
                left = max(left, padded[t + j]); right = max(right, padded[4 + t + j])
            }
            val cc = w[t].coerceIn(0.01, 0.99)
            -ln(cc / (1.0 - cc)) + max(0.0, min(left, right) - level[t] - 10 * log10(2.0))
        }
        val mu = (0 until n).filter { valid[it] }.map { floor(m[it] * 100 + 0.5) / 100 }.distinct().sorted().toDoubleArray()
        val beta = pitchHoldMs / 1000 / SwiftF0.FRAME_PERIOD

        val vn = DoubleArray(mu.size) { Double.POSITIVE_INFINITY }
        val noteStart = IntArray(mu.size)
        val back = IntArray(n + 1)
        val kind = IntArray(n + 1) { -1 }
        var best = 0.0
        for (t in 0 until n) {
            val start = best + beta
            var j = 0
            var jBest = 0
            var vBest = Double.POSITIVE_INFINITY
            while (j < mu.size) {
                if (start < vn[j]) { noteStart[j] = t; vn[j] = start }
                vn[j] += min(abs(mu[j] - m[t]), 2.0) * w[t] + q[t]
                if (vn[j] < vBest) { vBest = vn[j]; jBest = j }
                j++
            }
            if (vBest < best) {
                best = vBest; back[t + 1] = noteStart[jBest]; kind[t + 1] = jBest
            } else back[t + 1] = t
        }
        val notes = ArrayList<PitchNote>()
        var b = n
        while (b > 0) {
            val a = back[b]
            if (kind[b] >= 0) {
                val hz = 440.0 * 2.0.pow((mu[kind[b]] - 69.0) / 12.0)
                var c = 0.0
                for (f in a until b) c += track.confidence[f]
                notes += PitchNote(track.timeOf(a), track.timeOf(b - 1) + SwiftF0.FRAME_PERIOD, hz, c / (b - a))
            }
            b = a
        }
        notes.reverse()
        return notes
    }
}
