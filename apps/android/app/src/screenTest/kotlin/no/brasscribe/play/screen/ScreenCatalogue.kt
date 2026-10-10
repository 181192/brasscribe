package no.brasscribe.play.screen

import android.view.KeyEvent
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import no.brasscribe.play.Appearance
import no.brasscribe.play.test.Slow
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.categories.Category

/**
 * Every screen of an app, one after the other, as a phone can show it: light, dark, high contrast, 200 %
 * text, on its side, and in bokmål. Each is opened, checked by the accessibility checks, and kept as a
 * screenshot ([shots]/<screen>-<how>.png) that a later run compares with. At 200 % no text may be cut off
 * or ellipsized, and with the keyboard the focus goes through a screen in the order it is read.
 *
 * An app's catalogue names its [screens]: a new screen is added there, and is then in every one of these.
 */
@Category(Slow::class)
abstract class ScreenCatalogue : ScreenTest() {
    /**
     * A screen: its [name] in the screenshots, and how to get to it from Home. [steady] is false for a screen
     * that shows a moment of something under way (its screenshot would differ from run to run, so none is kept).
     * [ownOrder] says why the keyboard does not go through this screen in the order it is read, for the few
     * where that is so (the keyboard's order is then not compared; it must still reach everything). [cutAtLargeText] are
     * texts known to be cut off at 200 %, and [notReached] controls the keyboard is known not to reach, each with the
     * issue that says so: the lists are for what is waiting to be fixed, and an entry goes when its issue is closed.
     */
    class Entry(
        val name: String, val steady: Boolean = true, val ownOrder: String? = null,
        val cutAtLargeText: Set<String> = emptySet(), val notReached: Set<Control> = emptySet(), val open: () -> Unit,
    )

    /**
     * What a finger can act on that is not for the keyboard, on any screen: the dimmed screen behind a sheet, which
     * a screen reader can tap to close it, where the keyboard closes the sheet with Escape or Back.
     */
    private val notForTheKeyboard = setOf("Close sheet")

    protected abstract val screens: List<Entry>

    private companion object {
        /** No release's version, so it cannot be taken for one. */
        const val FIXED_VERSION = "0.0.0"
    }

    /**
     * About shows the app's version, which every release changes. The catalogue shows a fixed one in its place,
     * so a release leaves the pictures of About as they were. ([leaveClean] puts the app's own back.)
     */
    @Before
    fun showAFixedVersion() {
        container.shownVersion = FIXED_VERSION
    }

    /**
     * Back to Home, with nothing of the screen before still under way: a screen that shows the notes being written
     * down leaves that work running, and its result would otherwise arrive on the next screen and take it away.
     */
    private fun fromHome() {
        waitUntil(30_000) { !vm.transcribe.value.running }
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
    }

    /** Shows every screen in turn and does [check] on it; all that failed are reported together. */
    private fun onEveryScreen(how: String, check: (Entry) -> Unit = {}) {
        val failed = mutableListOf<String>()
        for (screen in screens) {
            try {
                fromHome()
                screen.open()
                // (A moment of something under way is looked at as it is: time that passes would end it.)
                if (screen.steady) settle() else rule.waitForIdle()
                checkAccessibility()
                check(screen)
                if (screen.steady) ScreenDevice.shot(rule, "$shots/${screen.name}-$how")
            } catch (e: Throwable) {
                failed += "${screen.name} ($how): ${e.javaClass.simpleName}: ${e.message.orEmpty().lines().take(12).joinToString(" / ")}"
                // What went wrong is easier to see than to read.
                runCatching { ScreenDevice.picture(rule, "$shots/failed/${screen.name}-$how") }
            }
        }
        assertEquals("screens with something wrong, $how", "", failed.joinToString("\n"))
    }

