package no.brasscribe.play.pitch

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/** A note found by Basic Pitch: seconds, MIDI pitch and the mean frame activation (0..1). */
data class BasicPitchNote(val start: Double, val end: Double, val pitch: Int, val amplitude: Double)

/** Frame-level model output, frames x 88 piano keys (MIDI 21..108). */
class BasicPitchOutput(val frames: Int, val note: FloatArray, val onset: FloatArray) {
    fun note(t: Int, f: Int) = note[t * BasicPitch.N_KEYS + f]
    fun onset(t: Int, f: Int) = onset[t * BasicPitch.N_KEYS + f]
}

/**
 * On-device Basic Pitch (Spotify, Apache-2.0) with ONNX Runtime: the batch-1 export from
 * convert/basic-pitch (`nmp-b1.onnx`, input 43 844 samples at 22 050 Hz, outputs 172 frames).
 * Reproduces `basic_pitch.inference.predict` with its defaults: windows overlapping by 30 frames,
 * unwrapped by dropping 15 frames at each side, then `output_to_notes_polyphonic` (onset 0.5,
 * frame 0.3, minimum note 127.70 ms, inferred onsets, melodia trick) and `model_frames_to_time`.
 * Pitch bends are not computed.
 */
class BasicPitch(modelBytes: ByteArray, threads: Int = 2) : AutoCloseable {
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession = env.createSession(modelBytes, OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(threads)
        addConfigEntry("session.intra_op.allow_spinning", "0")
    })

    /** [audio] is mono float at [sampleRate]; it is resampled to 22 050 Hz first. */
    fun transcribe(
        audio: FloatArray,
        sampleRate: Int,
        onsetThreshold: Double = 0.5,
        frameThreshold: Double = 0.3,
        minimumNoteLengthMs: Double = 127.70,
    ): List<BasicPitchNote> {
        val x = if (sampleRate == SAMPLE_RATE) audio else Resampler.resample(audio, sampleRate, SAMPLE_RATE)
        val out = infer(x)
        val minNoteLen = (minimumNoteLengthMs / 1000 * (SAMPLE_RATE.toDouble() / FFT_HOP)).let { floor(it + 0.5).toInt() }
        return notes(out, onsetThreshold, frameThreshold, minNoteLen)
    }

    /** Model activations for 22 050 Hz mono audio (`run_inference` + `unwrap_output`). */
    fun infer(audio22k: FloatArray): BasicPitchOutput {
        val originalLength = audio22k.size
        val padded = FloatArray(OVERLAP_LEN / 2 + originalLength)
        System.arraycopy(audio22k, 0, padded, OVERLAP_LEN / 2, originalLength)
        val keep = ANNOT_N_FRAMES - 2 * (N_OVERLAP_FRAMES / 2)
        val windows = (padded.size + HOP_SIZE - 1) / HOP_SIZE
        val note = FloatArray(windows * keep * N_KEYS)
        val onset = FloatArray(windows * keep * N_KEYS)
        val window = FloatArray(AUDIO_N_SAMPLES)
        for (w in 0 until windows) {
            val start = w * HOP_SIZE
            window.fill(0f)
            System.arraycopy(padded, start, window, 0, min(AUDIO_N_SAMPLES, padded.size - start))
            OnnxTensor.createTensor(env, FloatBuffer.wrap(window), longArrayOf(1, AUDIO_N_SAMPLES.toLong(), 1)).use { input ->
                session.run(mapOf(INPUT to input), setOf(NOTE, ONSET)).use { r ->
                    copyTrimmed((r.get(NOTE).get() as OnnxTensor).floatBuffer, note, w * keep)
                    copyTrimmed((r.get(ONSET).get() as OnnxTensor).floatBuffer, onset, w * keep)
                }
            }
        }
        val frames = min(windows * keep, floor(originalLength * (ANNOTATIONS_FPS.toDouble() / SAMPLE_RATE)).toInt())
        return BasicPitchOutput(frames, note.copyOf(frames * N_KEYS), onset.copyOf(frames * N_KEYS))
    }

    private fun copyTrimmed(src: FloatBuffer, dst: FloatArray, frameOffset: Int) {
        val skip = N_OVERLAP_FRAMES / 2
        val keep = ANNOT_N_FRAMES - 2 * skip
        src.position(skip * N_KEYS)
        src.get(dst, frameOffset * N_KEYS, keep * N_KEYS)
    }

    override fun close() {
        session.close()
    }

    companion object {
        const val SAMPLE_RATE = 22050
        const val FFT_HOP = 256
        const val ANNOTATIONS_FPS = SAMPLE_RATE / FFT_HOP // 86, integer as upstream
        const val ANNOT_N_FRAMES = ANNOTATIONS_FPS * 2 // 172
        const val AUDIO_N_SAMPLES = SAMPLE_RATE * 2 - FFT_HOP // 43 844
        const val N_OVERLAP_FRAMES = 30
        const val OVERLAP_LEN = N_OVERLAP_FRAMES * FFT_HOP
        const val HOP_SIZE = AUDIO_N_SAMPLES - OVERLAP_LEN
        const val N_KEYS = 88
        const val MIDI_OFFSET = 21
        private const val MAX_FREQ_IDX = 87
        private const val ENERGY_TOL = 11
        private const val INPUT = "serving_default_input_2:0"
        private const val NOTE = "StatefulPartitionedCall:1"
        private const val ONSET = "StatefulPartitionedCall:2"

        /** `model_frames_to_time`: frame times with upstream's per-window offset correction. */
        fun frameTime(i: Int): Double {
            val original = i.toDouble() * FFT_HOP / SAMPLE_RATE
            val windowOffset = (FFT_HOP.toDouble() / SAMPLE_RATE) * (ANNOT_N_FRAMES - AUDIO_N_SAMPLES.toDouble() / FFT_HOP) + 0.0018
            return original - windowOffset * floor(i.toDouble() / ANNOT_N_FRAMES)
        }

        /** `output_to_notes_polyphonic` (no frequency limits) followed by frame-to-time conversion. */
        fun notes(out: BasicPitchOutput, onsetThresh: Double, frameThresh: Double, minNoteLen: Int): List<BasicPitchNote> {
            val n = out.frames
            if (n == 0) return emptyList()
            val k = N_KEYS
            val onsets = inferredOnsets(out)
            // Strict local maxima in time (scipy.signal.argrelmax, axis 0, edges excluded) at or above the threshold.
            val starts = ArrayList<Long>()
            for (t in 1 until n - 1) for (f in 0 until k) {
                val v = onsets[t * k + f]
                if (v > onsets[(t - 1) * k + f] && v > onsets[(t + 1) * k + f] && v >= onsetThresh) starts += t.toLong() * k + f
            }
            val remaining = DoubleArray(n * k) { out.note[it].toDouble() }
            val events = ArrayList<IntArray>()
            // Onsets go backwards in time (np.where order reversed).
            for (s in starts.indices.reversed()) {
                val start = (starts[s] / k).toInt()
                val f = (starts[s] % k).toInt()
                if (start >= n - 1) continue
                var i = start + 1
                var below = 0
                while (i < n - 1 && below < ENERGY_TOL) {
                    if (remaining[i * k + f] < frameThresh) below++ else below = 0
                    i++
                }
                i -= below
                if (i - start <= minNoteLen) continue
                for (t in start until i) {
                    remaining[t * k + f] = 0.0
                    if (f < MAX_FREQ_IDX) remaining[t * k + f + 1] = 0.0
                    if (f > 0) remaining[t * k + f - 1] = 0.0
                }
                events += intArrayOf(start, i, f)
            }
            // Melodia trick: grow notes from the strongest remaining frames.
            while (true) {
                var best = 0
                for (j in 1 until remaining.size) if (remaining[j] > remaining[best]) best = j
                if (remaining[best] <= frameThresh) break
                val mid = best / k
                val f = best % k
                remaining[best] = 0.0
                var i = mid + 1
                var below = 0
                while (i < n - 1 && below < ENERGY_TOL) {
                    if (remaining[i * k + f] < frameThresh) below++ else below = 0
                    clear(remaining, i, f)
                    i++
                }
                val end = i - 1 - below
                i = mid - 1
                below = 0
                while (i > 0 && below < ENERGY_TOL) {
                    if (remaining[i * k + f] < frameThresh) below++ else below = 0
                    clear(remaining, i, f)
                    i--
                }
                val start = i + 1 + below
                if (end - start <= minNoteLen) continue
                events += intArrayOf(start, end, f)
            }
            return events.map { (s, e, f) ->
                var sum = 0.0
                for (t in s until e) sum += out.note(t, f)
                BasicPitchNote(frameTime(s), frameTime(e), f + MIDI_OFFSET, if (e > s) sum / (e - s) else 0.0)
            }
        }

        private fun clear(r: DoubleArray, t: Int, f: Int) {
            val k = N_KEYS
            r[t * k + f] = 0.0
            if (f < MAX_FREQ_IDX) r[t * k + f + 1] = 0.0
            if (f > 0) r[t * k + f - 1] = 0.0
        }

        /** `get_infered_onsets` with n_diff = 2: onsets maxed with rescaled positive frame differences. */
        private fun inferredOnsets(out: BasicPitchOutput): DoubleArray {
            val n = out.frames
            val k = N_KEYS
            val diff = DoubleArray(n * k)
            var maxDiff = 0.0
            var maxOnset = Double.NEGATIVE_INFINITY
            for (t in 0 until n) for (f in 0 until k) {
                val x = out.note(t, f).toDouble()
                val d1 = x - (if (t >= 1) out.note(t - 1, f).toDouble() else 0.0)
                val d2 = x - (if (t >= 2) out.note(t - 2, f).toDouble() else 0.0)
                val d = if (t < 2) 0.0 else max(0.0, min(d1, d2))
                diff[t * k + f] = d
                if (d > maxDiff) maxDiff = d
                maxOnset = max(maxOnset, out.onset(t, f).toDouble())
            }
            // Same operation order as upstream: max(onsets) * frame_diff / max(frame_diff).
            return DoubleArray(n * k) { max(out.onset[it].toDouble(), if (maxDiff > 0) maxOnset * diff[it] / maxDiff else 0.0) }
        }
    }
}
