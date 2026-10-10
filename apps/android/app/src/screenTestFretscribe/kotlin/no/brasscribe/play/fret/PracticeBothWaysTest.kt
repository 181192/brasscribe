package no.brasscribe.play.fret

import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
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
        // The player is there once the recording is (it is looked for when the tab opens).
        waitForTag("fs-practice-play", 10_000)

        aWholeLineIsInView(label, tab)
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

    /** On its side the header scrolls with the page: once the player has scrolled up to it, a zoom leaves it in view. */
    @Test
    fun onItsSideTheHeaderScrolledToStaysThroughAZoom() {
        computer("bass-line-marks")
        turn(landscape = true)
        showTheTab()
        settle()
        // Scrolled up by hand, as a player does.
        rule.onNodeWithTag("fs-tab-scroll").performTouchInput { swipeDown() }
        settle()
        rule.onNodeWithTag("fs-tab-tuning").assertIsDisplayed()
        rule.onNodeWithTag("fs-tab-zoom-in").performClick()
        engraved()
        settle()
        rule.onNodeWithTag("fs-tab-tuning").assertIsDisplayed()
    }

    /** At open: a whole line of the tab is in the room the tab has on screen. */
    private fun aWholeLineIsInView(label: String, tab: TabView) {
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
    }

    /**
     * With Switch Access, or a service that only speaks, the phone is used by sight: on its side the page opens on its
     * first line as without them, a whole line of the tab in view.
     */
    @Test
    fun onItsSideWithSwitchAccessAWholeLineIsInView() {
        rule.runOnUiThread { container.assistiveOverride = true; container.touchExplorationOverride = false }
        try {
            computer("bass-line-marks")
            turn(landscape = true)
            val tab = showTheTab()
            settle()
            waitForTag("fs-practice-play", 10_000)
            aWholeLineIsInView("on-its-side-switch-access", tab)
        } finally {
            rule.runOnUiThread { container.assistiveOverride = null; container.touchExplorationOverride = null }
        }
    }

    /** With a screen reader explored by touch (TalkBack) the page opens at its top on its side too: the header is read first, in order. */
    @Test
    fun onItsSideWithAScreenReaderTheHeaderIsReadFirst() {
        rule.runOnUiThread { container.assistiveOverride = true; container.touchExplorationOverride = true }
        try {
            computer("bass-line-marks")
            turn(landscape = true)
            showTheTab()
            settle()
            rule.onNodeWithTag("fs-tab-tuning").assertIsDisplayed()
            rule.onNodeWithTag("fs-tab-marked").assertIsDisplayed()
            rule.onNode(androidx.compose.ui.test.isHeading() and androidx.compose.ui.test.hasText("Bass line")).assertExists()
        } finally {
            rule.runOnUiThread { container.assistiveOverride = null; container.touchExplorationOverride = null }
        }
    }

    @Test fun uprightAtTheOrdinarySize() = check("upright", landscape = false, scale = 1f)

    @Test fun uprightAt200PercentText() = check("upright-200", landscape = false, scale = 2f)

    @Test fun onItsSideAtTheOrdinarySize() = check("on-its-side", landscape = true, scale = 1f)

    @Test fun onItsSideAt200PercentText() = check("on-its-side-200", landscape = true, scale = 2f)
}
