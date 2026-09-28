package no.brasscribe.play

import alphaTab.IEventEmitter
import alphaTab.IEventEmitterOfT
import alphaTab.core.ecmaScript.Float32Array
import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.midi.ControlChangeEvent
import alphaTab.midi.ControllerType
import alphaTab.midi.MidiFile
import alphaTab.midi.NoteOffEvent
import alphaTab.midi.NoteOnEvent
import alphaTab.midi.ProgramChangeEvent
import alphaTab.midi.TempoChangeEvent
import alphaTab.synth.AlphaSynth
import alphaTab.synth.ISynthOutput
import alphaTab.synth.ISynthOutputDevice
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import no.brasscribe.play.audio.LoudnessMeter
import no.brasscribe.play.audio.OutputStage
import no.brasscribe.play.audio.PlaybackLevels
import no.brasscribe.play.audio.RealisticSynth
import no.brasscribe.play.score.BandSoundFontFile
import no.brasscribe.play.score.BandSoundMap
import no.brasscribe.play.score.ChannelPlan
import no.brasscribe.play.score.StagedSynthOutput
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.roundToInt

/**
 * Playback loudness on the device (sounds/playback-levels.json): the full-band test phrase rendered
 * offline through alphaTab's synth with the app's channel plan, balance and output stage, the
 * metronome's click, and the sfizz tier's C++ limiter against the Kotlin curve. The phrase needs
 * sounds/phrases.py's phrases.json pushed to /data/local/tmp/brasscribe/phrases.json (skipped without it).
 */
@RunWith(AndroidJUnit4::class)
class PlaybackLevelTest {
    private val target get() = InstrumentationRegistry.getInstrumentation().targetContext

    private class Emitter : IEventEmitter {
        private val handlers = ArrayList<() -> Unit>()
        override fun on(value: () -> Unit): () -> Unit { handlers += value; return { off(value) } }
        override fun off(value: () -> Unit) { handlers -= value }
        fun trigger() { for (h in handlers.toList()) h() }
    }

    private class EmitterOf<T> : IEventEmitterOfT<T> {
        override fun on(value: (T) -> Unit): () -> Unit = {}
        override fun off(value: (T) -> Unit) {}
    }

    /** Collects what alphaTab's synth renders; the test pulls by triggering sample requests. */
    private class Capture : ISynthOutput {
        val out = ArrayList<Float>()
        override val sampleRate: Double = 44100.0
        override val ready = Emitter()
        override val samplesPlayed: IEventEmitterOfT<Double> = EmitterOf()
        override val sampleRequest = Emitter()
        override fun open(bufferTimeInMilliseconds: Double) { ready.trigger() }
        override fun play() {}
        override fun pause() {}
        override fun destroy() {}
        override fun activate() {}
        override fun resetSamples() {}
        override fun addSamples(samples: Float32Array) { for (v in samples.data) out += v }
        override suspend fun enumerateOutputDevices(): alphaTab.collections.List<ISynthOutputDevice> = alphaTab.collections.List()
        override suspend fun setOutputDevice(device: ISynthOutputDevice?) {}
        override suspend fun getOutputDevice(): ISynthOutputDevice? = null

        fun pull(seconds: Double): FloatArray {
            val want = (seconds * sampleRate).toInt() * 2
            var guard = 0
            while (out.size < want && guard++ < 100_000) sampleRequest.trigger()
            return out.take(want).toFloatArray()
        }
    }

    private fun soundFont(): ByteArray? = runCatching { target.assets.open(BandSoundFontFile.ASSET).use { it.readBytes() } }.getOrNull()
    private fun mapping(): BandSoundMap? = runCatching { BandSoundMap.parse(String(target.assets.open("sounds/mapping.json").use { it.readBytes() })) }.getOrNull()

    private fun db(x: Float) = 20 * log10(maxOf(x.toDouble(), 1e-9))
    private fun peak(x: FloatArray) = x.maxOfOrNull { abs(it) } ?: 0f

