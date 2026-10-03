package no.brasscribe.play.screen

import android.app.UiAutomation
import android.app.UiModeManager
import android.content.Context
import android.graphics.Bitmap
import android.view.KeyEvent
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.MainActivity
import org.junit.rules.TestRule
import java.io.File

typealias AppRule = AndroidComposeTestRule<ActivityScenarioRule<MainActivity>, MainActivity>

/**
 * What a screen test asks of the machine it runs on. This is a device's: the phone's own settings, set
 * through the shell, and real time. src/test has the same for the JVM.
 */
object ScreenDevice {
    /** False on a device. */
    const val JVM = false

    /** Whether what alphaTab engraves has its colours as the theme gave them: on a device it has (see the JVM's). */
    const val ENGRAVES_IN_COLOUR = true

    /** The phone itself, before the app is started on it: a device is what it is. */
    fun phone(): TestRule = TestRule { test, _ -> test }

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()

    private fun shell(command: String) {
        instrumentation.uiAutomation.executeShellCommand(command).close()
        Thread.sleep(400)
    }

    /** A file of apps/fixtures ("bass-line/tab.json"), which the test APK carries as assets; null when it is not there. */
    fun fixture(path: String): ByteArray? = runCatching { instrumentation.context.assets.open(path).use { it.readBytes() } }.getOrNull()

    /** The app in [tag]'s language ("en-GB", "nb-NO"), as after the phone's setting for it changed. */
    fun language(rule: AppRule, tag: String) {
        shell("cmd locale set-app-locales ${instrumentation.targetContext.packageName} --locales $tag")
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
    }

    /** The phone's text size: 2f is 200 %. */
    fun textSize(rule: AppRule, scale: Float) {
        shell("settings put system font_scale $scale")
        rule.waitUntil(10_000) { kotlin.math.abs(rule.activity.resources.configuration.fontScale - scale) < 0.05f }
        rule.waitForIdle()
    }

    /** The phone on its side, or upright again. */
    fun turn(rule: AppRule, sideways: Boolean) {
        instrumentation.uiAutomation.setRotation(if (sideways) UiAutomation.ROTATION_FREEZE_90 else UiAutomation.ROTATION_FREEZE_0)
        rule.waitUntil(10_000) {
            val metrics = rule.activity.resources.displayMetrics
            (metrics.widthPixels > metrics.heightPixels) == sideways
        }
        rule.waitForIdle()
    }

    /** The phone's own dark theme. */
    fun night(rule: AppRule, dark: Boolean) {
        shell("cmd uimode night ${if (dark) "yes" else "no"}")
        rule.waitForIdle()
    }

    /** The phone's contrast setting at its highest, or back to standard. False where the device does not take it. */
    fun highContrast(rule: AppRule, on: Boolean): Boolean {
        shell(if (on) "settings put secure contrast_level 1.0" else "settings delete secure contrast_level")
        val contrast = rule.activity.getSystemService(UiModeManager::class.java).contrast
        if (on && contrast < 0.5f) return false
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
        return true
    }

    /** A key pressed and let go on the keyboard. */
    fun key(rule: AppRule, code: Int, meta: Int = 0) {
        if (meta == 0) instrumentation.sendKeyDownUpSync(code)
        else for (action in listOf(KeyEvent.ACTION_DOWN, KeyEvent.ACTION_UP)) instrumentation.sendKeySync(KeyEvent(0, 0, action, code, 0, meta))
        rule.waitForIdle()
    }

    /** The whole screen as it is drawn now, every window of it. */
    fun screen(rule: AppRule): Bitmap {
        settle(rule)
        val shot = checkNotNull(instrumentation.uiAutomation.takeScreenshot()) { "no screenshot" }
        return shot.copy(Bitmap.Config.ARGB_8888, false)
    }

    /** The phone's Back. */
    fun back(rule: AppRule) {
        instrumentation.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        rule.waitForIdle()
    }

    /** A keyboard is in use from now on: touch mode ends, as with the first key pressed. */
    fun keyboard(rule: AppRule) {
        instrumentation.setInTouchMode(false)
        rule.waitForIdle()
    }

    /** The system's own sheet over the app (the share chooser) is closed. */
    fun closeSystemSheet(rule: AppRule) {
        Thread.sleep(1500)
        instrumentation.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        rule.waitForIdle()
    }

