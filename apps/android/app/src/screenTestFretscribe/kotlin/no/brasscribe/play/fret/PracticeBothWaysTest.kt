package no.brasscribe.play.fret

import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.Appearance
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Practice is the same on a phone held upright and on its side, at the ordinary text size and at 200 %: when the tab
 * opens a whole line of it is in view, and every control of practice and of the tab is there, whole and at least
 * 48 dp, also what scrolls with the page (the tuning, the "?" line).
 */
@RunWith(AndroidJUnit4::class)
class PracticeBothWaysTest : TabScreenTest() {
    private val controls = listOf("fs-practice-play", "fs-practice-start", "fs-practice-previous", "fs-practice-next",
        "fs-practice-slower", "fs-practice-faster", "fs-practice-repeat", "fs-tab-zoom-out", "fs-tab-zoom-in")
    private val onThePage = listOf("fs-tab-tuning", "fs-tab-marked")

    private fun check(label: String, landscape: Boolean, scale: Float) {
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        textSize(scale)
        turn(landscape)
        val tab = showTheTab()
        settle()

        // At open: a whole line of the tab is in the room the tab has on screen.
        val e = tab.engraving.value!!
        var page = 0
        rule.runOnUiThread { page = tab.pageScrolled }
        val room = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow
        val drawn = rule.onNodeWithTag("fs-tab").fetchSemanticsNode().boundsInWindow
        val whole = e.lines.count { line ->
            val top = drawn.top + line.top - page
            val bottom = drawn.top + line.bottom - page
            top >= room.top - 2 && bottom <= room.bottom + 2
        }
        assertTrue("$label: a whole line of the tab is in view when it opens ($whole; the tab's room ${room.top}–${room.bottom}, the page at ${drawn.top} scrolled $page)", whole >= 1)
        shot("practice-$label")

        // Every control: shown whole, at least 48 dp.
        for (tag in controls) {
            rule.onNodeWithTag(tag, useUnmergedTree = true).assertIsDisplayed().assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
            val b = rule.onNodeWithTag(tag, useUnmergedTree = true).fetchSemanticsNode().boundsInWindow
            val window = rule.onNodeWithTag("fs-practice").fetchSemanticsNode().boundsInWindow
            if (tag.startsWith("fs-practice")) assertTrue("$label: $tag is whole in the player ($b in $window)", b.top >= window.top - 1 && b.bottom <= window.bottom + 1)
        }
        // Pinned above the tab, or the top of the page a scroll up away.
        for (tag in onThePage) {
            val node = rule.onNodeWithTag(tag)
            if (runCatching { node.assertIsDisplayed() }.isFailure) node.performScrollTo()
            node.assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        }
        assertNoTextIsClipped()
        checkAccessibility()
    }

    @Test fun uprightAtTheOrdinarySize() = check("upright", landscape = false, scale = 1f)

    @Test fun uprightAt200PercentText() = check("upright-200", landscape = false, scale = 2f)

    @Test fun onItsSideAtTheOrdinarySize() = check("on-its-side", landscape = true, scale = 1f)

    @Test fun onItsSideAt200PercentText() = check("on-its-side-200", landscape = true, scale = 2f)
}
