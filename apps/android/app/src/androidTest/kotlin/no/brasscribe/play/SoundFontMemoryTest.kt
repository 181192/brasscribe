package no.brasscribe.play

import android.os.Debug
import android.os.SystemClock
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.score.BandSoundFontFile
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The band SoundFont is held once: after alphaTab has loaded it (on the first Play), nothing in Play keeps the file's
 * bytes (alphaTab keeps its own copy of the sample chunk). Needs the SoundFont sideloaded into the
 * app's files, sounds/brasscribe-band-mobile.sf2; skipped without it.
 */
@RunWith(AndroidJUnit4::class)
class SoundFontMemoryTest {
    @get:Rule
    val scenario = ActivityScenarioRule(MainActivity::class.java)

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: MainActivity
    private val vm get() = ViewModelProvider(activity)[PlayViewModel::class.java]

    @Before
    fun setUp() {
        scenario.scenario.onActivity { activity = it }
        (activity.application as PlayApplication).container.firstRunDone = true
    }

    private fun used(): Long { val rt = Runtime.getRuntime(); return rt.totalMemory() - rt.freeMemory() }

    private fun gc() { repeat(3) { Runtime.getRuntime().gc(); System.runFinalization(); Thread.sleep(100) } }

    @Test
    fun soundFontBytesAreDroppedOnceLoaded() {
        val sf = BandSoundFontFile.sideloaded(activity)
        assumeTrue("no band SoundFont sideloaded", sf != null)
        gc()
        val heapBefore = used()
        val nativeBefore = Debug.getNativeHeapAllocatedSize()
        val xml = instrumentation.context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }
        val file = File(activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        instrumentation.runOnMainSync { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        val end = SystemClock.uptimeMillis() + 60_000
        while (vm.scoreController?.state?.value?.loaded != true) {
            assertTrue("score loaded in time", SystemClock.uptimeMillis() < end)
            Thread.sleep(100)
        }
        // The band SoundFont loads with the first Play.
        instrumentation.runOnMainSync { vm.scoreController!!.togglePlay() }
        while (vm.scoreController?.state?.value?.bandSoundFont != true) {
            assertTrue("band SoundFont loaded in time", SystemClock.uptimeMillis() < end)
            Thread.sleep(100)
        }
        assertTrue("the load was seen", vm.scoreController!!.soundFontBytes != null)
        instrumentation.runOnMainSync { vm.scoreController!!.stop() }
        Thread.sleep(300)
        gc()
        val heapAfter = used()
        val nativeAfter = Debug.getNativeHeapAllocatedSize()
        android.util.Log.i("BrasscribePlay", "band SoundFont %s (%d MB): Java heap %d -> %d MB (file bytes %s); native %d -> %d MB"
            .format(sf!!.name, sf.length() shr 20, heapBefore shr 20, heapAfter shr 20,
                if (vm.scoreController!!.soundFontBytes?.get() != null) "still reachable" else "released", nativeBefore shr 20, nativeAfter shr 20))
        assertNull("Play keeps no copy of the SoundFont's bytes", vm.scoreController!!.soundFontBytes?.get())
        // What stays is alphaTab's own: its copy of the sample chunk (the file's size) and the samples
        // as floats (twice that), about three times the file. A copy of ours would make it four.
        assertTrue("alphaTab's share only (${(heapAfter - heapBefore) shr 20} MB for a ${sf.length() shr 20} MB file)",
            heapAfter - heapBefore < sf.length() * 7 / 2)
    }
}
