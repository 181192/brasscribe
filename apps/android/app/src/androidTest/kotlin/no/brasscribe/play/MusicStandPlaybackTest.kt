package no.brasscribe.play

import android.app.UiAutomation
import android.content.res.Configuration
import android.os.SystemClock
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The music stand while the music plays, in real time. A Compose test rule drives Compose on a test
 * clock that only moves when the main thread is idle, and alphaTab keeps the main thread busy while
 * it plays; so these tests use a plain activity and read the screen as TalkBack does, through the
 * accessibility tree. Assistive tech is simulated with AppContainer.assistiveOverride.
 */
@RunWith(AndroidJUnit4::class)
class MusicStandPlaybackTest {
    @get:Rule
    val scenario = ActivityScenarioRule(MainActivity::class.java)

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val automation get() = instrumentation.uiAutomation
    private lateinit var activity: MainActivity
    private val container get() = (activity.application as PlayApplication).container
    private val vm get() = ViewModelProvider(activity)[PlayViewModel::class.java]
    private val controller get() = vm.scoreController!!

    @Before
    fun setUp() {
        scenario.scenario.onActivity { activity = it }
        container.firstRunDone = true
        container.standFollow = true
        container.standKeepControls = false
        container.standHintShown = true
        container.assistiveOverride = false
        instrumentation.runOnMainSync { vm.home() }
    }

    @After
    fun tearDown() {
        instrumentation.runOnMainSync {
            container.assistiveOverride = null
            vm.scoreController?.let { if (it.state.value.playing) it.togglePlay() }
        }
        automation.setRotation(UiAutomation.ROTATION_FREEZE_0)
        instrumentation.setInTouchMode(true)
    }

    private fun waitFor(what: String, ms: Long = 20_000, condition: () -> Boolean) {
        val end = SystemClock.uptimeMillis() + ms
        while (!condition()) {
            if (SystemClock.uptimeMillis() > end) throw AssertionError("timed out: $what; on screen: ${texts()}")
            Thread.sleep(100)
        }
    }

    /** Nodes whose text or description contains [text] (Compose does not answer findAccessibilityNodeInfosByText). */
    private fun nodes(text: String): List<AccessibilityNodeInfo> {
        val out = ArrayList<AccessibilityNodeInfo>()
        fun walk(n: AccessibilityNodeInfo?) {
            n ?: return
            if ((n.text ?: n.contentDescription)?.contains(text) == true) out += n
            for (i in 0 until n.childCount) walk(n.getChild(i))
        }
        walk(automation.rootInActiveWindow)
        return out
    }

    private fun onScreen(text: String) = nodes(text).isNotEmpty()

    private fun texts(): List<String> {
        val out = ArrayList<String>()
        fun walk(n: AccessibilityNodeInfo?) {
            n ?: return
            (n.text ?: n.contentDescription)?.let { out += it.toString() }
            for (i in 0 until n.childCount) walk(n.getChild(i))
        }
        walk(automation.rootInActiveWindow)
        return out
    }

    private fun click(text: String) {
        var n: AccessibilityNodeInfo? = nodes(text).firstOrNull() ?: throw AssertionError("no '$text' on screen")
        while (n != null && !n.isClickable) n = n.parent
        assertTrue("'$text' is clickable", n?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true)
    }

    /** A tap on the music, as a finger, in the upper part of the screen (clear of the layer). */
    private fun tapMusic() {
        val dm = activity.resources.displayMetrics
        val x = dm.widthPixels / 2f
        val y = dm.heightPixels * 0.35f
        val t = SystemClock.uptimeMillis()
        for ((action, at) in listOf(MotionEvent.ACTION_DOWN to t, MotionEvent.ACTION_UP to t + 60)) {
            val e = MotionEvent.obtain(t, at, action, x, y, 0).apply { source = InputDevice.SOURCE_TOUCHSCREEN }
            automation.injectInputEvent(e, true)
            e.recycle()
        }
        Thread.sleep(300)
    }

    private fun key(code: Int) {
        val t = SystemClock.uptimeMillis()
        automation.injectInputEvent(KeyEvent(t, t, KeyEvent.ACTION_DOWN, code, 0), true)
        automation.injectInputEvent(KeyEvent(t, t + 30, KeyEvent.ACTION_UP, code, 0), true)
        Thread.sleep(300)
    }

