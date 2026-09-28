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

    /**
     * The original recording plays at the arrangement's estimated band loudness ([bandEstimateLufs]),
     * clamped to [RECORDING_MIN_TARGET_LUFS]..[RECORDING_MAX_TARGET_LUFS]; at this level when there is
     * no arrangement or it has no pitched note.
     */
    const val RECORDING_FALLBACK_LUFS = -16.0
    const val RECORDING_MIN_TARGET_LUFS = -20.0
    const val RECORDING_MAX_TARGET_LUFS = -10.0
    const val RECORDING_MAX_BOOST_DB = 12.0
    const val RECORDING_MAX_CUT_DB = 30.0

    /** recording.band_estimate.offset_db: fitted on the golden arrangement, checked on the full-band phrase. */
    const val BAND_ESTIMATE_OFFSET_DB = -1.2

    /**
     * L(v) of the band estimate: dynamics.sampler_velocity.alphatab_lufs, the pitched parts of the
     * full-band phrase through alphaSynth at each velocity, as (velocity, LUFS) knots.
     */
    /** dynamics.velocity: each mark's MIDI velocity (alphaTab's MidiUtils.dynamicToVelocity), by MusicXML element name. */
    val DYNAMIC_VELOCITY: Map<String, Int> = mapOf(
        "pppppp" to 3, "ppppp" to 5, "pppp" to 10, "ppp" to 15, "pp" to 31, "p" to 47, "mp" to 63, "mf" to 79,
        "f" to 95, "ff" to 111, "fff" to 127, "ffff" to 127, "fffff" to 127, "ffffff" to 127,
        "sf" to 111, "sfz" to 111, "fz" to 111, "sfp" to 111, "sfpp" to 111, "sfzp" to 111,
        "fp" to 95, "rf" to 95, "rfz" to 95, "sffz" to 95, "pf" to 87, "n" to 1,
    )

    /** dynamics.step: what an accent adds to the velocity (a marcato adds two). */
    const val DYNAMIC_STEP = 16

    val VELOCITY_LUFS: List<Pair<Int, Double>> = listOf(
        15 to -46.63, 31 to -40.33, 47 to -36.71, 63 to -28.36, 79 to -24.72, 95 to -22.25, 111 to -17.04, 127 to -15.87,
    )

    /** The metronome click's peak after the output. */
    const val METRONOME_CLICK_PEAK_DBFS = -10.0

    /** alphaTab's metronome (and count-in) volume that puts its click there through the stage, measured. */
    const val METRONOME_GAIN_DB = 0.0

    /** Gain that brings a recording measured at [lufs] (integrated, whole file) to [targetLufs]; 0 for silence. */
    fun recordingGainDb(lufs: Double, targetLufs: Double = RECORDING_FALLBACK_LUFS): Double =
        if (!lufs.isFinite()) 0.0 else (targetLufs - lufs).coerceIn(-RECORDING_MAX_CUT_DB, RECORDING_MAX_BOOST_DB)

    /** The recording's target for an arrangement's band estimate; the fallback when there is none. */
    fun recordingTargetLufs(estimate: Double?): Double =
        if (estimate == null || !estimate.isFinite()) RECORDING_FALLBACK_LUFS
        else estimate.coerceIn(RECORDING_MIN_TARGET_LUFS, RECORDING_MAX_TARGET_LUFS)

    /** L(v): linear between the [VELOCITY_LUFS] knots, 20·log10 below the lowest, the highest's above it. */
    fun velocityLufs(v: Double): Double {
        val (v0, l0) = VELOCITY_LUFS.first()
        if (v <= v0) return l0 + 20 * log10(maxOf(v, 1e-9) / v0)
        for ((a, b) in VELOCITY_LUFS.zipWithNext()) {
            if (v <= b.first) return a.second + (b.second - a.second) * (v - a.first) / (b.first - a.first)
        }
        return VELOCITY_LUFS.last().second
    }

    /**
     * Estimated integrated LUFS of the band playing an arrangement (recording.band_estimate):
     * offset + 10·log10(Σ d·10^(L(v)/10) / U) over its pitched notes, d each note's length and U the
     * time in which at least one sounds, both in quarter notes. Null without notes.
     */
    fun bandEstimateLufs(notes: List<BandNote>): Double? {
        val ns = notes.filter { it.end > it.start }
        if (ns.isEmpty()) return null
        val energy = ns.sumOf { (it.end - it.start) * 10.0.pow(velocityLufs(it.velocity) / 10) }
        var union = 0.0
        var end = Double.NEGATIVE_INFINITY
        for (n in ns.sortedWith(compareBy({ it.start }, { it.end }))) {
            if (n.end > end) {
                union += n.end - maxOf(n.start, end)
                end = n.end
            }
        }
        return BAND_ESTIMATE_OFFSET_DB + 10 * log10(energy / union)
    }

    fun factor(db: Double): Float = 10.0.pow(db / 20).toFloat()
}

/** One pitched note of an arrangement for the band estimate: start and end in quarter notes, the velocity it plays at. */
data class BandNote(val start: Double, val end: Double, val velocity: Double)

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
