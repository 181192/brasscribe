package no.brasscribe.play

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.score.BandSoundFontFile
import no.brasscribe.play.score.BarAudio
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * "Listen to this bar" with the band SoundFont on the phone: a few bars of a full band render from
 * the bars' samples only, not the whole SoundFont (which alphaTab would hold three times over).
 * Needs the band SoundFont in the APK (or sideloaded) and a band score pushed to
 * /data/local/tmp/brasscribe/band.musicxml (the golden arrangement); skipped without them.
 */
@RunWith(AndroidJUnit4::class)
class BarAudioMemoryTest {
    private val target get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun used(): Long { val rt = Runtime.getRuntime(); return rt.totalMemory() - rt.freeMemory() }

    private fun gc() { repeat(3) { Runtime.getRuntime().gc(); System.runFinalization(); Thread.sleep(100) } }

    /** Runs [block] with the used Java heap polled; the peak above the heap before it, in bytes. */
    private fun <T> peakHeap(block: () -> T): Pair<T, Long> {
        gc()
        val before = used()
        val peak = java.util.concurrent.atomic.AtomicLong(before)
        val running = java.util.concurrent.atomic.AtomicBoolean(true)
        val poll = Thread { while (running.get()) { peak.accumulateAndGet(used(), ::maxOf); Thread.sleep(2) } }.apply { start() }
        try {
            val r = block()
            return r to (maxOf(peak.get(), used()) - before)
        } finally {
            running.set(false)
            poll.join()
        }
    }

    @Test
    fun barsRenderFromTheirSamplesOnly() {
        val xml = File("/data/local/tmp/brasscribe/band.musicxml").takeIf { it.canRead() }?.readText()
        assumeTrue("no band score pushed to /data/local/tmp/brasscribe/band.musicxml", xml != null)
        val sf = BandSoundFontFile.resolve(target)
        assumeTrue("no band SoundFont bundled or sideloaded", sf != null)
        BarAudio.render(target, xml!!, 1, 1, sf) // warm up: classes, the parse's first run
        val rt = Runtime.getRuntime()
        // for scale: the score's parse alone, and the bars from the whole SoundFont
        val (_, parse) = peakHeap { alphaTab.importer.ScoreLoader.loadScoreFromBytes(alphaTab.core.ecmaScript.Uint8Array(xml.toByteArray().asUByteArray()), alphaTab.Settings()) }
        val (_, whole) = peakHeap { BarAudio.render(xml, 1, 4, null, sf, whole = true) { ByteArray(0) } }
        android.util.Log.i("BarAudio", "parse alone: Java heap peak +%d MB; bars 1-4 with the whole SoundFont: +%d MB".format(parse shr 20, whole shr 20))
        for ((first, last) in listOf(1 to 1, 1 to 4, 60 to 61)) {
            val t0 = System.nanoTime()
            val (audio, peak) = peakHeap { BarAudio.render(target, xml, first, last, sf) }
            val ms = (System.nanoTime() - t0) / 1_000_000
            android.util.Log.i("BarAudio", "bars %d-%d: %.1f s of audio in %d ms, Java heap peak +%d MB (max heap %d MB, SoundFont %d MB), peak %.3f"
                .format(first, last, audio!!.samples.size / 44100.0, ms, peak shr 20, rt.maxMemory() shr 20, sf!!.length() shr 20, audio.peak()))
            assertTrue("bars $first-$last sound", audio.peak() > 0.01f)
            // The whole SoundFont is the file's bytes, alphaTab's copy and the samples as floats; the
            // polled heap counts garbage not yet collected too (the parse's, the seek's).
            assertTrue("bars $first-$last: ${peak shr 20} MB of heap, ${whole shr 20} MB with the whole SoundFont", peak < whole / 2)
        }
    }

    /** Without the band SoundFont (a build without the sound pack) the bars play on alphaTab's General MIDI one. */
    @Test
    fun barsPlayOnGeneralMidiWithoutTheBandSoundFont() {
        val xml = File("/data/local/tmp/brasscribe/band.musicxml").takeIf { it.canRead() }?.readText()
            ?: InstrumentationRegistry.getInstrumentation().context.assets.open("old-hundredth/brass-band.musicxml").use { String(it.readBytes()) }
        val audio = BarAudio.render(target, xml, 1, 4, bandSoundFont = null)!!
        android.util.Log.i("BarAudio", "bars 1-4 on General MIDI: %.1f s, peak %.3f".format(audio.samples.size / 44100.0, audio.peak()))
        assertTrue("the bars sound", audio.peak() > 0.01f)
    }
}
