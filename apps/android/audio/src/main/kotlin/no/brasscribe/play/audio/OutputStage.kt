package no.brasscribe.play.audio

import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.pow
import kotlin.math.tanh
import kotlin.math.withSign

/**
 * The loudness every Play app plays at: sounds/playback-levels.json, which the tests check these
 * against (docs/research/12-band-sound.md §11).
 */
object PlaybackLevels {
    /** The full-band test phrase lands here (integrated LUFS) through the band stage. */
    const val BAND_PHRASE_LUFS = -12.0

    /** Make-up gain before the limiter on alphaTab's synth output (unity master volume), measured. */
    const val ALPHATAB_GAIN_DB = 4.0

    /**
     * Make-up gain on the sfizz tier's mix. Its parts are balanced to the band SoundFont's
     * (single_voice_gain_db), so it takes alphaTab's gain.
     */
    const val SFIZZ_GAIN_DB = 4.0

    /** The original recording plays at this integrated loudness: a whole arrangement from the band. */
    const val RECORDING_TARGET_LUFS = -16.0
    const val RECORDING_MAX_BOOST_DB = 12.0
    const val RECORDING_MAX_CUT_DB = 30.0

    /** The metronome click's peak after the output. */
    const val METRONOME_CLICK_PEAK_DBFS = -10.0

    /** alphaTab's metronome (and count-in) volume that puts its click there through the stage, measured. */
    const val METRONOME_GAIN_DB = 0.0

    /** Gain that brings a recording measured at [lufs] (integrated, whole file) to the target; 0 for silence. */
    fun recordingGainDb(lufs: Double): Double =
        if (!lufs.isFinite()) 0.0 else (RECORDING_TARGET_LUFS - lufs).coerceIn(-RECORDING_MAX_CUT_DB, RECORDING_MAX_BOOST_DB)

    fun factor(db: Double): Float = 10.0.pow(db / 20).toFloat()
}

/**
 * The output stage: make-up gain, then a memoryless soft limiter, the same curve on every Play app.
 * Linear up to [THRESHOLD], tanh towards [CEILING] above it, so nothing ever clips. It has no attack
 * or release: it cannot pump when the music stops or fades, and below the threshold every part keeps
 * its level, so mute and solo keep the balance. The sfizz tier runs the same curve in C++
 * (cpp/output_stage.h).
 */
object OutputStage {
    /** Where the limiter starts to bend (−1.9 dBFS). */
    const val THRESHOLD = 0.8f

    /** What the limiter never reaches (−0.18 dBFS). */
    const val CEILING = 0.98f

    /** The limiter curve for one sample (gain already applied). */
    fun limit(x: Float): Float {
        val a = abs(x)
        if (a <= THRESHOLD) return x
        val knee = CEILING - THRESHOLD
        return (THRESHOLD + knee * tanh((a - THRESHOLD) / knee)).withSign(x)
    }

    /** Gain, then the limiter, in place over [from] until [to]. */
    fun process(samples: FloatArray, gain: Float, from: Int = 0, to: Int = samples.size) {
        for (i in from until to) samples[i] = limit(samples[i] * gain)
    }
}

/**
 * Integrated loudness (ITU-R BS.1770 / EBU R128) of audio fed in chunks: K-weighting, 400 ms blocks
 * with 75 % overlap, the −70 LUFS absolute gate and the −10 LU relative gate. The filters are
 * pyloudnorm's, so the numbers match sounds/output-stage-vectors.json and the other Play apps.
 */
class LoudnessMeter(sampleRate: Double, val channels: Int) {
    private class Biquad(val b0: Double, val b1: Double, val b2: Double, val a1: Double, val a2: Double) {
        var z1 = 0.0
        var z2 = 0.0
        fun run(x: Double): Double {
            val y = b0 * x + z1
            z1 = b1 * x - a1 * y + z2
            z2 = b2 * x - a2 * y
            return y
        }
    }

    private val shelf = Array(channels.coerceAtLeast(1)) {
        val g = 4.0; val q = 1 / kotlin.math.sqrt(2.0); val fc = 1500.0
        val a = 10.0.pow(g / 40); val w = 2 * Math.PI * fc / sampleRate; val al = kotlin.math.sin(w) / (2 * q)
        val c = kotlin.math.cos(w); val s = kotlin.math.sqrt(a)
        val a0 = (a + 1) - (a - 1) * c + 2 * s * al
        Biquad(a * ((a + 1) + (a - 1) * c + 2 * s * al) / a0, -2 * a * ((a - 1) + (a + 1) * c) / a0,
            a * ((a + 1) + (a - 1) * c - 2 * s * al) / a0, 2 * ((a - 1) - (a + 1) * c) / a0, ((a + 1) - (a - 1) * c - 2 * s * al) / a0)
    }
    private val highpass = Array(channels.coerceAtLeast(1)) {
        val q = 0.5; val fc = 38.0
        val w = 2 * Math.PI * fc / sampleRate; val al = kotlin.math.sin(w) / (2 * q); val c = kotlin.math.cos(w); val a0 = 1 + al
        Biquad((1 + c) / 2 / a0, -(1 + c) / a0, (1 + c) / 2 / a0, -2 * c / a0, (1 - al) / a0)
    }
    private val subBlock = Math.round(sampleRate * 0.1).toInt().coerceAtLeast(1)
    private val subEnergy = ArrayList<Double>()
    private var acc = 0.0
    private var accCount = 0

    /** Feeds [frames] interleaved frames from [offset] (in samples). */
    fun process(interleaved: FloatArray, offset: Int = 0, frames: Int = (interleaved.size - offset) / channels) {
        var i = 0
        while (i < frames) {
            val n = minOf(frames - i, subBlock - accCount)
            for (c in 0 until channels) {
                val f1 = shelf[c]; val f2 = highpass[c]
                var s = 0.0
                for (k in i until i + n) { val y = f2.run(f1.run(interleaved[offset + k * channels + c].toDouble())); s += y * y }
                acc += s
            }
            accCount += n
            i += n
            if (accCount == subBlock) { subEnergy += acc; acc = 0.0; accCount = 0 }
        }
    }

    /** Integrated loudness in LUFS; −∞ for silence or less than 400 ms of audio. */
    val integratedLufs: Double
        get() {
            if (subEnergy.size < 4) return Double.NEGATIVE_INFINITY
            val n = subBlock * 4.0
            val blocks = (0..subEnergy.size - 4).map { j -> (subEnergy[j] + subEnergy[j + 1] + subEnergy[j + 2] + subEnergy[j + 3]) / n }
            fun lufs(z: Double) = -0.691 + 10 * log10(z)
            val abs = blocks.filter { it > 0 && lufs(it) > -70 }
            if (abs.isEmpty()) return Double.NEGATIVE_INFINITY
            val rel = lufs(abs.average()) - 10
            return lufs(abs.filter { lufs(it) > rel }.average())
        }

    companion object {
        /** Integrated loudness of mono audio as it plays from two speakers (dual mono, +3 dB). */
        fun dualMono(audio: PcmAudio): Double {
            val m = LoudnessMeter(audio.sampleRate.toDouble(), 1)
            m.process(audio.samples)
            return m.integratedLufs + 10 * log10(2.0)
        }
    }
}

/**
 * This audio level-matched: [gainDb] (from the whole recording's loudness, never a slice's), then
 * the limiter, so a boost cannot clip.
 */
fun PcmAudio.leveled(gainDb: Double): PcmAudio {
    if (gainDb == 0.0) return this
    val out = samples.copyOf()
    OutputStage.process(out, PlaybackLevels.factor(gainDb))
    return PcmAudio(out, sampleRate)
}
