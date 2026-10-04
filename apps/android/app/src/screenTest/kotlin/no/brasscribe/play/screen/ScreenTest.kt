package no.brasscribe.play.screen

import android.graphics.Bitmap
import android.view.KeyEvent
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
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

    /**
     * Opens [file] from Home, as the user does. Home is shown first: going there and opening the file in one step
     * can bring the screen it opens on back before Home was ever drawn, and that screen would keep what it
     * remembered from the last time it was shown.
     */
    protected fun openFromHome(file: File) {
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
        rule.runOnUiThread { vm.importUri(android.net.Uri.fromFile(file)) }
    }
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
            container.qrCamera = no.brasscribe.play.ui.PhoneQrCamera
            container.updateAppearance(Appearance.SYSTEM)
            vm.scores.value.forEach(vm::deleteEntry)
            vm.home()
        }
    }

    /**
     * Waits until the score on screen is a new one (not [before], the controller of the score shown before), is loaded,
     * and alphaTab has finished engraving it and painted what is in view: no render is on its way or under way, and no
     * part of the engraving in view waits for its picture. A fixed delay is not enough, as a setting that changes after
     * the first render (the title block, the stand's layout) engraves it again, and alphaTab does all of it on a thread
     * of its own: a new width is engraved again 25 ms later (by the clock on the wall), and the parts in view are
     * painted only after the render has finished, once the view has laid them out.
     */
    protected fun waitForEngravedScore(before: no.brasscribe.play.score.ScoreController? = null, ms: Long = 30_000) {
        try {
            waitUntil(ms) {
                val c = vm.scoreController
                c != null && c !== before && c.state.value.loaded && c.renders.value > 0 && !c.engraving.value &&
                    // (A width alphaTab has not engraved yet is engraved again once its pause after a change of size is over.)
                    c.view.api.container.width == c.view.api.renderer.width && onUi { AlphaTabSurface.painted(c.view, c.parts) }
            }
        } catch (e: AssertionError) {
            val c = vm.scoreController
            val state = if (c == null) "no score" else "new ${c !== before}, loaded ${c.state.value.loaded}, renders ${c.renders.value}, " +
                "engraving ${c.engraving.value}, width ${c.view.api.container.width} engraved at ${c.view.api.renderer.width}, " +
                "parts ${onUi { AlphaTabSurface.describe(c.view, c.parts) }}"
            throw AssertionError("no engraved score within $ms ms ($state)", e)
        }
    }

    private fun <T> onUi(read: () -> T): T {
        var out: Result<T>? = null
        rule.runOnUiThread { out = runCatching(read) }
        return out!!.getOrThrow()
    }

    /**
     * The pairing scanner open, the camera allowed, on a camera that shows [code] (a QR code's text) or, when it is
     * null, nothing that reads.
     */
    protected fun pairingScanner(code: String? = null) {
        ScreenDevice.allowCamera(rule)
        rule.runOnUiThread { container.qrCamera = ShownQrCode(code); vm.home(); vm.navigate(no.brasscribe.play.Screen.SETTINGS); vm.navigate(no.brasscribe.play.Screen.COMPANION) }
        rule.waitForIdle()
        rule.onNode(androidx.compose.ui.test.hasText(text(no.brasscribe.play.R.string.pair_scan))).performScrollTo().performClick()
        rule.waitForIdle()
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

    /**
     * Whether [node] is drawn only in part, cut by a box it is in that clips it. The text is measured inside the nearest
     * part that scrolls (or the root): what that part's viewport hides, where it has not been scrolled to, is not a cut,
     * while a box inside it that clips is, in view or not.
     */
    private fun cutByWhatItIsIn(node: SemanticsNode): Boolean {
        // Measured inside the nearest part that scrolls (below its viewport, where its content moves as it scrolls), or the root.
        val scroller = generateSequence(node.parent) { it.parent }
            .firstOrNull { it.config.contains(SemanticsProperties.VerticalScrollAxisRange) || it.config.contains(SemanticsProperties.HorizontalScrollAxisRange) }
        val holder = scroller?.layoutInfo ?: generateSequence(node.layoutInfo) { it.parentInfo }.last()
        val text = node.layoutInfo.coordinates
        val within = holder.coordinates
        if (!text.isAttached || !within.isAttached) return false
        val whole = within.localBoundingBoxOf(text, clipBounds = false)
        val shown = within.localBoundingBoxOf(text, clipBounds = true)
        return whole.width - shown.width > 1f || whole.height - shown.height > 1f
    }

    /** A control a finger can act on: what it says, and what it is. */
    data class Control(val words: String, val role: Role? = null) {
        override fun toString() = if (role != null) "$words ($role)" else words
    }

    private class Seen(val control: Control, val window: Int)

    /** Every actionable control seen during the last [tabThrough], before its first Tab and after each, by node id. */
    private val seenInRound = mutableMapOf<Int, Seen>()

    private fun windowOf(node: SemanticsNode): Int = generateSequence(node) { it.parent }.last().id

    private fun noteActionable() {
        for (n in actionable()) seenInRound.getOrPut(n.id) { Seen(Control(FocusOrder.words(n), n.config.getOrNull(SemanticsProperties.Role)), windowOf(n)) }
    }

    /**
     * The elements Tab reaches, in the order it reaches them, until it is back at the first. On the way it notes every
     * control a finger could act on, also those that Tab has scrolled out of view by the end, for [missedByTheKeyboard].
     */
    protected fun tabThrough(): List<SemanticsNode> {
        seenInRound.clear()
        noteActionable()
        val reached = mutableListOf<SemanticsNode>()
        repeat(120) {
            key(KeyEvent.KEYCODE_TAB)
            noteActionable()
            val now = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true)).fetchSemanticsNodes().lastOrNull() ?: return@repeat
            if (reached.any { it.id == now.id }) return reached
            reached += now
        }
        return reached
    }

    /** Every element a finger can act on (a click, a toggle, a choice) that is laid out and not turned off, in view or scrolled out of it. */
    protected fun actionable(): List<SemanticsNode> =
        rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.OnClick) and !SemanticsMatcher.keyIsDefined(SemanticsProperties.Disabled))
            .fetchSemanticsNodes().filter { it.layoutInfo.isPlaced && it.size.width > 0 && it.size.height > 0 }

    /**
     * What a finger can act on and Tab, going round the screen ([reached], from [tabThrough]), does not reach. Only the
     * window the keyboard is in counts (a dialog, and not the screen under it), as a finger can reach only that one too.
     */
    protected fun missedByTheKeyboard(reached: List<SemanticsNode>): List<Control> {
        val ids = reached.map { it.id }.toSet()
        val windows = reached.map(::windowOf).toSet()
        return seenInRound.filter { (id, seen) -> id !in ids && (windows.isEmpty() || seen.window in windows) }.values.map { it.control }
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
