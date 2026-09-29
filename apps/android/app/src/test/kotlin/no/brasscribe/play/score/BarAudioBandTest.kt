package no.brasscribe.play.score

import alphaTab.IEventEmitter
import alphaTab.IEventEmitterOfT
import alphaTab.core.ecmaScript.Float32Array
import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.midi.AlphaSynthMidiFileHandler
import alphaTab.midi.MidiFile
import alphaTab.midi.MidiFileGenerator
import alphaTab.synth.AlphaSynth
import alphaTab.synth.ISynthOutput
import alphaTab.synth.ISynthOutputDevice
import no.brasscribe.play.audio.LoudnessMeter
import no.brasscribe.play.audio.PcmAudio
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

/**
 * "Listen to this bar" with the band SoundFont: the bars' subset of the phone SoundFont sounds exactly
 * as the whole file does, for a fraction of its size. Needs data/sounds/band/brasscribe-band-mobile.sf2
 * and the golden arrangement (data/golden); skipped without them.
 */
class BarAudioBandTest {
    private val sounds = File(System.getProperty("brasscribe.sounds") ?: "../../../sounds")
    private val sf2 = File(sounds.parentFile, "data/sounds/band/brasscribe-band-mobile.sf2")
    private val golden = File(sounds.parentFile, "data/golden/mikkel-arranged-band/brass-band.musicxml")
    private val map = BandSoundMap.parse(File(sounds, "mapping.json").readText())

    private fun render(first: Int, last: Int, whole: Boolean): PcmAudio =
        BarAudio.render(golden.readText(), first, last, map, sf2, whole) { error("the band SoundFont plays") }!!

    @Test
    fun barsSoundAsWithTheWholeSoundFont() {
        assumeTrue("no band SoundFont in data/sounds/band", sf2.isFile)
        assumeTrue("no golden arrangement in data/golden", golden.isFile)
        for ((first, last) in listOf(1 to 4, 17 to 17, 60 to 61)) {
            val t0 = System.nanoTime()
            val subset = render(first, last, whole = false)
            val t1 = System.nanoTime()
            val whole = render(first, last, whole = true)
            val t2 = System.nanoTime()
            println("bars $first-$last: subset %d ms, whole file %d ms, %.1f s, peak %.3f"
                .format((t1 - t0) / 1_000_000, (t2 - t1) / 1_000_000, subset.samples.size / 44100.0, subset.peak()))
            println("bars $first-$last: subset SoundFont %d KB".format(subsetSize(first, last) shr 10))
            assertTrue("bars $first-$last are not silent", subset.peak() > 0.05f)
            assertEquals(whole.samples.size, subset.samples.size)
            val diff = subset.samples.indices.maxOf { abs(subset.samples[it] - whole.samples[it]) }
            assertEquals("bars $first-$last: the subset plays the same samples", 0f, diff, 1e-6f)
        }
    }

    private fun subsetSize(first: Int, last: Int): Int {
        val settings = alphaTab.Settings()
        val score = ScoreLoader.loadScoreFromBytes(Uint8Array(golden.readBytes().asUByteArray()), settings)
        BandPlan.apply(score, BandPlan.partNames(score), map, true)
        val midi = MidiFile()
        MidiFileGenerator(score, settings, AlphaSynthMidiFileHandler(midi, true)).generate()
        val bars = score.masterBars
        val (uses, programs) = BarAudio.uses(midi, bars[first - 1].start, bars[last - 1].start + bars[last - 1].calculateDuration(false))
        return SoundFontSubset.build(sf2, uses, programs).size
    }

    /**
     * The bars at the score screen's level: its player (alphaTab's synth with the whole band SoundFont,
     * the plan's channel volumes, the output stage on the stereo stream) against the bars rendered
     * here (mono, the stage after the downmix), both played on two speakers.
     */
    @Test
    fun barsPlayAtTheScoreScreensLevel() {
        assumeTrue("no band SoundFont in data/sounds/band", sf2.isFile)
        assumeTrue("no golden arrangement in data/golden", golden.isFile)
        for ((first, last) in listOf(1 to 4, 60 to 61)) levelOf(first, last)
    }

