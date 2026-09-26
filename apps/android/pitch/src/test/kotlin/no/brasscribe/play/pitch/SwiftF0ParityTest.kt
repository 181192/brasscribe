package no.brasscribe.play.pitch

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import no.brasscribe.play.model.KotlinCoreBridge
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.log2
import kotlin.math.min
import kotlin.math.sin

/** The same melody as src/test/python/make_reference.py, computed sample for sample. */
object SyntheticMelody {
    private const val SR = 16000
    private val NOTES = List(3) {
        listOf(70 to 0.8, 72 to 0.4, 74 to 0.4, 75 to 1.2, 0 to 0.3, 77 to 0.6, 79 to 0.6, 81 to 0.3, 82 to 1.6, 0 to 0.5,
            65 to 0.9, 67 to 0.45, 69 to 0.45, 70 to 2.0, 0 to 0.4)
    }.flatten()

    fun samples(): FloatArray {
        val out = ArrayList<Float>()
        for ((pitch, dur) in NOTES) {
            val n = Math.round(dur * SR).toInt()
            if (pitch == 0) { repeat(n) { out += 0f }; continue }
            val f0 = 440.0 * Math.pow(2.0, (pitch - 69) / 12.0)
            for (i in 0 until n) {
                val t = i.toDouble() / SR
                var tone = 0.0
                for (h in 1..6) tone += (1.0 / h) * sin(2 * PI * f0 * h * t)
                val env = min(1.0, min(t / 0.02, (dur - t) / 0.02))
                out += (0.25 * tone * env).toFloat()
            }
        }
        return out.toFloatArray()
    }

    /** MIDI pitches of the sounding notes, in order. */
    val pitches: List<Int> = NOTES.map { it.first }.filter { it != 0 }
}

class SwiftF0ParityTest {
    @Serializable
    data class RefNote(val start: Double, val end: Double, val pitch_hz: Double)

    @Serializable
    data class Reference(
        val samples: Int, val frames: Int, val confidence: List<Double>, val pitch_hz: List<Double>,
        val loudness_db: List<Double>, val notes: List<RefNote>,
    )

    private val model = File(System.getProperty("brasscribe.swiftf0") ?: "missing")
    private val reference: Reference by lazy {
        Json { ignoreUnknownKeys = true }.decodeFromString(Reference.serializer(),
            File(System.getProperty("brasscribe.pitchFixtures"), "swiftf0-reference.json").readText())
    }

    @Test
    fun matchesUpstreamSwiftF0OnTheSyntheticMelody() {
        assumeTrue("SwiftF0 ONNX export not present at $model", model.isFile)
        val audio = SyntheticMelody.samples()
        assertEquals(reference.samples, audio.size)
        val track = SwiftF0(model.readBytes()).use { it.detect(audio) }
        assertEquals(reference.frames, track.size)

        var voicedAgree = 0
        var maxLoudDiff = 0.0
        var maxCentsVoiced = 0.0
        for (i in 0 until track.size) {
            val a = track.confidence[i] >= 0.5
            val b = reference.confidence[i] >= 0.5
            if (a == b) voicedAgree++
            maxLoudDiff = maxOf(maxLoudDiff, abs(track.loudnessDb[i] - reference.loudness_db[i]))
            if (a && b) maxCentsVoiced = maxOf(maxCentsVoiced, abs(1200 * log2(track.pitchHz[i] / reference.pitch_hz[i])))
        }
        val agreement = voicedAgree.toDouble() / track.size
        println("SwiftF0 parity: voicing agreement %.4f, max voiced pitch diff %.2f cents, max loudness diff %.4f dB"
            .format(agreement, maxCentsVoiced, maxLoudDiff))
        assertTrue("voicing agreement $agreement", agreement >= 0.99)
        assertTrue("pitch diff $maxCentsVoiced cents", maxCentsVoiced < 5.0)
        assertTrue("loudness diff $maxLoudDiff dB", maxLoudDiff < 0.01)

        val notes = NoteSegmenter.segment(track)
        println("SwiftF0 parity: ${notes.size} notes (reference ${reference.notes.size})")
        assertEquals(reference.notes.size, notes.size)
        for ((got, want) in notes.zip(reference.notes)) {
            assertEquals(want.start, got.start, 0.033)
            assertEquals(want.end, got.end, 0.033)
            assertEquals(PitchNote(0.0, 0.0, want.pitch_hz, 1.0).midi, got.midi)
        }
        assertEquals(SyntheticMelody.pitches, notes.map { it.midi })
    }

    @Test
    fun segmenterMatchesReferenceGivenReferenceFrames() {
        // Pure port check, no model needed: segment the reference frames and compare with upstream notes.
        val track = PitchTrack(reference.pitch_hz.toDoubleArray(), reference.confidence.toDoubleArray(), reference.loudness_db.toDoubleArray())
        val notes = NoteSegmenter.segment(track)
        assertEquals(reference.notes.size, notes.size)
        for ((got, want) in notes.zip(reference.notes)) {
            assertEquals(want.start, got.start, 1e-3)
            assertEquals(want.end, got.end, 1e-3)
            // The stored frames are rounded to 0.001 Hz, which can move the fitted pitch by about a cent.
            assertEquals(0.0, 1200 * log2(got.pitchHz / want.pitch_hz), 2.0)
        }
    }

    @Test
    fun soloTranscriptionOfA44kHzTakeGivesTheMelody() {
        assumeTrue("SwiftF0 ONNX export not present at $model", model.isFile)
        val audio44 = Resampler.resample(SyntheticMelody.samples(), 16000, 44100)
        val result = SwiftF0(model.readBytes()).use { SoloTranscriber(it, KotlinCoreBridge).transcribe(audio44, 44100, "Synthetic", bpm = 75.0) }
        val placed = result.composition.voices.single().notes
        println("Solo transcription: ${result.notes} notes from %.1f s of audio, SwiftF0 %d ms on this JVM, key %d"
            .format(result.audioSeconds, result.detectMillis, result.composition.keys[0].fifths))
        assertEquals(SyntheticMelody.pitches, placed.map { it.pitch })
        assertEquals(-2, result.composition.keys[0].fifths) // B-flat major material
    }

    @Test
    fun resamplerKeepsASineAtItsPitch() {
        val sr = 48000
        val sine = FloatArray(sr) { (0.5 * sin(2 * PI * 440.0 * it / sr)).toFloat() }
        val out = Resampler.resample(sine, sr, 16000)
        assertEquals(16000, out.size)
        // Zero crossings per second of a 440 Hz sine: 880.
        val crossings = (1 until out.size).count { (out[it - 1] < 0) != (out[it] < 0) }
        assertEquals(880.0, crossings.toDouble(), 2.0)
    }
}
