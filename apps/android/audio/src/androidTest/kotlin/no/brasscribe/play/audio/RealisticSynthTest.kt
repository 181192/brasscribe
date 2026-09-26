package no.brasscribe.play.audio

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.math.abs

/**
 * Runs sfizz on the device without the audio output (offline render). Skips when the library was built
 * without sfizz. The SFZ-instrument case needs a sound pack pushed to the path given as the `sfz`
 * instrumentation argument (see README).
 */
@RunWith(AndroidJUnit4::class)
class RealisticSynthTest {
    private fun peak(frames: FloatArray) = frames.maxOf { abs(it) }

    @Test
    fun testToneRendersSound() {
        assumeTrue("built without sfizz", RealisticSynth.available)
        assertTrue(RealisticSynth.loadTestTone(0))
        RealisticSynth.noteOn(0, 69, 100)
        val out = RealisticSynth.renderOffline(48000 / 4)
        val p = peak(out)
        android.util.Log.i("RealisticSynthTest", "test tone peak %.4f, voices %d".format(p, RealisticSynth.activeVoices()))
        assertTrue("peak $p", p > 0.01f)
        RealisticSynth.allOff()
    }

    @Test
    fun scheduledNoteStartsOnItsFrame() {
        assumeTrue("built without sfizz", RealisticSynth.available)
        assertTrue(RealisticSynth.loadTestTone(2))
        RealisticSynth.allOff()
        RealisticSynth.renderOffline(512)
        // 0.1 s ahead at the offline rate (48 kHz): silence first, the tone from about frame 4800.
        RealisticSynth.noteAt(2, 72, 100, 0.1)
        val out = RealisticSynth.renderOffline(9600)
        val before = (0 until 4700).maxOf { abs(out[it * 2]) }
        val after = (4900 until 9600).maxOf { abs(out[it * 2]) }
        val first = (0 until 9600).first { abs(out[it * 2]) > 1e-4f }
        android.util.Log.i("RealisticSynthTest", "scheduled note: first sample at frame %d, peak before %.5f, after %.4f".format(first, before, after))
        assertTrue("silent before", before < 1e-4f)
        assertTrue("sounding after", after > 0.01f)
        RealisticSynth.allOff()
    }

    @Test
    fun cornetSoundPackRenders() {
        assumeTrue("built without sfizz", RealisticSynth.available)
        val path = InstrumentationRegistry.getArguments().getString("sfz")
        assumeTrue("no sfz argument", path != null && File(path).isFile)
        val t0 = System.nanoTime()
        assertTrue(RealisticSynth.load(1, File(path!!)))
        val loadMs = (System.nanoTime() - t0) / 1_000_000
        val regions = RealisticSynth.regions(1)
        RealisticSynth.noteOn(1, 60, 90)
        val out = RealisticSynth.renderOffline(48000 / 2)
        val p = peak(out)
        android.util.Log.i("RealisticSynthTest", "cornet sfz: %d regions, load %d ms, peak %.4f".format(regions, loadMs, p))
        assertTrue(regions > 10)
        assertTrue("peak $p", p > 0.01f)
        RealisticSynth.allOff()
    }
}