    /** A recording to open: [wav] written as [name]. The phone decodes it itself. */
    @Suppress("UNUSED_PARAMETER")
    fun recording(context: Context, name: String, wav: ByteArray, sampleRate: Int): File =
        File(context.cacheDir, name).apply { writeBytes(wav) }

    /** Waits until [condition] holds, for [ms] at most. */
    fun waitUntil(rule: AppRule, ms: Long, condition: () -> Boolean) = rule.waitUntil(ms) { condition() }

    /** Waits until [condition] holds where no screen is up. */
    fun waitWithoutScreen(ms: Long, condition: () -> Boolean) {
        val end = System.nanoTime() + ms * 1_000_000
        while (!condition()) {
            if (System.nanoTime() > end) throw AssertionError("not within $ms ms")
            Thread.sleep(20)
        }
        instrumentation.waitForIdleSync()
    }

    /** Lets the screen come to rest. */
    fun settle(rule: AppRule) {
        rule.waitForIdle()
        Thread.sleep(900)
        rule.waitForIdle()
    }

    /** Waits until the screen is at rest also where the app's other threads have a hand in it. */
    fun rest(rule: AppRule) {
        settle(rule)
        settle(rule)
    }

    /** [ms] of real time, for what runs by the clock on the wall (a recording that plays). */
    @Suppress("UNUSED_PARAMETER")
    fun elapse(rule: AppRule, ms: Long) = Thread.sleep(ms)

    /** A key held down: pressed, repeated [repeats] times as a held key is, and let go. */
    fun hold(rule: AppRule, code: Int, repeats: Int) {
        val down = android.os.SystemClock.uptimeMillis()
        for (again in 0..repeats) instrumentation.sendKeySync(KeyEvent(down, android.os.SystemClock.uptimeMillis(), KeyEvent.ACTION_DOWN, code, again))
        instrumentation.sendKeySync(KeyEvent(down, android.os.SystemClock.uptimeMillis(), KeyEvent.ACTION_UP, code, 0))
        rule.waitForIdle()
    }

    /** What the app announces to a screen reader, each to [heard], until the returned handle is closed. */
    @Suppress("UNUSED_PARAMETER")
    fun announcements(rule: AppRule, heard: (String) -> Unit): AutoCloseable {
        val automation = instrumentation.uiAutomation
        automation.setOnAccessibilityEventListener { event ->
            if (event.eventType == android.view.accessibility.AccessibilityEvent.TYPE_ANNOUNCEMENT) heard(event.text.joinToString(" "))
        }
        return AutoCloseable { automation.setOnAccessibilityEventListener(null) }
    }

    /** Frames the app has drawn since it started, as the system counts them. */
    @Suppress("UNUSED_PARAMETER")
    fun framesDrawn(rule: AppRule): Int {
        val out = android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand("dumpsys gfxinfo ${instrumentation.targetContext.packageName}"))
            .use { it.readBytes().decodeToString() }
        return Regex("""Total frames rendered: (\d+)""").find(out)!!.groupValues[1].toInt()
    }

    /** Frames drawn while nothing is touched for [ms]: a still screen draws none. */
    fun framesWhileStill(rule: AppRule, ms: Long = 4_000): Int {
        settle(rule)
        Thread.sleep(1_500)
        val before = framesDrawn(rule)
        Thread.sleep(ms)
        return framesDrawn(rule) - before
    }

    /** Lets [ms] pass. */
    @Suppress("UNUSED_PARAMETER")
    fun pass(rule: AppRule, ms: Long) = Thread.sleep(ms)

    /** The screenshots are the JVM run's (Roborazzi); a device takes none. */
    @Suppress("UNUSED_PARAMETER")
    fun shot(rule: AppRule, name: String) = rule.waitForIdle()

    /** The pictures of a flow's moments are the JVM run's too. */
    @Suppress("UNUSED_PARAMETER")
    fun picture(rule: AppRule, name: String) = rule.waitForIdle()

    /** Back to the phone as a test finds it. */
    fun reset(rule: AppRule) {
        shell("cmd locale set-app-locales ${instrumentation.targetContext.packageName} --locales en-GB")
        shell("settings put system font_scale 1.0")
        shell("settings delete secure contrast_level")
        shell("cmd uimode night no")
        instrumentation.uiAutomation.setRotation(UiAutomation.ROTATION_FREEZE_0)
        instrumentation.setInTouchMode(true)
    }
}
