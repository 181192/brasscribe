package no.brasscribe.play.pitch

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.sin
import no.brasscribe.play.test.Slow
import org.junit.experimental.categories.Category

/** The signals of src/test/python/make_beat_this_reference.py, computed the same way (double, then float). */
object BeatSignals {
    private const val SR = 22050

    fun sweep(seconds: Double = 2.0): FloatArray {
        val n = (seconds * SR).toInt()
        val f0 = 100.0
        val k = (4000.0 - f0) / seconds
        val click = (0.25 * SR).toInt()
        return FloatArray(n) { i ->
            val t = i.toDouble() / SR
            var x = 0.3 * sin(2 * PI * (f0 * t + 0.5 * k * t * t)) + 0.2 * sin(2 * PI * 440.0 * t)
            if (i % click < 20) x += 0.5
            x.toFloat()
        }
    }

    fun clicks(seconds: Double = 40.0, bpm: Double = 120.0): FloatArray {
        val n = (seconds * SR).toInt()
        val x = DoubleArray(n)
        val period = 60.0 / bpm
        val length = (0.03 * SR).toInt()
        var beat = 0
        while (true) {
            val start = Math.round((0.5 + beat * period) * SR).toInt()
            if (start + length > n) break
            val accent = beat % 4 == 0
            val f = if (accent) 1500.0 else 1000.0
            val a = if (accent) 0.9 else 0.5
            for (j in 0 until length) {
                val t = j.toDouble() / SR
                x[start + j] += a * exp(-t / 0.008) * sin(2 * PI * f * t)
            }
            beat++
        }
        return FloatArray(n) { x[it].toFloat() }
    }
}

/** Mono samples of a PCM or float WAV (channels averaged), as torchaudio/soundfile read them. */
internal fun readWav(file: File, fromS: Double, toS: Double): Pair<FloatArray, Int> {
    val bytes = file.readBytes()
    val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    var pos = 12
    var channels = 1; var rate = 44100; var bits = 16; var format = 1
    while (pos + 8 <= bytes.size) {
        val id = String(bytes, pos, 4)
        val size = b.getInt(pos + 4)
        val body = pos + 8
        if (id == "fmt ") {
            format = b.getShort(body).toInt(); channels = b.getShort(body + 2).toInt()
            rate = b.getInt(body + 4); bits = b.getShort(body + 14).toInt()
            if (format == 0xFFFE) format = b.getShort(body + 24).toInt()
        } else if (id == "data") {
            val frameBytes = channels * bits / 8
            val total = minOf(size, bytes.size - body) / frameBytes
            val a = (fromS * rate).toInt().coerceIn(0, total)
            val z = (toS * rate).toInt().coerceIn(a, total)
            return FloatArray(z - a) { f ->
                var s = 0.0
                for (c in 0 until channels) {
                    val at = body + (a + f) * frameBytes + c * bits / 8
                    s += when {
                        format == 3 -> b.getFloat(at).toDouble()
                        bits == 16 -> b.getShort(at) / 32768.0
                        bits == 24 -> ((bytes[at].toInt() and 0xff) or ((bytes[at + 1].toInt() and 0xff) shl 8) or (bytes[at + 2].toInt() shl 16)) / 8388608.0
                        else -> b.getInt(at) / 2147483648.0
                    }
                }
                (s / channels).toFloat()
            } to rate
        }
        pos = body + size + (size and 1)
    }
    error("no data chunk in $file")
}

/** Event F1 at a ±50 ms window with one-to-one matching (as mir_eval.util.match_events on sorted events). */
internal fun eventF1(ref: DoubleArray, est: DoubleArray, window: Double = 0.05): Double {
    if (ref.isEmpty() && est.isEmpty()) return 1.0
    if (ref.isEmpty() || est.isEmpty()) return 0.0
    var i = 0; var j = 0; var hits = 0
    while (i < ref.size && j < est.size) {
        val d = est[j] - ref[i]
        when {
            abs(d) <= window + 1e-9 -> { hits++; i++; j++ }
            d < 0 -> j++
            else -> i++
        }
    }
    return 2.0 * hits / (ref.size + est.size)
}

@Category(Slow::class)
class BeatThisParityTest {
    @Serializable data class LogMelRef(val frames: Int, val mels: Int, val logmel: List<List<Double>>)
    @Serializable data class BeatsRef(val beats: List<Double>, val downbeats: List<Double>)
    @Serializable data class Excerpt(val file: String, val start_s: Double, val end_s: Double, val beats: List<Double>, val downbeats: List<Double>)
    @Serializable data class ExcerptsRef(val excerpts: List<Excerpt>)