    /** "Old Hundredth" (apps/fixtures, in the test APK only) on the stand, slowed so its twelve bars last. */
    private fun openStand() {
        val xml = instrumentation.context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }
        val file = File(activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        instrumentation.runOnMainSync { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitFor("the score") { vm.scoreController?.state?.value?.loaded == true && onScreen("Music stand") }
        instrumentation.runOnMainSync { controller.setSpeed(50) }
        click("Music stand")
        waitFor("the stand") { onScreen("Leave") && onScreen("page 1 of") }
    }

    /** The activity in front, read on the main thread without waiting for it to be idle (it never is while playing). */
    private fun resumedActivity(): android.app.Activity? {
        var a: android.app.Activity? = null
        instrumentation.runOnMainSync {
            a = androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance()
                .getActivitiesInStage(androidx.test.runner.lifecycle.Stage.RESUMED).firstOrNull()
        }
        return a
    }

    private fun play() {
        instrumentation.runOnMainSync { controller.togglePlay() }
        waitFor("playing") { controller.state.value.playing }
    }

    @Test
    fun rotationKeepsThePlaybackAndThePlace() {
        openStand()
        play()
        waitFor("bar 2") { controller.state.value.bar >= 2 }
        val before = controller.state.value.bar
        val player = controller

        automation.setRotation(UiAutomation.ROTATION_FREEZE_90)
        waitFor("landscape") { activity.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE }
        Thread.sleep(2_000)
        // The same activity, the same alphaTab view and player, still playing, and not back at bar 1.
        assertSame(activity, resumedActivity())
        assertSame(player, vm.scoreController)
        assertTrue("still playing after the turn", controller.state.value.playing)
        assertTrue("bar ${controller.state.value.bar} after bar $before", controller.state.value.bar >= before)
        waitFor("the stand on its side, one line") { onScreen(" · bar ") && onScreen("Leave") }

        automation.setRotation(UiAutomation.ROTATION_FREEZE_0)
        waitFor("portrait") { activity.resources.configuration.orientation == Configuration.ORIENTATION_PORTRAIT }
        Thread.sleep(2_000)
        assertSame(activity, resumedActivity())
        assertTrue("still playing after turning back", controller.state.value.playing)
        assertTrue(controller.state.value.bar >= before)
        assertTrue(onScreen("Leave"))
    }

    @Test
    fun theControlsHideOnlyWithoutAssistiveTechOrAKeyboard() {
        openStand()
        // Paused: the layer stays.
        Thread.sleep(5_000)
        assertTrue("paused: the layer stays", onScreen("Speed 50%"))

        // Playing, without assistive tech: it hides after 4 s and leaves the accessibility tree;
        // Leave and the position stay.
        play()
        waitFor("the layer hides", 8_000) { !onScreen("Speed 50%") }
        assertTrue("Leave stays", onScreen("Leave"))
        assertTrue("the position stays", onScreen("page 1 of"))
        // A tap on the music brings it back, and it goes again 4 s later.
        tapMusic()
        waitFor("a tap shows the layer", 3_000) { onScreen("Speed 50%") }

        // A screen reader or switch access: it never hides by itself, and a tap does not hide it.
        instrumentation.runOnMainSync { container.assistiveOverride = true }
        tapMusic()
        Thread.sleep(6_000)
        assertTrue("the layer stays with assistive tech", onScreen("Speed 50%"))
        instrumentation.runOnMainSync { container.assistiveOverride = false }
        waitFor("it hides again without", 8_000) { !onScreen("Speed 50%") }

        // A Bluetooth page turner is a keyboard: its keys turn the page (each press is announced, a
        // turn or "first/last page") and leave the layer hidden.
        for (k in listOf(KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_PAGE_UP)) {
            instrumentation.runOnMainSync { vm.status.value = null }
            key(k)
            var said: String? = null
            waitFor("the page key reached the stand", 3_000) { instrumentation.runOnMainSync { said = vm.status.value?.text }; said != null }
            assertTrue("a page message: $said", said!!.contains("page", ignoreCase = true))
            assertTrue("a page key leaves the layer hidden", !onScreen("Speed 50%"))
        }
        // With the layer up, page keys don't keep it: it still hides 4 s after the last touch.
        tapMusic()
        waitFor("a tap shows the layer", 3_000) { onScreen("Speed 50%") }
        key(KeyEvent.KEYCODE_PAGE_DOWN)
        Thread.sleep(2_000)
        key(KeyEvent.KEYCODE_PAGE_UP)
        waitFor("page keys don't restart the 4 s timer", 2_500) { !onScreen("Speed 50%") }
        // Tab shows the layer, and it stays until the next touch.
        key(KeyEvent.KEYCODE_TAB)
        waitFor("Tab shows the layer", 3_000) { onScreen("Speed 50%") }
        Thread.sleep(6_000)
        assertTrue("the layer stays after Tab", onScreen("Speed 50%"))
        assertTrue("still playing", controller.state.value.playing)
    }
}
