package no.brasscribe.play.screen

import android.graphics.Bitmap
import android.view.KeyEvent
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.text.TextLayoutResult
import androidx.lifecycle.ViewModelProvider
import no.brasscribe.play.Appearance
import no.brasscribe.play.MainActivity
import no.brasscribe.play.PlayApplication
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.engine.FixtureSource
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.rules.RuleChain
import org.junit.rules.TestRule
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A test of the app's screens that runs both on the JVM (with the unit tests, under Robolectric) and on a
 * device (with the instrumented tests): the real activity and view model, a fixture computer, and the
 * accessibility checks on every action. What the two runs do differently is in [ScreenDevice].
 */
abstract class ScreenTest {
    // (The rule whose effects run on a StandardTestDispatcher: an effect's coroutine that comes back from Dispatchers.IO
    // is resumed on the main thread, as on a phone, and not on the worker it came back on, where Compose would recompose.)
    val rule: AppRule = createAndroidComposeRule<MainActivity>()

    /** The phone first, then the app on it. */
    @get:Rule
    val onThePhone: TestRule = RuleChain.outerRule(ScreenDevice.phone()).around(rule)

    protected val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]
    protected val container get() = (rule.activity.application as PlayApplication).container

    @Before
    fun startClean() {
        rule.enableAccessibilityChecks(ScreenAccessibility.validator())
        rule.activity.getSharedPreferences("engine", 0).edit().clear().commit()
        // (On the JVM the app's time follows the wall's: the fixture computer's stages are kept short.)
        if (ScreenDevice.JVM) container.fixtureStageSeconds = 0.2
        rule.runOnUiThread {
            container.firstRunDone = true
            vm.scores.value.forEach(vm::deleteEntry)
            vm.home()
        }
        rule.waitForIdle()
    }

    /** The accessibility checks on the screen a test ends on, so every screen test runs them at least once. */
    @After
    fun checkTheLastScreen() {
        if (checksTheLastScreen) checkAccessibility()
    }

    /** False for a test whose last screen is not the app's own (a view put up by the test itself). */
    protected open val checksTheLastScreen: Boolean = true

    @After
    fun leaveClean() {
        ScreenDevice.reset(rule)
        rule.runOnUiThread {
            container.fixtureSource = null
            container.updateAppearance(Appearance.SYSTEM)
            vm.scores.value.forEach(vm::deleteEntry)
            vm.home()
        }
    }

    protected fun text(id: Int, vararg args: Any): String = rule.activity.getString(id, *args)

    protected fun language(tag: String) = ScreenDevice.language(rule, tag)

    protected fun textSize(scale: Float) = ScreenDevice.textSize(rule, scale)

    protected fun key(code: Int, meta: Int = 0) = ScreenDevice.key(rule, code, meta)

    /** The whole screen as it is drawn now. */
    protected fun screen(): Bitmap = ScreenDevice.screen(rule)

    /** Where this test's pictures go. */
    protected open val shots: String = "screens"

    /** A picture of the screen at this moment, to look at (see [ScreenDevice.picture]). */
    protected fun shot(name: String) = ScreenDevice.picture(rule, "$shots/$name")

    /**
     * The accessibility checks on what is on the screen now. On a device they also run on every action a test
     * performs; on the JVM where a test calls this (and on every screen of the catalogue).
     */
    protected fun checkAccessibility() = ScreenDevice.checkAccessibility(rule)

    /** Waits until [condition] holds; the app's time passes meanwhile. */
    protected fun waitUntil(ms: Long = 5_000, condition: () -> Boolean) = ScreenDevice.waitUntil(rule, ms, condition)

    /** Waits until the screen is at rest also where the app's other threads have a hand in it (see [ScreenDevice.rest]). */
    protected fun rest() = ScreenDevice.rest(rule)

    /** Lets [ms] of the app's time pass. */
    protected fun pass(ms: Long) = ScreenDevice.pass(rule, ms)

    /** Lets the screen come to rest: what was started is drawn, and nothing more is on its way. */
    protected fun settle() = ScreenDevice.settle(rule)

    protected fun waitForTag(tag: String, ms: Long = 60_000) =
        waitUntil(ms) { rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }

    /** The fixture computer: the files of [folder] in apps/fixtures, each changed by [change] on the way when it answers one. */
    protected fun computer(folder: String, change: (name: String, bytes: ByteArray?) -> ByteArray? = { _, bytes -> bytes }) {
        container.fixtureSource = FixtureSource { name -> change(name, ScreenDevice.fixture("$folder/$name")) }
    }

    /** Two seconds of a low E as a WAV file: a recording to open. */
    protected fun recording(name: String = "Bass line.wav"): File {
        val rate = 22_050
        val samples = ShortArray(rate * 2) { i -> (Math.sin(2 * Math.PI * 82.4 * i / rate) * 9000).toInt().toShort() }
        val data = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN).also { b -> samples.forEach(b::putShort) }.array()
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
            .putInt(rate).putInt(rate * 2).putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size).array()
        return ScreenDevice.recording(rule.activity, name, header + data, rate)
    }

    /** Every text now on screen. */
    protected fun shown(): String = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text), useUnmergedTree = true)
        .fetchSemanticsNodes().flatMap { it.config[SemanticsProperties.Text] }.joinToString(" | ") { it.text }

    /**
     * Every text on screen is drawn whole: no line is cut off or ellipsized, and none is cut by what it is in (a
     * text that runs out of a box that clips). A text that a part that scrolls has partly moved out of view is not cut.
     */
    protected fun assertNoTextIsClipped(except: Set<String> = emptySet()) {
        val clipped = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.GetTextLayoutResult), useUnmergedTree = true)
            .fetchSemanticsNodes().mapNotNull { node ->
                // (A text that is laid out and then left out, as a control with no room in its row is, is not on the screen.)
                if (!node.layoutInfo.isPlaced) return@mapNotNull null
                val layouts = mutableListOf<TextLayoutResult>()
                node.config.getOrNull(SemanticsActions.GetTextLayoutResult)?.action?.invoke(layouts)
                val l = layouts.firstOrNull() ?: return@mapNotNull null
                val cut = l.didOverflowHeight || (0 until l.lineCount).any(l::isLineEllipsized) ||
                    (!l.layoutInput.softWrap && l.multiParagraph.maxIntrinsicWidth > l.size.width + 1f) || cutByWhatItIsIn(node)
                l.layoutInput.text.text.takeIf { cut }
            }
        assertEquals("clipped text", emptyList<String>(), clipped.filter { it !in except })
    }

    /** Whether [node] is drawn only in part, cut by an ancestor that clips it, and not because a part that scrolls moved it. */
    private fun cutByWhatItIsIn(node: SemanticsNode): Boolean {
        val whole = Rect(node.positionInWindow.x, node.positionInWindow.y, node.positionInWindow.x + node.size.width, node.positionInWindow.y + node.size.height)
        val shown = node.boundsInWindow
        if (shown.isEmpty || (whole.width - shown.width <= 1f && whole.height - shown.height <= 1f)) return false
        val scrolls = generateSequence(node.parent) { it.parent }.any {
            it.config.contains(SemanticsProperties.VerticalScrollAxisRange) || it.config.contains(SemanticsProperties.HorizontalScrollAxisRange)
        }
        return !scrolls
    }

    /** The elements Tab reaches, in the order it reaches them, until it is back at the first. */
    protected fun tabThrough(): List<SemanticsNode> {
        val reached = mutableListOf<SemanticsNode>()
        repeat(120) {
            key(KeyEvent.KEYCODE_TAB)
            val now = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true)).fetchSemanticsNodes().lastOrNull() ?: return@repeat
            if (reached.any { it.id == now.id }) return reached
            reached += now
        }
        return reached
    }

    /** Every element a finger can act on (a click, a toggle, a choice) that is on the screen and not turned off. */
    protected fun actionable(): List<SemanticsNode> =
        rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.OnClick) and !SemanticsMatcher.keyIsDefined(SemanticsProperties.Disabled))
            .fetchSemanticsNodes().filter { it.layoutInfo.isPlaced && !it.boundsInWindow.isEmpty }

    /**
     * What a finger can act on and Tab, going round the screen ([reached]), does not reach: their words. Only the window
     * the keyboard is in counts (a dialog, and not the screen under it), as a finger can reach only that one too.
     */
    protected fun missedByTheKeyboard(reached: List<SemanticsNode>): List<String> {
        fun windowOf(node: SemanticsNode): Int = generateSequence(node) { it.parent }.last().id
        val ids = reached.map { it.id }.toSet()
        val windows = reached.map(::windowOf).toSet()
        return actionable().filter { it.id !in ids && (windows.isEmpty() || windowOf(it) in windows) }.map(FocusOrder::words)
    }

    /** What the element with the keyboard's focus says: its texts and its name. */
    protected fun focusedWords(): String = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true))
        .fetchSemanticsNodes().lastOrNull()?.config?.let { c ->
            (c.getOrNull(SemanticsProperties.Text).orEmpty().map { it.text } + c.getOrNull(SemanticsProperties.ContentDescription).orEmpty()).joinToString(" ")
        }.orEmpty()

    /** Tab until the focused element says [words]; fails when the keyboard never gets there. */
    protected fun tabTo(words: String, seen: MutableSet<String> = mutableSetOf()) {
        repeat(12) {
            if (focusedWords().contains(words)) return
            key(KeyEvent.KEYCODE_TAB)
            seen += focusedWords()
        }
        assertTrue("the keyboard never reached \"$words\"; it reached $seen", focusedWords().contains(words))
    }
}
