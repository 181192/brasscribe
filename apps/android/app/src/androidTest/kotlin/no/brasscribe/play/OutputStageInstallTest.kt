package no.brasscribe.play

import android.os.SystemClock
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.score.BandSoundFontFile
import no.brasscribe.play.score.StagedSynthOutput
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import no.brasscribe.play.test.DeviceOnly

/**
 * The app's own score player plays through the shared output stage: after a score opens and the band
 * SoundFont loads, alphaTab's synth output in the view is the staged one, and it stays staged after
 * playing and stopping.
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class OutputStageInstallTest {
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

    private fun installed(): Boolean {
        var ok = false
        instrumentation.runOnMainSync { ok = vm.scoreController?.let { StagedSynthOutput.isInstalled(it.view.api) } == true }
        return ok
    }

    @Test
    fun scorePlaybackGoesThroughTheStage() {
        assumeTrue("no band SoundFont bundled", BandSoundFontFile.bundled(activity) || BandSoundFontFile.sideloaded(activity) != null)
        val xml = instrumentation.context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }
        val file = File(activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        instrumentation.runOnMainSync { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        val end = SystemClock.uptimeMillis() + 60_000
        while (vm.scoreController?.state?.value?.loaded != true) {
            assertTrue("score loaded in time", SystemClock.uptimeMillis() < end)
            Thread.sleep(100)
        }
        assertTrue("alphaTab's output is staged once the score is open", installed())
        // The band SoundFont loads with the first Play.
        instrumentation.runOnMainSync { vm.scoreController!!.togglePlay() }
        while (vm.scoreController?.state?.value?.bandSoundFont != true || vm.scoreController?.state?.value?.playing != true) {
            assertTrue("band SoundFont loaded and playing in time", SystemClock.uptimeMillis() < end)
            Thread.sleep(100)
        }
        assertTrue("staged with the band SoundFont in", installed())
        Thread.sleep(500)
        instrumentation.runOnMainSync { vm.scoreController!!.stop() }
        Thread.sleep(300)
        assertTrue("still staged after play and stop", installed())
    }
}
