package no.brasscribe.play.pitch

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.ln1p
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Port of `beat_this.preprocessing.LogMelSpect`: torchaudio `MelSpectrogram` (22.05 kHz, n_fft 1024,
 * hop 441, periodic Hann window, centred with reflect padding, magnitude (power 1) divided by
 * sqrt(n_fft) (`normalized="frame_length"`), 128 slaney mels from 30 Hz to 11 kHz without filter normalisation), then
 * `log1p(1000 x)`. Output is frames x 128, frame-major.
 */
class LogMel(
    private val sampleRate: Int = SAMPLE_RATE,
    private val nFft: Int = 1024,
    private val hop: Int = 441,
    fMin: Double = 30.0,
    fMax: Double = 11000.0,
    val nMels: Int = 128,
    private val logMultiplier: Double = 1000.0,
) {
    private val nFreqs = nFft / 2 + 1
    private val window = DoubleArray(nFft) { 0.5 - 0.5 * cos(2 * PI * it / nFft) }
    private val frameNorm = sqrt(nFft.toDouble())
    /** Mel filterbank, [nFreqs][nMels], as torchaudio.functional.melscale_fbanks(norm=None, "slaney"). */
    private val fb: Array<DoubleArray> = melFilterbank(fMin, fMax)
    private val fft = RealFft(nFft)

    fun frames(samples: Int): Int = 1 + samples / hop

    /** Log-mel spectrogram of mono audio at [sampleRate]: returns [frames][nMels]. */
    fun compute(x: FloatArray): Array<FloatArray> {
        require(x.size > nFft / 2) { "audio too short for reflect padding" }
        val pad = nFft / 2
        val n = x.size
        val count = frames(n)
        val frame = DoubleArray(nFft)
        val mag = DoubleArray(nFreqs)
        val re = DoubleArray(nFreqs)
        val im = DoubleArray(nFreqs)
        return Array(count) { f ->
            val start = f * hop - pad
            for (k in 0 until nFft) {
                var i = start + k
                // torch reflect padding (edge sample not repeated).
                if (i < 0) i = -i
                if (i >= n) i = 2 * (n - 1) - i
                frame[k] = x[i].toDouble() * window[k]
            }
            fft.forward(frame, re, im)
            for (b in 0 until nFreqs) mag[b] = sqrt(re[b] * re[b] + im[b] * im[b]) / frameNorm
            FloatArray(nMels) { m ->
                var s = 0.0
                for (b in 0 until nFreqs) {
                    val w = fb[b][m]
                    if (w != 0.0) s += mag[b] * w
                }
                ln1p(logMultiplier * s).toFloat()
            }
        }
    }

    private fun melFilterbank(fMin: Double, fMax: Double): Array<DoubleArray> {
        val allFreqs = DoubleArray(nFreqs) { it * (sampleRate / 2.0) / (nFreqs - 1) }
        val mMin = hzToMel(fMin)
        val mMax = hzToMel(fMax)
        val fPts = DoubleArray(nMels + 2) { melToHz(mMin + (mMax - mMin) * it / (nMels + 1)) }
        val fDiff = DoubleArray(nMels + 1) { fPts[it + 1] - fPts[it] }
        return Array(nFreqs) { b ->
            DoubleArray(nMels) { m ->
                val down = -(fPts[m] - allFreqs[b]) / fDiff[m]
                val up = (fPts[m + 2] - allFreqs[b]) / fDiff[m + 1]
                max(0.0, min(down, up))
            }
        }
    }

    companion object {
        const val SAMPLE_RATE = 22050
        private const val F_SP = 200.0 / 3
        private const val MIN_LOG_HZ = 1000.0
        private const val MIN_LOG_MEL = MIN_LOG_HZ / F_SP
        private val LOGSTEP = ln(6.4) / 27.0

        fun hzToMel(f: Double): Double = if (f < MIN_LOG_HZ) f / F_SP else MIN_LOG_MEL + ln(f / MIN_LOG_HZ) / LOGSTEP
        fun melToHz(m: Double): Double = if (m < MIN_LOG_MEL) F_SP * m else MIN_LOG_HZ * kotlin.math.exp(LOGSTEP * (m - MIN_LOG_MEL))
    }
}

/** Radix-2 FFT of a real frame of power-of-two length; writes bins 0..n/2. */
internal class RealFft(private val n: Int) {
    private val bits = Integer.numberOfTrailingZeros(n)
    private val cosT = DoubleArray(n / 2) { cos(2 * PI * it / n) }
    private val sinT = DoubleArray(n / 2) { -sin(2 * PI * it / n) }
    private val rev = IntArray(n) { Integer.reverse(it) ushr (32 - bits) }
    private val bufRe = DoubleArray(n)
    private val bufIm = DoubleArray(n)

    init {
        require(n > 1 && n and (n - 1) == 0) { "FFT size must be a power of two" }
    }

    fun forward(x: DoubleArray, outRe: DoubleArray, outIm: DoubleArray) {
        for (i in 0 until n) { bufRe[rev[i]] = x[i]; bufIm[rev[i]] = 0.0 }
        var size = 2
        while (size <= n) {
            val half = size / 2
            val step = n / size
            var start = 0
            while (start < n) {
                var k = 0
                for (j in start until start + half) {
                    val wr = cosT[k]
                    val wi = sinT[k]
                    val l = j + half
                    val tr = wr * bufRe[l] - wi * bufIm[l]
                    val ti = wr * bufIm[l] + wi * bufRe[l]
                    bufRe[l] = bufRe[j] - tr
                    bufIm[l] = bufIm[j] - ti
                    bufRe[j] += tr
                    bufIm[j] += ti
                    k += step
                }
                start += size
            }
            size *= 2
        }
        for (b in 0..n / 2) { outRe[b] = bufRe[b]; outIm[b] = bufIm[b] }
    }
}