    private fun levelOf(first: Int, last: Int) {
        val bar = render(first, last, whole = false)
        val settings = alphaTab.Settings()
        val score = ScoreLoader.loadScoreFromBytes(Uint8Array(golden.readBytes().asUByteArray()), settings)
        val plan = BandPlan.apply(score, BandPlan.partNames(score), map, true)
        val midi = MidiFile()
        MidiFileGenerator(score, settings, AlphaSynthMidiFileHandler(midi, true)).generate()
        val capture = Capture()
        val synth = AlphaSynth(StagedSynthOutput(capture), 500.0)
        synth.metronomeVolume = 0.0
        synth.countInVolume = 0.0
        synth.loadSoundFont(Uint8Array(sf2.readBytes().asUByteArray()), false)
        synth.loadMidiFile(midi)
        // as ScoreController.applyVolumes: changeTrackVolume sets each part's channel volume
        plan.channels.forEachIndexed { i, ch -> synth.setChannelVolume(ch.toDouble(), plan.gains[i]) }
        synth.tickPosition = score.masterBars[first - 1].start
        synth.play()
        val stereo = capture.pull(bar.samples.size)
        synth.destroy()
        val screen = LoudnessMeter(44100.0, 2).apply { process(stereo) }.integratedLufs
        val dual = FloatArray(bar.samples.size * 2) { bar.samples[it / 2] }
        val here = LoudnessMeter(44100.0, 2).apply { process(dual) }.integratedLufs
        val screenPeak = stereo.maxOf { abs(it) }
        println("bars $first-$last: score screen %.2f LUFS, peak %.3f; bar render %.2f LUFS, peak %.3f".format(screen, screenPeak, here, bar.peak()))
        assertEquals("bars $first-$last: bar render vs score screen (LUFS)", screen, here, 1.0)
    }

    /** Collects what alphaTab's synth renders; the test pulls by triggering sample requests. */
    private class Capture : ISynthOutput {
        private val out = ArrayList<Float>()
        override val sampleRate: Double = 44100.0
        override val ready = Emitter()
        override val samplesPlayed: IEventEmitterOfT<Double> = object : IEventEmitterOfT<Double> {
            override fun on(value: (Double) -> Unit): () -> Unit = {}
            override fun off(value: (Double) -> Unit) {}
        }
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

        fun pull(frames: Int): FloatArray {
            var guard = 0
            while (out.size < frames * 2 && guard++ < 100_000) sampleRequest.trigger()
            return out.take(frames * 2).toFloatArray()
        }
    }

    private class Emitter : IEventEmitter {
        private val handlers = ArrayList<() -> Unit>()
        override fun on(value: () -> Unit): () -> Unit { handlers += value; return { off(value) } }
        override fun off(value: () -> Unit) { handlers -= value }
        fun trigger() { for (h in handlers.toList()) h() }
    }

    @Test
    fun subsetKeepsThePlayedPresetsOnly() {
        assumeTrue("no band SoundFont in data/sounds/band", sf2.isFile)
        // Solo cornet (bank 0, program 56) middle C, and the snare
        val uses = setOf(SoundFontSubset.Use(0, 56, 60), SoundFontSubset.Use(0, 0, 38, drums = true))
        val out = SoundFontSubset.build(sf2, uses, setOf(56, 57, 58, 60, 0))
        println("subset %d KB of %d MB".format(out.size shr 10, sf2.length() shr 20))
        assertTrue("a small part of the file", out.size < sf2.length() / 20)
        val b = ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(out.size - 8, b.getInt(4))
        // every preset but the two played is set aside, on a bank nothing selects
        val phdr = chunk(out, "phdr")
        val kept = (0 until phdr.capacity() / 38 - 1).map { p ->
            (phdr.getShort(p * 38 + 22).toInt() and 0xFFFF) to (phdr.getShort(p * 38 + 20).toInt() and 0xFFFF)
        }.filter { it.first != 1999 }
        assertEquals(setOf(0 to 56, 128 to 0), kept.toSet())
    }

    /** A pdta sub-chunk, found by walking the RIFF lists. */
    private fun chunk(sf: ByteArray, id: String): ByteBuffer {
        val b = ByteBuffer.wrap(sf).order(ByteOrder.LITTLE_ENDIAN)
        fun tag(at: Int) = String(sf, at, 4, Charsets.US_ASCII)
        var pos = 12
        while (pos < sf.size) {
            val size = b.getInt(pos + 4)
            if (tag(pos) == "LIST" && tag(pos + 8) == "pdta") {
                var p = pos + 12
                while (p < pos + 8 + size) {
                    val s = b.getInt(p + 4)
                    if (tag(p) == id) return ByteBuffer.wrap(sf.copyOfRange(p + 8, p + 8 + s)).order(ByteOrder.LITTLE_ENDIAN)
                    p += 8 + s + (s and 1)
                }
            }
            pos += 8 + size + (size and 1)
        }
        error("no $id")
    }
}
