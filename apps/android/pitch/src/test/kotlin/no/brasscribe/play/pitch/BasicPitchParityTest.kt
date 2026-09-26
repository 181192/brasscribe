package no.brasscribe.play.pitch

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import javax.sound.sampled.AudioSystem
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.sin

/**
 * Basic Pitch on ONNX Runtime against upstream `basic_pitch.inference.predict` (same batch-1 ONNX,
 * ONNX Runtime CPU in Python). References: src/test/python/make_basic_pitch_reference.py.
 */
class BasicPitchParityTest {
    @Serializable
    data class RefNote(val start: Double, val end: Double, val pitch: Int, val amplitude: Double)

    @Serializable
    data class Reference(val samples: Int = 0, val seconds: Int = 0, val notes: List<RefNote>)

    private val json = Json { ignoreUnknownKeys = true }
    private val model = File(System.getProperty("brasscribe.models") ?: "missing", "basic-pitch/nmp-b1.onnx")
    private val urmp = File(System.getProperty("brasscribe.data") ?: "missing", "urmp/Dataset/10_March_tpt_sax/AuSep_1_tpt_10_March.wav")

    private fun reference(name: String): Reference =
        json.decodeFromString(Reference.serializer(), File(System.getProperty("brasscribe.pitchFixtures"), name).readText())

    /** The SyntheticMelody formula at any sample rate (the Python reference uses 22 050 Hz). */
    private fun melody(sr: Int): FloatArray {
        val notes = List(3) {
            listOf(70 to 0.8, 72 to 0.4, 74 to 0.4, 75 to 1.2, 0 to 0.3, 77 to 0.6, 79 to 0.6, 81 to 0.3, 82 to 1.6, 0 to 0.5,
                65 to 0.9, 67 to 0.45, 69 to 0.45, 70 to 2.0, 0 to 0.4)
        }.flatten()
        val out = ArrayList<Float>()
        for ((pitch, dur) in notes) {
            val n = Math.rint(dur * sr).toInt() // Python round(): half to even
            if (pitch == 0) { repeat(n) { out += 0f }; continue }
            val f0 = 440.0 * Math.pow(2.0, (pitch - 69) / 12.0)
            for (i in 0 until n) {
                val t = i.toDouble() / sr
                var tone = 0.0
                for (h in 1..6) tone += (1.0 / h) * sin(2 * PI * f0 * h * t)
                val env = min(1.0, min(t / 0.02, (dur - t) / 0.02))
                out += (0.25 * tone * env).toFloat()
            }
        }
        return out.toFloatArray()
    }

    /** Note F1 with mir_eval's rule used by convert/common/parity.py: same pitch, onset within 50 ms, one-to-one. */
    private fun f1(got: List<BasicPitchNote>, want: List<RefNote>, tol: Double = 0.05): Double {
        val used = BooleanArray(want.size)
        var hits = 0
        for (g in got.sortedBy { it.start }) {
            val j = want.indices.filter { !used[it] && want[it].pitch == g.pitch && abs(want[it].start - g.start) <= tol }
                .minByOrNull { abs(want[it].start - g.start) } ?: continue
            used[j] = true
            hits++
        }
        if (got.isEmpty() && want.isEmpty()) return 1.0
        return 2.0 * hits / (got.size + want.size)
    }

    private fun sorted(notes: List<BasicPitchNote>) = notes.sortedWith(compareBy({ it.start }, { it.pitch }))

    @Test
    fun syntheticMelodyMatchesUpstreamNoteForNote() {
        assumeTrue("Basic Pitch ONNX export not present at $model", model.isFile)
        val ref = reference("basic-pitch-synthetic.json")
        val audio = melody(BasicPitch.SAMPLE_RATE)
        assertEquals(ref.samples, audio.size)
        val t0 = System.nanoTime()
        val got = sorted(BasicPitch(model.readBytes()).use { it.transcribe(audio, BasicPitch.SAMPLE_RATE) })
        val ms = (System.nanoTime() - t0) / 1_000_000
        println("Basic Pitch synthetic: ${got.size} notes (reference ${ref.notes.size}), F1 %.4f, %d ms on this JVM for %.1f s"
            .format(f1(got, ref.notes), ms, audio.size / 22050.0))
        assertEquals(ref.notes.size, got.size)
        for ((g, w) in got.zip(ref.notes)) {
            assertEquals(w.pitch, g.pitch)
            assertEquals(w.start, g.start, 1e-4)
            assertEquals(w.end, g.end, 1e-4)
            assertEquals(w.amplitude, g.amplitude, 1e-3)
        }
    }

    @Test
    fun urmpTrumpetMatchesUpstream() {
        assumeTrue("Basic Pitch ONNX export not present at $model", model.isFile)
        assumeTrue("URMP clip not present at $urmp", urmp.isFile)
        val ref = reference("basic-pitch-urmp-march.json")
        val (audio, sr) = readWav(urmp, ref.seconds.toDouble())
        val t0 = System.nanoTime()
        val got = BasicPitch(model.readBytes()).use { it.transcribe(audio, sr) }
        val ms = (System.nanoTime() - t0) / 1_000_000
        val f = f1(got, ref.notes)
        println("Basic Pitch URMP March trumpet 30 s: ${got.size} notes (reference ${ref.notes.size}), F1 %.4f, %d ms on this JVM (incl. 48->22.05 kHz resampling)"
            .format(f, ms))
        assertTrue("note F1 $f", f >= 0.98)
    }

    private fun readWav(file: File, seconds: Double): Pair<FloatArray, Int> {
        AudioSystem.getAudioInputStream(file).use { stream ->
            val fmt = stream.format
            val bytesPer = fmt.sampleSizeInBits / 8
            require((bytesPer == 2 || bytesPer == 3) && !fmt.isBigEndian) { "expected 16/24-bit little-endian PCM, got $fmt" }
            val ch = fmt.channels
            val frames = min(stream.frameLength, (seconds * fmt.sampleRate).toLong()).toInt()
            val bytes = stream.readNBytes(frames * fmt.frameSize)
            fun sample(i: Int): Float {
                val o = i * bytesPer
                return if (bytesPer == 2) ((bytes[o].toInt() and 0xff) or (bytes[o + 1].toInt() shl 8)) / 32768f
                else ((bytes[o].toInt() and 0xff) or ((bytes[o + 1].toInt() and 0xff) shl 8) or (bytes[o + 2].toInt() shl 16)) / 8388608f
            }
            val out = FloatArray(frames) { f ->
                var s = 0f
                for (c in 0 until ch) s += sample(f * ch + c)
                s / ch
            }
            return out to fmt.sampleRate.toInt()
        }
    }
}
