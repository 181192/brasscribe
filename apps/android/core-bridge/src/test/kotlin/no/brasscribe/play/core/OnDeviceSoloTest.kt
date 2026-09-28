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
import no.brasscribe.play.test.Slow
import org.junit.experimental.categories.Category

/**
 * The phone's offline solo path on the JVM (the same ONNX models and the host build of the core) on
 * the first 30 s of the URMP March trumpet, compared with the engine's solo profile on the same clip
 * when -Pbrasscribe.engineSolo=<dir with composition.json> is given.
 */
@Category(Slow::class)
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

    /**
     * The reference of the on-device path (apps/apple/scripts/make-ondevice-reference.sh on
     * data/runs/apple/entertainer-tpt1-30s.wav): the Python tools the engine uses and the layered
     * arranger with only a solo layer, minimal lineup.
     */
    @Test
    fun entertainerMatchesTheLayeredReference() {
        val core = RustCoreBridge.load()
        assumeTrue("host core missing", core != null)
        assumeTrue("models missing", File(models, "swift-f0/swift-f0-window.onnx").isFile)
        val runs = File(System.getProperty("brasscribe.data") ?: "missing", "runs/apple")
        val clipE = File(runs, "entertainer-tpt1-30s.wav")
        val ref = File(runs, "entertainer-ref/layered/composition.json")
        assumeTrue("Entertainer clip or reference missing", clipE.isFile && ref.isFile)
        val (audio, rate) = readMono(clipE, 60.0)
        val sw = SwiftF0(File(models, "swift-f0/swift-f0-window.onnx").readBytes())
        val bp = BasicPitch(File(models, "basic-pitch/nmp-b1.onnx").readBytes())
        val bt = BeatThis(File(models, "beat-this/beat-this-small0.onnx").readBytes())
        val pipeline = SoloPipeline(sw, bp, bt, core!!)
        val (take, stats) = pipeline.listen(audio, rate, "Reference", null)
        val arranged = pipeline.arrange(take, ArrangeOptions(lineup = "minimal"))!!
        listOf(sw, bp, bt).forEach { it.close() }
        val expected = CompositionJson.decode(ref.readText())
        val got = arranged.composition.voices.first { it.role == VoiceRole.MELODY }.notes.sortedWith(compareBy({ it.start }, { it.pitch }))
        val want = expected.voices.first { it.role == VoiceRole.MELODY }.notes.sortedWith(compareBy({ it.start }, { it.pitch }))
        val remaining = want.map { Triple(it.pitch, it.start, it.dur) }.toMutableList()
        val exact = got.count { remaining.remove(Triple(it.pitch, it.start, it.dur)) }
        val onsets = want.map { it.pitch to it.start }.toMutableList()
        val sameStart = got.count { onsets.remove(it.pitch to it.start) }
        val gotKeys = got.map { it.pitch to it.start }.toMutableList()
        want.filter { !gotKeys.remove(it.pitch to it.start) }.forEach { println("  only in reference: $it") }
        val wantKeys = want.map { it.pitch to it.start }.toMutableList()
        got.filter { !wantKeys.remove(it.pitch to it.start) }.forEach { println("  only on the phone: $it") }
        println("  sw first: ${take.swiftF0.take(3)}; beats: ${take.beatsText.lines().take(4)}")
        val bars = TickMap(arranged.composition).totalBars
        val refBars = TickMap(expected).totalBars
        println("Entertainer on the phone path: SwiftF0 %d, Basic Pitch %d, beats %d; %d melody notes vs %d, %d bars vs %d; F1 pitch+start+dur %.3f, F1 pitch+start %.3f, key %s vs %s"
            .format(stats.swiftF0Notes, stats.basicPitchNotes, stats.beats, got.size, want.size, bars, refBars,
                2.0 * exact / (got.size + want.size), 2.0 * sameStart / (got.size + want.size),
                arranged.composition.keys.firstOrNull()?.fifths, expected.keys.firstOrNull()?.fifths))
        assertTrue("F1 pitch+start+dur", 2.0 * exact / (got.size + want.size) >= 0.98)
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
