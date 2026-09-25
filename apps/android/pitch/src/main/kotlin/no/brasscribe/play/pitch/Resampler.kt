package no.brasscribe.play.pitch

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.min
import kotlin.math.sin

/** Band-limited resampling with a Hann-windowed sinc (16 zero crossings each side). */
object Resampler {
    private const val HALF_TAPS = 16

    fun resample(input: FloatArray, fromRate: Int, toRate: Int): FloatArray {
        if (fromRate == toRate || input.isEmpty()) return input.copyOf()
        val ratio = toRate.toDouble() / fromRate
        val outLen = floor(input.size * ratio).toInt()
        val cutoff = min(1.0, ratio)
        val half = HALF_TAPS / cutoff
        val out = FloatArray(outLen)
        for (i in 0 until outLen) {
            val center = i / ratio
            val lo = maxOf(0, (center - half).toInt())
            val hi = minOf(input.size - 1, (center + half).toInt() + 1)
            var acc = 0.0
            var norm = 0.0
            for (k in lo..hi) {
                val x = (k - center) * cutoff
                val window = 0.5 + 0.5 * cos(PI * (k - center) / half)
                if (window <= 0) continue
                val s = if (x == 0.0) 1.0 else sin(PI * x) / (PI * x)
                val c = s * window
                acc += input[k] * c
                norm += c
            }
            out[i] = if (norm == 0.0) 0f else (acc / norm).toFloat()
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
