package no.brasscribe.play.screen

import android.content.Context
import android.media.MediaFormat
import android.net.Uri
import android.os.Looper
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.view.inspector.WindowInspector
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.test.ext.junit.rules.ActivityScenarioRule
import com.github.takahirom.roborazzi.captureScreenRoboImage
import no.brasscribe.play.MainActivity
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.android.controller.ActivityController
import org.robolectric.shadows.ShadowMediaExtractor
import org.robolectric.shadows.util.DataSource
import java.io.File
import java.util.Locale
import java.util.concurrent.TimeUnit

typealias AppRule = AndroidComposeTestRule<ActivityScenarioRule<MainActivity>, MainActivity>

/**
 * What a screen test asks of the machine it runs on. This is the JVM's: Robolectric's Android, with the
 * settings of a phone given as resource qualifiers, the clock moved by the test, and the screenshots taken
 * by Roborazzi. src/androidTest has the same for a device.
 */
object ScreenDevice {
    /** True on the JVM: nothing here needs a device. */
    const val JVM = true

    private val fixtures = File(checkNotNull(System.getProperty("brasscribe.fixtures")) { "brasscribe.fixtures is not set (app/build.gradle.kts)" })

    /** A file of apps/fixtures ("bass-line/tab.json"); null when it is not there. */
    fun fixture(path: String): ByteArray? = File(fixtures, path).takeIf { it.isFile }?.readBytes()

    /** The app in [tag]'s language ("en-GB", "nb-NO"), as after the phone's setting for it changed. */
    fun language(rule: AppRule, tag: String) {
        val (language, region) = tag.split('-').let { it[0] to it.getOrNull(1) }
        // (The app's own locale becomes the process's on a phone.)
        Locale.setDefault(Locale.forLanguageTag(tag))
        qualifiers(rule, "+" + language + region?.let { "-r$it" }.orEmpty(), restart = true)
    }

    /** The phone's text size: 2f is 200 %. */
    fun textSize(rule: AppRule, scale: Float) {
        if (RuntimeEnvironment.getFontScale() == scale) return
        RuntimeEnvironment.setFontScale(scale)
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
    }

    /** The phone on its side, or upright again. The activity takes the turn itself, as its manifest says. */
    fun turn(rule: AppRule, sideways: Boolean) = qualifiers(rule, if (sideways) "+land" else "+port", restart = false)

    /** The phone's own dark theme. */
    fun night(rule: AppRule, dark: Boolean) = qualifiers(rule, if (dark) "+night" else "+notnight", restart = false)

    /** The phone's contrast setting at its highest, or back to standard. False where the device does not take it. */
    fun highContrast(rule: AppRule, on: Boolean): Boolean {
        val manager = rule.activity.getSystemService(android.app.UiModeManager::class.java)
        shadowOf(manager).setContrast(if (on) 1f else 0f)
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
        return true
    }

    private fun qualifiers(rule: AppRule, qualifiers: String, restart: Boolean) {
        RuntimeEnvironment.setQualifiers(qualifiers)
        if (restart) rule.activityRule.scenario.recreate()
        else rule.runOnUiThread { ActivityController.of(rule.activity).configurationChange(RuntimeEnvironment.getApplication().resources.configuration) }
        rule.waitForIdle()
    }

