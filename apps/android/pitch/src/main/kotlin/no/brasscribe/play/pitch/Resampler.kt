package no.brasscribe.play.pitch

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.min
import kotlin.math.sin

/**
 * Band-limited resampling with a Hann-windowed sinc (16 zero crossings each side of the output
 * cutoff). The kernel is tabulated at [PHASES] fractional offsets, so the inner loop is multiply-adds.
 */
object Resampler {
    private const val HALF_TAPS = 16
    private const val PHASES = 512

    fun resample(input: FloatArray, fromRate: Int, toRate: Int): FloatArray {
        if (fromRate == toRate || input.isEmpty()) return input.copyOf()
        val ratio = toRate.toDouble() / fromRate
        val outLen = floor(input.size * ratio).toInt()
        val cutoff = min(1.0, ratio)
        val half = HALF_TAPS / cutoff
        val taps = 2 * kotlin.math.ceil(half).toInt() + 1
        val reach = taps / 2
        // table[p][k]: weight of input sample (base - reach + k) when the output sits p/PHASES past base.
        val table = Array(PHASES) { p ->
            val frac = p.toDouble() / PHASES
            val w = FloatArray(taps)
            var norm = 0.0
            for (k in 0 until taps) {
                val d = (k - reach) - frac
                val window = if (kotlin.math.abs(d) >= half) 0.0 else 0.5 + 0.5 * cos(PI * d / half)
                val x = d * cutoff
                val s = if (x == 0.0) 1.0 else sin(PI * x) / (PI * x)
                w[k] = (s * window).toFloat()
                norm += s * window
            }
            for (k in 0 until taps) w[k] = (w[k] / norm).toFloat()
            w
        }
        val out = FloatArray(outLen)
        val last = input.size - 1
        for (i in 0 until outLen) {
            val center = i / ratio
            val base = floor(center).toInt()
            val w = table[((center - base) * PHASES).toInt().coerceIn(0, PHASES - 1)]
            var acc = 0f
            val start = base - reach
            if (start >= 0 && start + taps - 1 <= last) {
                for (k in 0 until taps) acc += input[start + k] * w[k]
            } else {
                for (k in 0 until taps) {
                    val j = start + k
                    if (j in 0..last) acc += input[j] * w[k]
                }
            }
            out[i] = acc
        }
        return out
    }

    /** Averages interleaved channels to mono. */
    fun mixToMono(interleaved: FloatArray, channels: Int): FloatArray {
        if (channels <= 1) return interleaved
        val frames = interleaved.size / channels
        return FloatArray(frames) { f ->
            var s = 0f
            for (c in 0 until channels) s += interleaved[f * channels + c]
            s / channels
        }
    }
}
