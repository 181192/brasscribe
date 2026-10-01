package no.brasscribe.play.core

import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.CompositionJson
import no.brasscribe.play.model.TickMap
import no.brasscribe.play.pitch.BandDraftPipeline
import no.brasscribe.play.pitch.BasicPitch
import no.brasscribe.play.pitch.BeatThis
import no.brasscribe.play.test.Slow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.experimental.categories.Category
import java.io.File
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioSystem

/**
 * The phone's band draft on the JVM (the same ONNX models and the host build of the core) on the ten
 * ChoraleBricks brass quartet mixes, compared with the engine's brass-band profile without MuScriptor
 * (apps/apple/scripts/make-band-draft-reference.sh, in data/runs/apple/<name>-band-draft-ref). Every
 * device composition is written to <tmp>/brasscribe-band-draft for scoring with the eval.
 */
@Category(Slow::class)
class BandDraftTest {
    private val models = File(System.getProperty("brasscribe.models") ?: "missing")
    private val data = File(System.getProperty("brasscribe.data") ?: "missing")

    private fun readMono(f: File): Pair<FloatArray, Int> {
        val src = AudioSystem.getAudioInputStream(f)
        val rate = src.format.sampleRate.toInt()
        val pcm = AudioSystem.getAudioInputStream(AudioFormat(rate.toFloat(), 16, src.format.channels, true, false), src)
        val bytes = pcm.readAllBytes()
        val ch = src.format.channels
        val out = FloatArray(bytes.size / (2 * ch)) { i ->
            var s = 0f
            for (c in 0 until ch) {
                val at = (i * ch + c) * 2
                s += ((bytes[at].toInt() and 0xff) or (bytes[at + 1].toInt() shl 8)).toShort() / 32768f
            }
            s / ch
        }
        return out to rate
    }

    /** Note F1 on pitch and written start of one voice. */
    private fun f1(a: Composition, b: Composition, voice: String): Double {
        val got = a.voices.first { it.id == voice }.notes.map { it.pitch to it.start }
        val want = b.voices.first { it.id == voice }.notes.map { it.pitch to it.start }.toMutableList()
        val hit = got.count { want.remove(it) }
        return if (got.isEmpty() && want.isEmpty()) 1.0 else 2.0 * hit / (got.size + hit + want.size)
    }

    /** Note F1 on pitch and performed onset (within 50 ms) of one voice: what was heard, whatever the grid. */
    private fun f1Heard(a: Composition, b: Composition, voice: String): Double {
        val got = a.voices.first { it.id == voice }.notes
        val want = b.voices.first { it.id == voice }.notes.toMutableList()
        val hit = got.count { n ->
            val j = want.indexOfFirst { it.pitch == n.pitch && kotlin.math.abs((it.onsetS ?: -9.0) - (n.onsetS ?: 9.0)) <= 0.05 }
            if (j >= 0) { want.removeAt(j); true } else false
        }
        return if (got.isEmpty() && want.isEmpty()) 1.0 else 2.0 * hit / (got.size + hit + want.size)
    }

    /** Bars per part of a MusicXML score. */
    private fun barsPerPart(xml: String): List<Int> = xml.split("<part id=").drop(1).map { Regex("<measure ").findAll(it).count() }