    private val json = Json { ignoreUnknownKeys = true }
    private val fixtures = File(System.getProperty("brasscribe.pitchFixtures"))
    private val model = File(System.getProperty("brasscribe.models") ?: "missing", "beat-this/beat-this-small0.onnx")
    private val data = File(System.getProperty("brasscribe.data") ?: "missing")

    @Test
    fun logMelMatchesTorchaudio() {
        val ref = json.decodeFromString(LogMelRef.serializer(), File(fixtures, "beatthis-logmel-reference.json").readText())
        val got = LogMel().compute(BeatSignals.sweep())
        assertEquals(ref.frames, got.size)
        var maxDiff = 0.0
        var maxVal = 0.0
        for (f in got.indices) for (m in 0 until ref.mels) {
            maxDiff = maxOf(maxDiff, abs(got[f][m] - ref.logmel[f][m]))
            maxVal = maxOf(maxVal, abs(ref.logmel[f][m]))
        }
        println("Beat This log-mel: %d x %d, max abs diff %.2e (values up to %.2f)".format(got.size, ref.mels, maxDiff, maxVal))
        // torch runs the STFT in float32; this port runs it in double.
        assertTrue("max abs diff $maxDiff", maxDiff < 1e-3)
    }

    @Test
    fun chunkStartsMatchSplitPiece() {
        assertEquals(listOf(-6), BeatThis.chunkStarts(1000).toList())
        assertEquals(listOf(-6, 1482, 1506), BeatThis.chunkStarts(3000).toList())
        assertEquals(listOf(-6, 506), BeatThis.chunkStarts(2000).toList())
    }

    @Test
    fun beatNumbersAndText() {
        val b = Beats(doubleArrayOf(0.5, 1.0, 1.5, 2.0, 2.5, 3.0), doubleArrayOf(1.0, 3.0))
        assertEquals(listOf(4, 1, 2, 3, 4, 1), b.numbers().toList())
        assertEquals("0.5\t4\n1.0\t1\n", b.toBeatsText().lines().take(2).joinToString("\n") + "\n")
    }

    private fun check(name: String, ref: BeatsRef, got: Beats, ms: Long) {
        val fb = eventF1(ref.beats.toDoubleArray(), got.beats)
        val fd = eventF1(ref.downbeats.toDoubleArray(), got.downbeats)
        println("Beat This %s: beat F1 %.4f (%d ref, %d got), downbeat F1 %.4f (%d ref, %d got), %d ms on this JVM"
            .format(name, fb, ref.beats.size, got.beats.size, fd, ref.downbeats.size, got.downbeats.size, ms))
        assertTrue("$name beat F1 $fb", fb >= 0.98)
        assertTrue("$name downbeat F1 $fd", fd >= 0.98)
    }

    @Test
    fun clickTrackMatchesUpstream() {
        assumeTrue("Beat This small0 ONNX not present at $model", model.isFile)
        val ref = json.decodeFromString(BeatsRef.serializer(), File(fixtures, "beatthis-clicks-reference.json").readText())
        BeatThis(model.readBytes()).use { bt ->
            val t0 = System.nanoTime()
            val got = bt.track(BeatSignals.clicks(), 22050)
            check("clicks 40 s", ref, got, (System.nanoTime() - t0) / 1_000_000)
        }
    }

    @Test
    fun audioExcerptsMatchUpstream() {
        assumeTrue("Beat This small0 ONNX not present at $model", model.isFile)
        val refs = json.decodeFromString(ExcerptsRef.serializer(), File(fixtures, "beatthis-excerpts-reference.json").readText())
        val present = refs.excerpts.filter { File(data, it.file).isFile }
        assumeTrue("no reference audio under $data", present.isNotEmpty())
        BeatThis(model.readBytes()).use { bt ->
            for (e in present) {
                val (audio, rate) = readWav(File(data, e.file), e.start_s, e.end_s)
                val t0 = System.nanoTime()
                val got = bt.track(audio, rate)
                check("${e.file} ${e.start_s}-${e.end_s} s", BeatsRef(e.beats, e.downbeats), got, (System.nanoTime() - t0) / 1_000_000)
            }
        }
    }
}