    /** The phrase as the app would play it: one channel per part, its preset and balance. */
    private fun renderPhrase(staged: Boolean): FloatArray? {
        val phrases = File("/data/local/tmp/brasscribe/phrases.json").takeIf { it.canRead() } ?: return null
        val sf2 = soundFont() ?: return null
        val map = mapping() ?: return null
        val band = Json.parseToJsonElement(phrases.readText()).jsonObject.getValue("band").jsonObject.entries.toList()
        val sounds = band.map { map.resolve(it.key)!! }
        val channels = ChannelPlan.forPlayback(sounds.map { it.percussion })
        val ticksPerSecond = 1920.0 // 960 a beat at 120 bpm
        val midi = MidiFile().apply { division = 960.0 }
        midi.addEvent(TempoChangeEvent(0.0, 500000.0))
        val events = ArrayList<Triple<Double, Int, alphaTab.midi.MidiEvent>>()
        var end = 0.0
        band.forEachIndexed { i, (_, v) ->
            val ch = channels[i].toDouble()
            val s = sounds[i]
            if (!s.percussion) midi.addEvent(ControlChangeEvent(0.0, 0.0, ch, ControllerType.BankSelectCoarse, s.bank.toDouble()))
            midi.addEvent(ProgramChangeEvent(0.0, 0.0, ch, if (s.percussion) 0.0 else s.program.toDouble()))
            for (n in v.jsonObject.getValue("notes").jsonArray.map { it.jsonArray }) {
                val on = (n[0].jsonPrimitive.double * ticksPerSecond).roundToInt().toDouble()
                val off = (n[1].jsonPrimitive.double * ticksPerSecond).roundToInt().toDouble()
                val key = n[2].jsonPrimitive.int.toDouble()
                events += Triple(on, 1, NoteOnEvent(0.0, on, ch, key, n[3].jsonPrimitive.int.toDouble()))
                events += Triple(off, 0, NoteOffEvent(0.0, off, ch, key, 0.0))
                end = maxOf(end, n[1].jsonPrimitive.double)
            }
        }
        for (e in events.sortedWith(compareBy({ it.first }, { it.second }))) midi.addEvent(e.third)
        val capture = Capture()
        val synth = AlphaSynth(if (staged) StagedSynthOutput(capture) else capture, 500.0)
        synth.metronomeVolume = 0.0
        synth.countInVolume = 0.0
        synth.loadSoundFont(Uint8Array(sf2.asUByteArray()), false)
        synth.loadMidiFile(midi)
        band.indices.forEach { i -> synth.setChannelVolume(channels[i].toDouble(), sounds[i].gain) }
        synth.play()
        val audio = capture.pull(end + 2.0)
        synth.destroy()
        return audio
    }

    @Test
    fun fullBandPhraseLandsOnTheSharedTarget() {
        val before = renderPhrase(staged = false)
        assumeTrue("phrases.json not pushed to /data/local/tmp/brasscribe", before != null)
        val after = renderPhrase(staged = true)!!
        val lb = LoudnessMeter(44100.0, 2).apply { process(before!!) }.integratedLufs
        val la = LoudnessMeter(44100.0, 2).apply { process(after) }.integratedLufs
        android.util.Log.i("LEVELS", "android alphaTab phrase before: peak %.2f dBFS, %.2f LUFS; after: peak %.2f dBFS, %.2f LUFS at %.1f dB"
            .format(db(peak(before!!)), lb, db(peak(after)), la, PlaybackLevels.ALPHATAB_GAIN_DB))
        assertTrue("peak ${peak(after)}", peak(after) <= OutputStage.CEILING)
        assertEquals(PlaybackLevels.BAND_PHRASE_LUFS, la, 1.0)
    }

    /** The metronome goes through the stage too and clicks at the shared level, below the knee. */
    @Test
    fun metronomeClicksAtTheSharedLevel() {
        val sf2 = soundFont()
        assumeTrue("band SoundFont not bundled", sf2 != null)
        val xml = InstrumentationRegistry.getInstrumentation().context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }
        val settings = alphaTab.Settings()
        val score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(Uint8Array(xml.asUByteArray()), settings)
        val full = MidiFile()
        alphaTab.midi.MidiFileGenerator(score, settings, alphaTab.midi.AlphaSynthMidiFileHandler(full, false)).generate()
        // the score without its notes: only the metronome sounds
        val midi = MidiFile().apply { division = full.division }
        for (e in full.events) if (e !is NoteOnEvent && e !is NoteOffEvent) midi.addEvent(e)
        val capture = Capture()
        val synth = AlphaSynth(StagedSynthOutput(capture), 500.0)
        synth.loadSoundFont(Uint8Array(sf2!!.asUByteArray()), false)
        synth.loadMidiFile(midi)
        synth.metronomeVolume = PlaybackLevels.factor(PlaybackLevels.METRONOME_GAIN_DB).toDouble() // as ScoreController.setMetronome
        synth.play()
        val clicks = capture.pull(4.0)
        synth.destroy()
        val p = db(peak(clicks))
        android.util.Log.i("LEVELS", "android metronome click peak %.2f dBFS".format(p))
        assertEquals(PlaybackLevels.METRONOME_CLICK_PEAK_DBFS, p, 1.5)
    }

    /** The sfizz tier's limiter (C++) is the Kotlin curve, which the JVM tests hold to the shared vectors. */
    @Test
    fun nativeLimiterIsTheSharedCurve() {
        for (i in -500..500) {
            val x = i / 100f
            assertEquals("limit($x)", OutputStage.limit(x), RealisticSynth.limit(x), 1e-6f)
        }
        // checkpoints from sounds/output-stage-vectors.json
        assertEquals(0.8, RealisticSynth.limit(0.8f).toDouble(), 1e-6)
        assertEquals(0.848752481, RealisticSynth.limit(0.85f).toDouble(), 1e-6)
        assertEquals(0.975821366, RealisticSynth.limit(1.2f).toDouble(), 1e-6)
        assertEquals(-0.979999417, RealisticSynth.limit(-2f).toDouble(), 1e-6)
        assertTrue(RealisticSynth.limit(50f) <= OutputStage.CEILING)
    }
}