    @Test
    fun theChoralesGiveABandScoreLikeTheEngines() {
        val core = RustCoreBridge.load()
        assumeTrue("host core missing", core != null)
        assumeTrue("models missing", File(models, "basic-pitch/nmp-b1.onnx").isFile && File(models, "beat-this/beat-this-small0.onnx").isFile)
        val chorales = File(data, "eval/choralebricks-brass4").listFiles()?.filter { File(it, "mix.wav").isFile }?.sortedBy { it.name }.orEmpty()
        assumeTrue("ChoraleBricks mixes missing", chorales.isNotEmpty())
        val out = File(System.getProperty("java.io.tmpdir"), "brasscribe-band-draft").apply { mkdirs() }
        val bp = BasicPitch(File(models, "basic-pitch/nmp-b1.onnx").readBytes())
        val bt = BeatThis(File(models, "beat-this/beat-this-small0.onnx").readBytes())
        val pipeline = BandDraftPipeline(bp, bt, core!!)
        val melody = mutableListOf<Double>(); val bass = mutableListOf<Double>()
        val melodyGrid = mutableListOf<Double>(); val sameGrid = mutableListOf<Double>(); val barDiff = mutableListOf<Int>()
        try {
            for (dir in chorales) {
                val (audio, rate) = readMono(File(dir, "mix.wav"))
                val (take, stats) = pipeline.listen(audio, rate, "Reference")
                File(out, "${dir.name}.beats").writeText(take.beatsText)
                File(out, "${dir.name}-bp.mid").writeBytes(no.brasscribe.play.model.MidiWriter.write(take.basicPitch, tpq = no.brasscribe.play.model.MidiWriter.BASIC_PITCH_TPQ))
                for ((lineup, parts) in listOf("minimal" to 8, "quartet" to 4)) {
                    val a0 = System.nanoTime()
                    val arranged = pipeline.arrange(take, ArrangeOptions(lineup = lineup))!!
                    val arrangeMs = (System.nanoTime() - a0) / 1_000_000
                    File(out, "${dir.name}-$lineup.json").writeText(arranged.compositionJson)
                    val bars = barsPerPart(arranged.musicXml)
                    assertEquals("${dir.name} $lineup parts", parts, bars.size)
                    assertTrue("${dir.name} $lineup bars per part $bars", bars.all { it == bars[0] } && bars[0] >= 4)
                    val refFile = File(data, "runs/apple/${dir.name}-band-draft-ref/$lineup/composition.json")
                    if (!refFile.isFile) {
                        println("${dir.name} $lineup: %.1f s audio, %d notes, %d beats, stages %s ms, arrange %d ms; %d bars; no reference"
                            .format(stats.audioSeconds, stats.basicPitchNotes, stats.beats, stats.ms, arrangeMs, bars[0]))
                        continue
                    }
                    val ref = CompositionJson.decode(refFile.readText())
                    // What was heard (pitch and performed onset) is the models' parity; the written grid also
                    // depends on Beat This!'s peaks, where ONNX on the JVM and PyTorch can differ by a beat.
                    val fm = f1Heard(arranged.composition, ref, "melody"); val fb = f1Heard(arranged.composition, ref, "bass")
                    val fmGrid = f1(arranged.composition, ref, "melody")
                    // The arranger's parity: the phone's notes on the engine's own beats give the engine's score.
                    val refBeats = File(refFile.parentFile.parentFile, "beats-small0.beats").readText()
                    val onRefBeats = pipeline.arrange(take.copy(beatsText = refBeats), ArrangeOptions(lineup = lineup))!!.composition
                    val fmSame = f1(onRefBeats, ref, "melody")
                    val refBars = TickMap(ref).totalBars; val gotBars = TickMap(arranged.composition).totalBars
                    println("${dir.name} $lineup: %.1f s audio, %d notes, %d beats, stages %s ms, arrange %d ms; bars %d vs engine %d; F1 heard melody %.3f, bass %.3f; F1 written melody %.3f, on the engine's beats %.3f"
                        .format(stats.audioSeconds, stats.basicPitchNotes, stats.beats, stats.ms, arrangeMs, gotBars, refBars, fm, fb, fmGrid, fmSame))
                    if (lineup == "minimal") { melody += fm; bass += fb; melodyGrid += fmGrid; sameGrid += fmSame; barDiff += gotBars - refBars }
                    assertTrue("${dir.name} $lineup bars $gotBars vs $refBars", kotlin.math.abs(gotBars - refBars) <= 2)
                    assertTrue("${dir.name} $lineup melody F1 $fm", fm >= 0.9)
                    assertTrue("${dir.name} $lineup bass F1 $fb", fb >= 0.9)
                    assertTrue("${dir.name} $lineup melody F1 on the engine's beats $fmSame", fmSame >= 0.95)
                }
            }
        } finally {
            listOf(bp, bt).forEach { it.close() }
        }
        if (melody.isNotEmpty()) println("band draft vs engine, %d chorales: mean F1 heard melody %.3f, bass %.3f; written melody %.3f, on the engine's beats %.3f; bar differences %s; compositions in %s"
            .format(melody.size, melody.average(), bass.average(), melodyGrid.average(), sameGrid.average(), barDiff, out))
    }
}
