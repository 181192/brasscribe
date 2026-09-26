package no.brasscribe.play.pitch

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Beat and downbeat times in seconds; every downbeat is also a beat. */
class Beats(val beats: DoubleArray, val downbeats: DoubleArray) {
    /** Beat number per beat (1 = downbeat), as `beat_this.utils.infer_beat_numbers`. */
    fun numbers(): IntArray {
        val firstTwo = downbeats.take(2).map { d -> beats.indexOfFirst { it >= d }.let { if (it < 0) beats.size else it } }
        var counter = 1
        if (firstTwo.size >= 2) {
            val inFirstMeasure = firstTwo[1] - firstTwo[0]
            val pickup = firstTwo[0]
            if (pickup < inFirstMeasure) counter = inFirstMeasure - pickup
        }
        val out = IntArray(beats.size)
        var di = 0
        for ((i, b) in beats.withIndex()) {
            if (di < downbeats.size && b == downbeats[di]) { counter = 1; di++ } else counter++
            out[i] = counter
        }
        return out
    }

    /** The `.beats` text the engine and the Rust core read: "time<TAB>number" per line (`save_beat_tsv`). */
    fun toBeatsText(): String {
        val n = numbers()
        return buildString { beats.forEachIndexed { i, t -> append(t.toString()).append('\t').append(n[i]).append('\n') } }
    }
}

/**
 * On-device Beat This! (small0) on ONNX Runtime: the dynamic-length export from convert/beat-this
 * ("spect" [1, T, 128] -> "beat", "downbeat" logits [1, T]) with upstream's host code ported:
 * the log-mel frontend ([LogMel]), 1500-frame chunks with a 6-frame border ("keep_first"
 * aggregation), and the minimal postprocessor (±70 ms max-pool peaks above logit 0, adjacent
 * peaks merged, downbeats moved to the nearest beat). 50 frames per second.
 */
class BeatThis(modelBytes: ByteArray, threads: Int = 2) : AutoCloseable {
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession = env.createSession(modelBytes, OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(threads)
        addConfigEntry("session.intra_op.allow_spinning", "0")
    })
    private val logMel = LogMel()

    /** Mono audio at any rate (resampled to 22.05 kHz here). */
    fun track(mono: FloatArray, sampleRate: Int): Beats {
        val x = if (sampleRate == LogMel.SAMPLE_RATE) mono else Resampler.resample(mono, sampleRate, LogMel.SAMPLE_RATE)
        return fromSpect(logMel.compute(x))
    }

    fun fromSpect(spect: Array<FloatArray>): Beats {
        val (beat, down) = logits(spect)
        return postprocess(beat, down)
    }

    /** Framewise beat and downbeat logits for the whole piece (upstream `split_predict_aggregate`). */
    fun logits(spect: Array<FloatArray>): Pair<FloatArray, FloatArray> {
        val len = spect.size
        val starts = chunkStarts(len)
        val beat = FloatArray(len) { -1000f }
        val down = FloatArray(len) { -1000f }
        // keep_first: later chunks are written first, so earlier chunks overwrite them.
        for (start in starts.reversed()) {
            val from = max(start, 0)
            val to = min(start + CHUNK, len)
            val left = max(0, -start)
            val right = max(0, min(BORDER, start + CHUNK - len))
            val frames = left + (to - from) + right
            val buf = FloatArray(frames * N_MELS)
            for (i in from until to) System.arraycopy(spect[i], 0, buf, (left + i - from) * N_MELS, N_MELS)
            val (b, d) = run(buf, frames)
            // Drop the border on both sides and place the rest at start + BORDER.
            for (k in BORDER until frames - BORDER) {
                val t = start + k
                if (t in 0 until len && t < start + CHUNK - BORDER) { beat[t] = b[k]; down[t] = d[k] }
            }
        }
        return beat to down
    }

    private fun run(buf: FloatArray, frames: Int): Pair<FloatArray, FloatArray> {
        OnnxTensor.createTensor(env, FloatBuffer.wrap(buf), longArrayOf(1, frames.toLong(), N_MELS.toLong())).use { input ->
            session.run(mapOf("spect" to input)).use { out ->
                val b = (out.get("beat").get() as OnnxTensor).floatBuffer
                val d = (out.get("downbeat").get() as OnnxTensor).floatBuffer
                return FloatArray(frames) { b.get(it) } to FloatArray(frames) { d.get(it) }
            }
        }
    }

    override fun close() = session.close()

    companion object {
        const val CHUNK = 1500
        const val BORDER = 6
        const val N_MELS = 128
        const val FPS = 50.0

        /** Upstream `split_piece(..., avoid_short_end=True)` chunk starts (the first is negative). */
        fun chunkStarts(len: Int): IntArray {
            val step = CHUNK - 2 * BORDER
            val starts = generateSequence(-BORDER) { it + step }.takeWhile { it < len - BORDER }.toMutableList()
            if (starts.isEmpty()) starts += -BORDER
            if (len > step) starts[starts.size - 1] = len - (CHUNK - BORDER)
            return starts.toIntArray()
        }

        /** Upstream `Postprocessor(type="minimal")` for one piece. */
        fun postprocess(beat: FloatArray, down: FloatArray): Beats {
            val beatTimes = peaks(beat).map { it / FPS }.toDoubleArray()
            val downTimes = peaks(down).map { it / FPS }.map { d ->
                if (beatTimes.isEmpty()) d else {
                    var best = 0
                    for (i in beatTimes.indices) if (abs(beatTimes[i] - d) < abs(beatTimes[best] - d)) best = i
                    beatTimes[best]
                }
            }.distinct().sorted().toDoubleArray()
            return Beats(beatTimes, downTimes)
        }

        /** Frames that equal the max within ±3 frames and exceed logit 0, adjacent ones merged to their mean. */
        internal fun peaks(logits: FloatArray): List<Double> {
            val n = logits.size
            val frames = (0 until n).filter { t ->
                val v = logits[t]
                var m = Float.NEGATIVE_INFINITY
                for (k in max(0, t - 3)..min(n - 1, t + 3)) m = max(m, logits[k])
                v == m && v > 0f
            }
            val out = ArrayList<Double>()
            if (frames.isEmpty()) return out
            var p = frames[0].toDouble()
            var c = 1
            for (i in 1 until frames.size) {
                val p2 = frames[i]
                if (p2 - p <= 1) { c++; p += (p2 - p) / c } else { out += p; p = p2.toDouble(); c = 1 }
            }
            out += p
            return out
        }
    }
}