    /** A key pressed and let go on the keyboard. As on a phone, the first key ends touch mode, so focus can be seen and moved. */
    fun key(rule: AppRule, code: Int) {
        rule.runOnUiThread {
            // The window in front takes the keys: a dialog's, when one is open.
            val window = WindowInspector.getGlobalWindowViews().last { v ->
                (v.layoutParams as? WindowManager.LayoutParams)?.let { it.flags and WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE == 0 } ?: true
            }
            if (!window.hasWindowFocus()) window.dispatchWindowFocusChanged(true)
            touchMode(window, false)
            val now = android.os.SystemClock.uptimeMillis()
            if (!window.dispatchKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_DOWN, code, 0))) moveFocus(window, code)
            window.dispatchKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_UP, code, 0))
        }
        rule.waitForIdle()
    }

    /** A Tab or an arrow nothing took moves the focus: what Android's window does with it (ViewRootImpl's focus navigation). */
    private fun moveFocus(root: View, code: Int) {
        val direction = when (code) {
            KeyEvent.KEYCODE_TAB -> View.FOCUS_FORWARD
            KeyEvent.KEYCODE_DPAD_LEFT -> View.FOCUS_LEFT
            KeyEvent.KEYCODE_DPAD_RIGHT -> View.FOCUS_RIGHT
            KeyEvent.KEYCODE_DPAD_UP -> View.FOCUS_UP
            KeyEvent.KEYCODE_DPAD_DOWN -> View.FOCUS_DOWN
            else -> return
        }
        val focused = root.findFocus()
        if (focused == null) {
            root.restoreDefaultFocus()
            return
        }
        val next = focused.focusSearch(direction)
        if (next != null && next !== focused && next.requestFocus(direction)) return
        root.dispatchUnhandledMove(focused, direction)
    }

    /** What the window does itself when a key or a finger arrives: Android's own call, which a test has no public way to. */
    private fun touchMode(window: View, touch: Boolean) {
        val root = View::class.java.getMethod("getViewRootImpl").invoke(window) ?: return
        root.javaClass.getDeclaredMethod("ensureTouchMode", Boolean::class.javaPrimitiveType).apply { isAccessible = true }.invoke(root, touch)
    }

    /**
     * A recording to open: [wav] (16-bit mono PCM in a WAV file) written as [name]. Android's media classes
     * are stand-ins here, so the file's sound track is told to them: the phone's own decoding is a device's to test.
     */
    fun recording(context: Context, name: String, wav: ByteArray, sampleRate: Int): File {
        val file = File(context.cacheDir, name).apply { writeBytes(wav) }
        val pcm = wav.copyOfRange(44, wav.size)
        val format = MediaFormat.createAudioFormat("audio/raw", sampleRate, 1).apply {
            setLong(MediaFormat.KEY_DURATION, pcm.size / 2 * 1_000_000L / sampleRate)
        }
        // The import reads the picked file, then its own copy of it.
        for (f in listOf(file, File(File(context.cacheDir, "takes"), name))) {
            ShadowMediaExtractor.addTrack(DataSource.toDataSource(context, Uri.fromFile(f), null), format, pcm)
        }
        return file
    }

    /**
     * Waits until [condition] holds, for [ms] at most. The JVM's clock stands still until a test moves it, so
     * the app's time is passed here (in steps, as fast as the machine goes), while the app's own threads get on.
     */
    fun waitUntil(rule: AppRule, ms: Long, condition: () -> Boolean) {
        val end = System.nanoTime() + ms * 1_000_000
        while (true) {
            rule.waitForIdle()
            if (condition()) return
            if (System.nanoTime() > end) throw AssertionError("not within $ms ms")
            pass(50)
            Thread.sleep(2)
        }
    }

    /** Lets the screen come to rest: a second of the app's time, with its frames. */
    fun settle(rule: AppRule) {
        repeat(20) { rule.waitForIdle(); pass(50) }
        rule.waitForIdle()
    }

    /** Lets [ms] of the app's time pass. */
    fun pass(ms: Long) {
        shadowOf(Looper.getMainLooper()).idleFor(ms, TimeUnit.MILLISECONDS)
    }

    /** The screen as it is now, as the screenshot [name] ("fretscribe/home-light"): recorded or compared when Roborazzi is asked to. */
    fun shot(rule: AppRule, name: String) {
        rule.waitForIdle()
        captureScreenRoboImage("src/screenshots/$name.png")
    }

    /** Back to the phone as a test finds it. */
    fun reset(rule: AppRule) {
        RuntimeEnvironment.setFontScale(1f)
        Locale.setDefault(Locale.UK)
        ShadowMediaExtractor.reset()
        DataSource.reset()
    }
}
