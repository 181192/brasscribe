package no.brasscribe.play.screen

import android.app.Activity
import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.media.MediaFormat
import android.net.Uri
import android.os.Looper
import android.provider.Settings
import android.view.Display
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.view.inspector.WindowInspector
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.platform.app.InstrumentationRegistry
import com.github.takahirom.roborazzi.captureScreenRoboImage
import no.brasscribe.play.MainActivity
import org.junit.Assume
import org.junit.rules.TestRule
import org.junit.runners.model.Statement
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import com.google.android.apps.common.testing.accessibility.framework.Parameters
import com.google.android.apps.common.testing.accessibility.framework.utils.contrast.BitmapImage
import org.robolectric.shadows.ShadowBuild
import org.robolectric.shadows.ShadowMediaExtractor
import org.robolectric.shadows.ShadowWindowManagerGlobal
import org.robolectric.shadows.util.DataSource
import java.io.File
import java.lang.ref.WeakReference
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

    /**
     * Whether what alphaTab engraves has its colours as the theme gave them. Not on the JVM: alphaSkia's build
     * for a desktop draws into a bitmap whose red and blue are the other way round from Android's, and alphaTab
     * copies it as it is. Ink and the lines' grey are the same either way; a coloured numeral is checked on a device.
     */
    const val ENGRAVES_IN_COLOUR = false

    /**
     * The phone itself, before the app is started on it: a status bar and gesture navigation, as a phone has
     * (Robolectric's own phone has neither until asked; its class for them is not public yet).
     */
    fun phone(): TestRule = TestRule { test, _ ->
        object : Statement() {
            override fun evaluate() {
                // The screens are the app's with its native core (the host build of it here): without it they would be
                // other screens (no What do you play?, no Your instrument, no arranger), so they are not tested then.
                val core = File(System.getProperty("jna.library.path").orEmpty()).listFiles().orEmpty().any { it.name.startsWith("libbrasscribe_ffi.") }
                Assume.assumeTrue("the host build of the core is missing: scripts/core-artifacts.sh ensure host (or cargo build --release -p brasscribe-ffi in core/)", core)
                val ui = Class.forName("org.robolectric.shadows.SystemUi")
                fun member(name: String) = ui.getDeclaredField(name).apply { isAccessible = true }.get(null)
                val display = ui.getDeclaredMethod("systemUiForDefaultDisplay").apply { isAccessible = true }.invoke(null)
                ui.declaredMethods.first { it.name == "setBehavior" }.apply { isAccessible = true }
                    .invoke(display, member("STANDARD_STATUS_BAR"), member("GESTURAL_NAVIGATION"))
                // Nothing moves by itself: the phone's animations are off, as they are on the emulators the device tests
                // run on, so a score is put at its place at once and a screenshot does not catch it on its way.
                Settings.Global.putFloat(RuntimeEnvironment.getApplication().contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 0f)
                // A service is listening to the accessibility tree, as the test's own connection does on a device, so Compose
                // builds that tree and the accessibility checks have something to check. It is not a screen reader: touch
                // exploration stays off, as on a device under test.
                val accessibility = RuntimeEnvironment.getApplication().getSystemService(android.view.accessibility.AccessibilityManager::class.java)
                shadowOf(accessibility).setEnabled(true)
                shadowOf(accessibility).setEnabledAccessibilityServiceList(listOf(android.accessibilityservice.AccessibilityServiceInfo()))
                test.evaluate()
            }
        }
    }

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
        else rule.runOnUiThread {
            // A change the activity takes itself (its manifest's configChanges): told to it and to its windows, as the phone does.
            val app = RuntimeEnvironment.getApplication().resources
            val config = Configuration(app.configuration)
            val activity = rule.activity
            @Suppress("DEPRECATION")
            activity.resources.updateConfiguration(config, app.displayMetrics)
            (Activity::class.java.getDeclaredField("mCurrentConfig").apply { isAccessible = true }.get(activity) as Configuration).setTo(config)
            activity.onConfigurationChanged(config)
            for (window in WindowInspector.getGlobalWindowViews()) {
                val root = View::class.java.getMethod("getViewRootImpl").invoke(window) ?: continue
                root.javaClass.getMethod("updateConfiguration", Int::class.javaPrimitiveType).invoke(root, Display.INVALID_DISPLAY)
                window.requestLayout()
            }
        }
        rule.waitForIdle()
    }

    /**
     * The Accessibility Test Framework's checks on the whole screen, with a picture of it for the contrast checks;
     * an error fails the test. (The framework leaves Compose's content alone on a phone that says it is
     * Robolectric's, so for the checks it says it is not: what Roborazzi does for its own checks.)
     */
    fun checkAccessibility(rule: AppRule) {
        rule.waitForIdle()
        val picture = screen(rule)
        rule.runOnUiThread {
            val fingerprint = android.os.Build.FINGERPRINT
            ShadowBuild.setFingerprint("brasscribe-jvm")
            try {
                val window = frontWindow()
                ScreenAccessibility.validator()
                    .setParameters(Parameters().apply { putScreenCapture(BitmapImage(picture)) })
                    .check(window)
            } finally {
                ShadowBuild.setFingerprint(fingerprint)
            }
        }
    }

    /** A key pressed and let go on the keyboard. As on a phone, the first key ends touch mode, so focus can be seen and moved. */
    fun key(rule: AppRule, code: Int, meta: Int = 0) {
        rule.runOnUiThread {
            // The window in front takes the keys: a dialog's, when one is open.
            val window = frontWindow()
            val now = android.os.SystemClock.uptimeMillis()
            val down = KeyEvent(now, now, KeyEvent.ACTION_DOWN, code, 0, meta)
            // As Android's window does (ViewRootImpl): a key ends touch mode, and a navigation key that gave the
            // window its first focus by that is used up.
            val navigation = down.hasNoModifiers() && code in NAVIGATION_KEYS
            val entered = (navigation || down.isPrintingKey) && window.isInTouchMode && touchMode(window, false)
            if (!(navigation && entered) && !window.dispatchKeyEvent(down)) moveFocus(window, code, meta)
            window.dispatchKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_UP, code, 0, meta))
        }
        rule.waitForIdle()
    }

    /**
     * The window in front: the last one opened that takes input. The phone's window manager gives it the window
     * focus when it opens and takes it from the one behind; here that is done for it.
     */
    private fun frontWindow(): View {
        val windows = WindowInspector.getGlobalWindowViews()
        val top = windows.last { v ->
            (v.layoutParams as? WindowManager.LayoutParams)?.let { it.flags and WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE == 0 } ?: true
        }
        if (front?.get() !== top) {
            front = WeakReference(top)
            for (w in windows) if (w !== top && w.hasWindowFocus()) windowFocus(w, false)
            if (!top.hasWindowFocus()) windowFocus(top, true)
        }
        return top
    }

    private var front: WeakReference<View>? = null

    private fun windowFocus(window: View, focused: Boolean) {
        val root = View::class.java.getMethod("getViewRootImpl").invoke(window)
        val change = root?.javaClass?.methods?.firstOrNull { it.name == "windowFocusChanged" && it.parameterTypes.contentEquals(arrayOf(Boolean::class.javaPrimitiveType)) }
        if (change != null) change.invoke(root, focused) else window.dispatchWindowFocusChanged(focused)
        shadowOf(Looper.getMainLooper()).idle()
    }

    /** The phone's Back. */
    fun back(rule: AppRule) {
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        rule.waitForIdle()
    }

    /** A keyboard is in use from now on: touch mode ends, as with the first key pressed. */
    fun keyboard(rule: AppRule) {
        rule.runOnUiThread { touchMode(frontWindow(), false) }
        rule.waitForIdle()
    }

    /** The system's own sheet over the app (the share chooser) is closed. Here none is shown: the request for it is only noted. */
    @Suppress("UNUSED_PARAMETER")
    fun closeSystemSheet(rule: AppRule) = Unit

    /** A Tab or an arrow nothing took moves the focus: what Android's window does with it (ViewRootImpl's focus navigation). */
    private fun moveFocus(root: View, code: Int, meta: Int) {
        val direction = when (code) {
            KeyEvent.KEYCODE_TAB -> if (meta and KeyEvent.META_SHIFT_ON != 0) View.FOCUS_BACKWARD else View.FOCUS_FORWARD
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
    private fun touchMode(window: View, touch: Boolean): Boolean {
        // For the windows opened from now on (a dialog, a menu), as the phone's one touch mode is for all its windows.
        ShadowWindowManagerGlobal::class.java.getDeclaredMethod("setInTouchMode", Boolean::class.javaPrimitiveType)
            .apply { isAccessible = true }.invoke(null, touch)
        val root = View::class.java.getMethod("getViewRootImpl").invoke(window) ?: return false
        return root.javaClass.getDeclaredMethod("ensureTouchMode", Boolean::class.javaPrimitiveType).apply { isAccessible = true }.invoke(root, touch) as Boolean
    }

    private val NAVIGATION_KEYS = setOf(
        KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_CENTER,
        KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_MOVE_HOME, KeyEvent.KEYCODE_MOVE_END,
        KeyEvent.KEYCODE_TAB, KeyEvent.KEYCODE_SPACE, KeyEvent.KEYCODE_ENTER,
    )

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
        val end = System.nanoTime() + ms * slower * 1_000_000
        var last = System.nanoTime()
        while (true) {
            rule.waitForIdle()
            frontWindow()
            if (condition()) return
            if (System.nanoTime() > end) throw AssertionError("not within $ms ms")
            Thread.sleep(5)
            // The app's clock goes as fast as the wall's, and no faster: while a test waits for work on another thread
            // (a file read, the fixture computer's answer), the app's own timers (a heartbeat, a "not found" after two
            // minutes, a status that clears) must not run ahead and fire as they never would on a phone in that time.
            val now = System.nanoTime()
            pass(rule, ((now - last) / 1_000_000).coerceAtLeast(1))
            last = now
        }
    }

    /** Waits until [condition] holds where no screen is up: the main thread's work is done meanwhile. */
    fun waitWithoutScreen(ms: Long, condition: () -> Boolean) {
        val end = System.nanoTime() + ms * 1_000_000
        while (!condition()) {
            if (System.nanoTime() > end) throw AssertionError("not within $ms ms")
            shadowOf(Looper.getMainLooper()).idleFor(20, TimeUnit.MILLISECONDS)
            Thread.sleep(2)
        }
        shadowOf(Looper.getMainLooper()).idle()
    }

    /**
     * A recording the app has put somewhere of its own (a kept recording, for one): its sound track is told to
     * Android's stand-in media classes, as [recording] does for the file it writes. [wav] is a 16-bit mono WAV.
     */
    fun knowsTheSoundOf(context: Context, wav: File) {
        val bytes = wav.readBytes()
        val rate = java.nio.ByteBuffer.wrap(bytes, 24, 4).order(java.nio.ByteOrder.LITTLE_ENDIAN).int
        val pcm = bytes.copyOfRange(44, bytes.size)
        val format = MediaFormat.createAudioFormat("audio/raw", rate, 1).apply { setLong(MediaFormat.KEY_DURATION, pcm.size / 2 * 1_000_000L / rate) }
        ShadowMediaExtractor.addTrack(DataSource.toDataSource(context, Uri.fromFile(wav), null), format, pcm)
    }

    /** Lets the screen come to rest: a second of the app's time, with its frames. */
    fun settle(rule: AppRule) {
        repeat(20) { rule.waitForIdle(); pass(rule, 50) }
        rule.waitForIdle()
    }

    /**
     * Waits until the screen is at rest also where the app's other threads have a hand in it (a score is
     * engraved on one, its sounds are loaded on another, a list's details are read on a third): the app's time
     * passes and they get on, until what is drawn has stayed the same for a while. For a screenshot that is to
     * be the same from run to run.
     */
    fun rest(rule: AppRule) {
        val end = System.nanoTime() + 6_000_000_000
        var drawn = 0
        var same = 0
        while (same < 4 && System.nanoTime() < end) {
            repeat(4) { rule.waitForIdle(); pass(rule, 50) }
            Thread.sleep(40)
            rule.waitForIdle()
            val now = pixels()
            if (now == drawn) same++ else { same = 0; drawn = now }
        }
    }

    private fun pixels(): Int {
        val shot = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot() ?: return 0
        val all = IntArray(shot.width * shot.height).also { shot.getPixels(it, 0, shot.width, 0, 0, shot.width, shot.height) }
        shot.recycle()
        return all.contentHashCode()
    }

    /** [ms] of real time, for what runs by the clock on the wall (a recording that plays), with the app's time beside it. */
    fun elapse(rule: AppRule, ms: Long) {
        val end = System.nanoTime() + ms * 1_000_000
        while (System.nanoTime() < end) {
            pass(rule, 10)
            Thread.sleep(10)
        }
        rule.waitForIdle()
    }

    /** A key held down: pressed, repeated [repeats] times as a held key is, and let go. */
    fun hold(rule: AppRule, code: Int, repeats: Int) {
        rule.runOnUiThread {
            val window = frontWindow()
            val down = android.os.SystemClock.uptimeMillis()
            for (again in 0..repeats) window.dispatchKeyEvent(KeyEvent(down, android.os.SystemClock.uptimeMillis(), KeyEvent.ACTION_DOWN, code, again))
            window.dispatchKeyEvent(KeyEvent(down, android.os.SystemClock.uptimeMillis(), KeyEvent.ACTION_UP, code, 0))
        }
        rule.waitForIdle()
    }

    /** What the app announces to a screen reader, each to [heard], until the returned handle is closed. */
    fun announcements(rule: AppRule, heard: (String) -> Unit): AutoCloseable {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.setOnAccessibilityEventListener { event ->
            if (event.eventType == android.view.accessibility.AccessibilityEvent.TYPE_ANNOUNCEMENT) heard(event.text.joinToString(" "))
        }
        return AutoCloseable { automation.setOnAccessibilityEventListener(null) }
    }

    /** Frames the app has drawn: counted by a device's system only. */
    @Suppress("UNUSED_PARAMETER")
    fun framesDrawn(rule: AppRule): Int = throw UnsupportedOperationException("frames are counted on a device")

    @Suppress("UNUSED_PARAMETER")
    fun framesWhileStill(rule: AppRule, ms: Long = 4_000): Int = throw UnsupportedOperationException("frames are counted on a device")

    /** How much longer a wait may take on a CI runner, whose two cores the app's threads share with the build. */
    private val slower = if (System.getenv("CI") != null) 3 else 1

    /** Lets [ms] of the app's time pass: Android's clock (its handlers and animations) and Compose's own (a delay in an effect). */
    fun pass(rule: AppRule, ms: Long) {
        shadowOf(Looper.getMainLooper()).idleFor(ms, TimeUnit.MILLISECONDS)
        rule.mainClock.advanceTimeBy(ms)
    }

    /** The whole screen as it is drawn now, every window of it. */
    fun screen(rule: AppRule): Bitmap {
        rule.waitForIdle()
        val shot = checkNotNull(InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()) { "no screenshot" }
        return shot.copy(Bitmap.Config.ARGB_8888, false)
    }

    /**
     * The screen at rest, as the screenshot [name] ("fretscribe/home-light") of the screen catalogue: recorded or
     * compared when Roborazzi is asked to (apps/android/scripts/screenshots.sh), and nothing otherwise.
     */
    fun shot(rule: AppRule, name: String) {
        rule.waitForIdle()
        captureScreenRoboImage("build/outputs/roborazzi/$name.png")
    }

    /**
     * The screen as it is at this moment of a flow, as the picture [name], to look at: kept under
     * build/outputs/screen-pictures while screenshots are recorded, and never compared (a moment of a flow is
     * not the same from run to run).
     */
    fun picture(rule: AppRule, name: String) {
        if (System.getProperty("roborazzi.test.record") != "true") return
        val file = File("build/outputs/screen-pictures/$name.png").apply { parentFile?.mkdirs() }
        file.outputStream().use { screen(rule).compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    /** Back to the phone as a test finds it. */
    fun reset(rule: AppRule) {
        RuntimeEnvironment.setFontScale(1f)
        Locale.setDefault(Locale.UK)
        ShadowMediaExtractor.reset()
        DataSource.reset()
    }
}
