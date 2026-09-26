package no.brasscribe.play.core

import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.CompositionJson
import no.brasscribe.play.model.TickMap
import no.brasscribe.play.model.VoiceRole
import no.brasscribe.play.pitch.BasicPitch
import no.brasscribe.play.pitch.BeatThis
import no.brasscribe.play.pitch.SoloPipeline
import no.brasscribe.play.pitch.SwiftF0
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioSystem
import kotlin.math.abs

/**
 * The phone's offline solo path on the JVM (the same ONNX models and the host build of the core) on
 * the first 30 s of the URMP March trumpet, compared with the engine's solo profile on the same clip
 * when -Pbrasscribe.engineSolo=<dir with composition.json> is given.
 */
class OnDeviceSoloTest {
    private val models = File(System.getProperty("brasscribe.models") ?: "missing")
    private val clip = File(System.getProperty("brasscribe.data") ?: "missing", "urmp/Dataset/10_March_tpt_sax/AuSep_1_tpt_10_March.wav")

    private fun readMono(f: File, seconds: Double): Pair<FloatArray, Int> {
        val src = AudioSystem.getAudioInputStream(f)
        val rate = src.format.sampleRate.toInt()
        val pcm = AudioSystem.getAudioInputStream(AudioFormat(rate.toFloat(), 16, src.format.channels, true, false), src)
        val bytes = pcm.readAllBytes()
        val ch = src.format.channels
        val frames = minOf(bytes.size / (2 * ch), (seconds * rate).toInt())
        val out = FloatArray(frames) { i ->
            var s = 0f
            for (c in 0 until ch) {
                val at = (i * ch + c) * 2
                s += ((bytes[at].toInt() and 0xff) or (bytes[at + 1].toInt() shl 8)).toShort() / 32768f
            }
            s / ch
        }
        return out to rate
    }

    @Test
    fun soloOnThePhoneAgainstTheEngineSoloProfile() {
        val core = RustCoreBridge.load()
        assumeTrue("host core missing", core != null)
        assumeTrue("models missing", File(models, "swift-f0/swift-f0-window.onnx").isFile)
        assumeTrue("URMP clip missing", clip.isFile)
        val (audio, rate) = readMono(clip, 30.0)
        val sw = SwiftF0(File(models, "swift-f0/swift-f0-window.onnx").readBytes())
        val bp = BasicPitch(File(models, "basic-pitch/nmp-b1.onnx").readBytes())
        val bt = BeatThis(File(models, "beat-this/beat-this-small0.onnx").readBytes())
        val pipeline = SoloPipeline(sw, bp, bt, core!!)
        val t0 = System.nanoTime()
        val (take, stats) = pipeline.listen(audio, rate, "March", null)
        val a0 = System.nanoTime()
        val arranged = pipeline.arrange(take, ArrangeOptions())!!
        val arrangeMs = (System.nanoTime() - a0) / 1_000_000
        val totalMs = (System.nanoTime() - t0) / 1_000_000
        listOf(sw, bp, bt).forEach { it.close() }
        val melody = arranged.composition.voices.first { it.role == VoiceRole.MELODY }.notes
        println("on-device solo (JVM): %d SwiftF0 notes, %d Basic Pitch notes, %d beats / %d downbeats, stages %s ms, arrange %d ms, total %d ms; %d melody notes, %d parts"
            .format(stats.swiftF0Notes, stats.basicPitchNotes, stats.beats, stats.downbeats, stats.ms, arrangeMs, totalMs, melody.size, arranged.parts.size))
        assertTrue(melody.size > 20)
        assertTrue(arranged.musicXml.contains("Solo Cornet"))

        val engineDir = System.getProperty("brasscribe.engineSolo")?.let(::File)
        assumeTrue("engine solo output not given", engineDir != null && File(engineDir, "composition.json").isFile)
        val engine = CompositionJson.decode(File(engineDir, "composition.json").readText())
        val ref = engine.voices.first { it.role == VoiceRole.MELODY }.notes
        // Note F1 on performed onsets (50 ms) and pitch, then on written positions (same bar and beat).
        fun f1(match: Int) = 2.0 * match / (melody.size + ref.size)
        val used = BooleanArray(ref.size)
        var byTime = 0
        for (n in melody) {
            val j = ref.indices.firstOrNull { !used[it] && ref[it].pitch == n.pitch && abs((ref[it].onsetS ?: -9.0) - (n.onsetS ?: 9.0)) <= 0.05 }
            if (j != null) { used[j] = true; byTime++ }
        }
        val mapA = TickMap(arranged.composition)
        val mapE = TickMap(engine)
        val refPos = ref.map { Triple(it.pitch, mapE.barOf(it.start), (it.start - mapE.barStart(mapE.barOf(it.start))) / 6) }.toMutableList()
        var byPos = 0
        for (n in melody) {
            val key = Triple(n.pitch, mapA.barOf(n.start), (n.start - mapA.barStart(mapA.barOf(n.start))) / 6)
            if (refPos.remove(key)) byPos++
        }
        // Written position as time: each note's grid tick mapped back through its own beat list (80 ms).
        val usedG = BooleanArray(ref.size)
        var byGrid = 0
        for (n in melody) {
            val t = mapA.secondsAt(n.start)
            val j = ref.indices.firstOrNull { !usedG[it] && ref[it].pitch == n.pitch && abs(mapE.secondsAt(ref[it].start) - t) <= 0.08 }
            if (j != null) { usedG[j] = true; byGrid++ }
        }
        val sameKey = arranged.composition.keys.firstOrNull()?.fifths == engine.keys.firstOrNull()?.fifths
        println("engine solo profile: %d melody notes, key %s; phone: %d notes, key %s; F1 onset+pitch %.3f, F1 bar+sixteenth+pitch %.3f, F1 grid time+pitch %.3f, same key %s, meter %s vs %s"
            .format(ref.size, engine.keys.firstOrNull()?.fifths, melody.size, arranged.composition.keys.firstOrNull()?.fifths,
                f1(byTime), f1(byPos), f1(byGrid), sameKey, arranged.composition.meters.firstOrNull(), engine.meters.firstOrNull()))
        File(System.getProperty("java.io.tmpdir"), "phone-solo-composition.json").writeText(arranged.compositionJson)
    }
}
