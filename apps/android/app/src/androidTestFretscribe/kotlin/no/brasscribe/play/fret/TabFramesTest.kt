package no.brasscribe.play.fret

import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.Appearance
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import no.brasscribe.play.test.DeviceOnly

/**
 * What the tab view costs a phone, as its system counts the frames: a still screen draws none, and flings
 * down a long song are drawn on time. A device's own: the JVM run has no display to count frames on.
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class TabFramesTest : TabScreenTest() {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()

    private fun shell(cmd: String) {
        instrumentation.uiAutomation.executeShellCommand(cmd).close()
        Thread.sleep(400)
    }

    /** Frames the app has drawn since it started, as the system counts them. */
    private fun framesDrawn(): Int {
        val out = android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand("dumpsys gfxinfo $PACKAGE")).use { it.readBytes().decodeToString() }
        return Regex("""Total frames rendered: (\d+)""").find(out)!!.groupValues[1].toInt()
    }

    /** Frames drawn while nothing is touched for [ms]: a still screen draws none. */
    private fun framesWhileStill(ms: Long = 4_000): Int {
        settle()
        Thread.sleep(1_500)
        val before = framesDrawn()
        Thread.sleep(ms)
        return framesDrawn() - before
    }

    @Test
    fun theScreenIsStillWhenNothingMoves() {
        computer("bass-line-marks")
        var tab = showTheTab()
        fun still(what: String): Int {
            val engravings = TabScreenProbe.view!!.engravings
            val frames = framesWhileStill()
            android.util.Log.i("TabFramesTest", "still, $what: $frames frames, ${TabScreenProbe.view!!.engravings - engravings} engravings")
            return frames
        }
        val results = LinkedHashMap<String, Int>()
        results["first shown"] = still("first shown")
        // The counter counts: a fling draws frames.
        val beforeFling = framesDrawn()
        shell("input swipe 540 1800 540 700 150")
        val drawn = framesDrawn() - beforeFling
        android.util.Log.i("TabFramesTest", "a fling drew $drawn frames")
        assertTrue("a fling draws frames ($drawn)", drawn > 5)
        results["after a fling down the page"] = still("after a fling down the page")
        repeat(6) { shell("input swipe 540 1800 540 500 80") }
        results["at the end of the page"] = still("at the end of the page")
        turn(landscape = true)
        tab = engraved()
        results["in landscape"] = still("in landscape")
        shell("input swipe 1200 900 1200 300 150")
        results["in landscape after a fling"] = still("in landscape after a fling")
        repeat(8) { shell("input swipe 1200 900 1200 200 80") }
        results["in landscape at the end of the page"] = still("in landscape at the end of the page")
        turn(landscape = false)
        tab = engraved()
        results["back in portrait"] = still("back in portrait")
        shell("input keyevent KEYCODE_HOME")
        Thread.sleep(1500)
        shell("am start -n $PACKAGE/no.brasscribe.play.MainActivity")
        Thread.sleep(2500)
        results["after leaving the app and coming back"] = still("after leaving the app and coming back")
        shell("input swipe 540 900 540 1900 100")
        results["then a swipe at the top"] = still("then a swipe at the top")
        shell("input swipe 540 1500 540 900 300")
        results["then a slow drag"] = still("then a slow drag")
        shell("input swipe 540 900 540 1900 100")
        shell("input swipe 540 900 540 1900 100")
        results["after swipes at the top"] = still("after swipes at the top")
        rule.onNodeWithTag("fs-tab-tuning").performClick()
        waitForTag("fs-show-tab")
        rule.onNodeWithTag("fs-show-tab").performClick()
        tab = engraved()
        shell("input swipe 540 900 540 1900 100")
        results["after Check the song and back, and a swipe at the top"] = still("after Check the song and back, and a swipe at the top")
        assertEquals("frames drawn in four seconds of nothing moving", results.mapValues { 0 }, results.mapValues { if (it.value <= 2) 0 else it.value })
    }

    @Test
    fun flingsDownALongSongAreDrawnOnTime() {
        longSong()
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val started = System.currentTimeMillis()
        val tab = showTheTab()
        val e = tab.engraving.value!!
        assertEquals(224, e.barsPerLine.sum())
        rule.onNodeWithTag("fs-tab-marked").assertTextEquals("28 notes marked ? · Check them")
        // Flings down the page, counted by the system: frames drawn, and how many of them were late.
        shell("dumpsys gfxinfo $PACKAGE reset")
        repeat(12) { shell("input swipe 540 1900 540 500 60") }
        settle()
        val stats = android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand("dumpsys gfxinfo $PACKAGE")).use { it.readBytes().decodeToString() }
        fun stat(label: String) = Regex("""$label: ([^\n]+)""").find(stats)?.groupValues?.get(1)?.trim().orEmpty()
        val frames = stat("Total frames rendered").toInt()
        val janky = Regex("""Janky frames: (\d+)""").find(stats)!!.groupValues[1].toInt()
        android.util.Log.i("TabFramesTest", "long song: ${e.lines.size} lines, page ${e.height} px, shown ${System.currentTimeMillis() - started} ms after the recording was opened; " +
            "12 flings: $frames frames, $janky late, 50th ${stat("50th percentile")}, 90th ${stat("90th percentile")}, 95th ${stat("95th percentile")}, 99th ${stat("99th percentile")}")
        assertTrue("flings draw frames ($frames)", frames > 60)
        assertTrue("most frames are on time ($janky of $frames late)", janky * 2 < frames)
        repeat(20) { shell("input swipe 540 1900 540 500 60") }
        assertTrue("still at the end of a long song", framesWhileStill() <= 2)
    }

    private companion object {
        const val PACKAGE = "no.fretscribe.play"
    }
}