    @Test
    fun light() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        onEveryScreen("light")
    }

    @Test
    fun dark() {
        rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
        onEveryScreen("dark")
    }

    @Test
    fun highContrast() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        assumeTrue("this device does not take the contrast setting", ScreenDevice.highContrast(rule, true))
        onEveryScreen("high-contrast")
    }

    @Test
    fun at200PercentText() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        textSize(2f)
        onEveryScreen("text-200") { assertNoTextIsClipped(except = it.cutAtLargeText) }
    }

    @Test
    fun onItsSide() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        ScreenDevice.turn(rule, sideways = true)
        onEveryScreen("landscape")
    }

    @Test
    fun inBokmal() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        language("nb-NO")
        onEveryScreen("nb") { assertNoTextIsClipped() }
    }

    @Test
    fun theKeyboardGoesThroughEachScreenInTheOrderItIsRead() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val failed = mutableListOf<String>()
        for (screen in screens) {
            try {
                fromHome()
                screen.open()
                settle()
                val all = tabThrough()
                // Whatever its order, the keyboard reaches everything a finger can act on.
                missedByTheKeyboard(all).filter { it.words !in notForTheKeyboard && it !in screen.notReached }.takeIf { it.isNotEmpty() }?.let { failed += "${screen.name}: the keyboard never reaches $it; it goes ${all.map(FocusOrder::words)}" }
                if (screen.ownOrder != null) continue
                val round = all
                val read = FocusOrder.reading(round, scrolling())
                // (Where on the screen the first Tab lands depends on what was touched last: the round is what is compared.)
                val reached = round.indexOfFirst { it.id == read.firstOrNull()?.id }.let { at -> if (at <= 0) round else round.drop(at) + round.take(at) }
                if (reached.map { it.id } != read.map { it.id }) {
                    failed += "${screen.name}: the keyboard goes ${reached.map(FocusOrder::words)}, and it is read ${read.map(FocusOrder::words)}"
                }
            } catch (e: Throwable) {
                failed += "${screen.name}: ${e.javaClass.simpleName}: ${e.message.orEmpty().lines().take(6).joinToString(" / ")}"
            }
        }
        assertEquals("screens the keyboard does not go through in reading order", "", failed.joinToString("\n"))
    }

    /** The part of the screen that scrolls: the largest of them, when there are several. */
    private fun scrolling(): SemanticsNode? = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.VerticalScrollAxisRange))
        .fetchSemanticsNodes().maxByOrNull { it.boundsInWindow.width * it.boundsInWindow.height }

}

/** The order a screen is read in, for the elements the keyboard reaches. */
object FocusOrder {
    private fun within(node: SemanticsNode, scroll: SemanticsNode?): Boolean =
        scroll != null && generateSequence(node.parent) { it.parent }.any { it.id == scroll.id }

    /** Where the element is, whole: also the part of it that is scrolled out of view. */
    private fun place(node: SemanticsNode): Rect =
        Rect(node.positionInWindow.x, node.positionInWindow.y, node.positionInWindow.x + node.size.width, node.positionInWindow.y + node.size.height)

    /**
     * [nodes] as they are read: what is above the part that scrolls first (the top bar, and what is pinned over
     * the content), then what is in it, then what is docked under it (a screen's one primary button); each
     * from top to bottom, and from the start of a row to its end.
     */
    fun reading(nodes: List<SemanticsNode>, scroll: SemanticsNode?): List<SemanticsNode> {
        val (inside, outside) = nodes.partition { within(it, scroll) }
        val (docked, above) = outside.partition { scroll != null && place(it).top >= scroll.boundsInWindow.bottom - 1f }
        return byPlace(above) + byPlace(inside) + byPlace(docked)
    }

    /** Rows from the top; two elements that share most of their height are in one row, read from its start. */
    private fun byPlace(nodes: List<SemanticsNode>): List<SemanticsNode> {
        val rows = mutableListOf<MutableList<SemanticsNode>>()
        for (node in nodes.sortedBy { place(it).top }) {
            val row = rows.lastOrNull()?.takeIf { r ->
                val a = place(r.first()); val b = place(node)
                minOf(a.bottom, b.bottom) - maxOf(a.top, b.top) > 0.5f * minOf(a.height, b.height)
            }
            if (row != null) row += node else rows += mutableListOf(node)
        }
        return rows.flatMap { row -> row.sortedBy { place(it).left } }
    }

    fun words(node: SemanticsNode): String =
        (node.config.getOrNull(SemanticsProperties.ContentDescription).orEmpty() + node.config.getOrNull(SemanticsProperties.Text).orEmpty().map { it.text })
            .firstOrNull() ?: node.config.getOrNull(SemanticsProperties.TestTag) ?: "#${node.id}"
}
