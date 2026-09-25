package no.brasscribe.play.pitch

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Per-frame output of SwiftF0: one frame per 256 samples at 16 kHz (16 ms). */
class PitchTrack(val pitchHz: DoubleArray, val confidence: DoubleArray, val loudnessDb: DoubleArray) {
    val size: Int get() = pitchHz.size
    fun timeOf(frame: Int): Double = frame * SwiftF0.FRAME_PERIOD
}

/**
 * On-device SwiftF0 pitch detection with ONNX Runtime (Android: onnxruntime-android; tests: the
 * desktop build). Runs the static-shape "window" export from models/convert (485 376 samples in,
 * 1896 frames out) and reproduces upstream `SwiftF0.detect`: 1875-frame windows with 11 frames of left
 * context and 10 of lookahead, the digital-silence gate and the loudness read-out.
 */
class SwiftF0(modelBytes: ByteArray, threads: Int = 2) : AutoCloseable {
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession = env.createSession(modelBytes, OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(threads)
        addConfigEntry("session.intra_op.allow_spinning", "0")
    })
    private val windowSamples: Int = (session.inputInfo.getValue("audio").info as ai.onnxruntime.TensorInfo).shape[1].toInt()

    /** [audio] is mono float at 16 kHz. */
    fun detect(audio: FloatArray, fmin: Float = FMIN, fmax: Float = FMAX): PitchTrack {
        require(audio.isNotEmpty()) { "audio must not be empty" }
        val n = max(1, audio.size / HOP)
        val pitch = DoubleArray(n)
        val conf = DoubleArray(n)
        val loud = DoubleArray(n)
        var start = 0
        while (start < n) {
            val end = min(start + WINDOW_FRAMES, n)
            val left = max(0, start - LEFT_FRAMES)
            val from = left * HOP
            val to = if (end < n) min(audio.size, (end + LOOKAHEAD_FRAMES) * HOP) else audio.size
            val window = FloatArray(windowSamples)
            System.arraycopy(audio, from, window, 0, min(to - from, windowSamples))
            val r = run(window, to - from, fmin, fmax)
            for (f in start until end) {
                val i = f - left
                pitch[f] = r.pitchHz[i]; conf[f] = r.confidence[i]; loud[f] = r.loudnessDb[i]
            }
            start = end
        }
        return PitchTrack(pitch, conf, loud)
    }

    /** Runs one padded window; [valid] samples are real audio, the rest zero padding. */
    private fun run(window: FloatArray, valid: Int, fmin: Float, fmax: Float): PitchTrack {
        val inputs = mapOf(
            "audio" to OnnxTensor.createTensor(env, FloatBuffer.wrap(window), longArrayOf(1, window.size.toLong())),
            "fmin" to OnnxTensor.createTensor(env, fmin),
            "fmax" to OnnxTensor.createTensor(env, fmax),
        )
        try {
            session.run(inputs).use { out ->
                val p = (out.get("pitch").get() as OnnxTensor).let { t -> readDoubles(t) }
                val c = (out.get("confidence").get() as OnnxTensor).let { t -> readDoubles(t) }
                val frames = c.size
                val loud = DoubleArray(frames)
                val power = DoubleArray(frames)
                for (i in 0 until frames) {
                    var peak = 0f
                    var pw = 0.0
                    val base = i * HOP
                    for (k in 0 until HOP) {
                        val s = if (base + k < window.size) window[base + k] else 0f
                        peak = max(peak, abs(s))
                        pw += s.toDouble() * s
                    }
                    power[i] = pw
                    if (peak < SILENCE_PEAK) c[i] = 0.0
                }
                for (i in 0 until frames) {
                    val prev = if (i == 0) 0.0 else power[i - 1]
                    loud[i] = 20 * log10(max(sqrt((prev + power[i]) / 512), 1e-7))
                }
                return PitchTrack(p, c, loud)
            }
        } finally {
            inputs.values.forEach { it.close() }
        }
    }

    private fun readDoubles(t: OnnxTensor): DoubleArray {
        val shape = t.info.shape
        val count = shape.fold(1L) { a, b -> a * b }.toInt()
        return when (t.info.type) {
            ai.onnxruntime.OnnxJavaType.DOUBLE -> { val b = t.doubleBuffer; DoubleArray(count) { b.get(it) } }
            else -> { val b = t.floatBuffer; DoubleArray(count) { b.get(it).toDouble() } }
        }
    }

    override fun close() {
        session.close()
    }

    companion object {
        const val SAMPLE_RATE = 16000
        const val HOP = 256
        const val FRAME_PERIOD = HOP.toDouble() / SAMPLE_RATE
        const val FMIN = 46.875f
        const val FMAX = 2093.75f
        const val LOOKAHEAD_FRAMES = 10
        const val LEFT_FRAMES = 11
        const val WINDOW_FRAMES = 1875
        const val SILENCE_PEAK = 1e-3f
    }
}
