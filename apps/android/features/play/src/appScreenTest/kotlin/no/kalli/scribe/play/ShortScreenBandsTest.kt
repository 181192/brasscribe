package no.kalli.scribe.play

import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The actions under a flow screen are docked while they leave the content room. On a short screen, where they would
 * take more than their share of the height, they come after the content and scroll with it. A problem with two
 * buttons is the case here, in both apps (the screen is shared).
 */
@RunWith(AndroidJUnit4::class)
class ShortScreenBandsTest : ScreenTest() {
    @After
    fun clean() {
        ScreenDevice.turn(rule, sideways = false)
        rule.runOnUiThread { vm.home() }
    }

    private fun aProblemWithTwoButtons() {
        rule.runOnUiThread { vm.home(); vm.showProblem(Problem.OPEN_FAILED) }
        settle()
        rule.onNodeWithText(text(R.string.back_home)).assertExists()
    }

    private fun primary(): SemanticsNode = rule.onNodeWithTag("problem-primary", useUnmergedTree = true).fetchSemanticsNode()

    /** Whether [node] is in a part of the screen that scrolls (one with somewhere to scroll to). */
    private fun scrolls(node: SemanticsNode): Boolean =
        generateSequence(node.parent) { it.parent }.any { (it.config.getOrNull(SemanticsProperties.VerticalScrollAxisRange)?.maxValue?.invoke() ?: 0f) > 0f }

    /** Down to the screen's bottom edge the page is its own colour: the navigation bar's strip is not another's. */
    private fun thePageGoesToTheBottomEdge() {
        // (A device draws its own handle or buttons there.)
        if (!ScreenDevice.JVM) return
        val picture = screen()
        // (The window's own size: after a turn the JVM's picture of the screen keeps the size it had.)
        val window = rule.activity.window.decorView
        val width = minOf(window.width, picture.width)
        val height = minOf(window.height, picture.height)
        // (The page's colour is taken at the left margin, half way down: nothing is drawn there on this screen.)
        val page = picture.getPixel(2, height / 2)
        for (x in listOf(2, width / 4, width / 2, width - 3)) for (up in 1..8) {
            assertEquals("the colour $up px above the bottom edge, $x px in", Integer.toHexString(page), Integer.toHexString(picture.getPixel(x, height - up)))
        }
    }

    @Test
    fun onAPhoneOnItsSideTwoButtonsScrollWithTheContent() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        aProblemWithTwoButtons()
        shot("problem-two-buttons-small-landscape")
        assertTrue("the buttons are in the part that scrolls", scrolls(primary()))
        thePageGoesToTheBottomEdge()
    }

    @Test
    fun onAPhoneUprightTwoButtonsAreDocked() {
        aProblemWithTwoButtons()
        assertFalse("the buttons are docked, outside the part that scrolls", scrolls(primary()))
        val button = primary()
        assertEquals("the docked button is in view, whole", button.size.height.toFloat(), button.boundsInWindow.height, 1f)
        thePageGoesToTheBottomEdge()
    }

    /** A message is docked whether the buttons are or not: it moves none of them, and is in view. */
    @Test
    fun aMessageMovesNoButtonOnAPhoneOnItsSide() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        aProblemWithTwoButtons()
        val before = primary().positionInWindow
        rule.runOnUiThread { vm.say(R.string.error_unreachable) }
        rule.waitForIdle()
        assertEquals("the button is where it was", before, primary().positionInWindow)
        val message = rule.onNodeWithText(text(R.string.error_unreachable)).fetchSemanticsNode()
        shot("problem-message-small-landscape")
        assertEquals("the message is in view, whole", message.size.height.toFloat(), message.boundsInWindow.height, 1f)
        val messageAt = message.positionInWindow
        rule.onNodeWithText(text(R.string.back_home)).performScrollTo()
        rule.waitForIdle()
        assertEquals("the message stays where it is while the screen scrolls", messageAt, rule.onNodeWithText(text(R.string.error_unreachable)).fetchSemanticsNode().positionInWindow)
        assertTrue("the buttons still scroll with the content", scrolls(primary()))
    }

    /**
     * The system's bars stay the app's own after the phone was turned: no scrim of the system's is drawn over the page
     * where the navigation bar is (a phone with three buttons would show it as a pale strip under the screen).
     */
    @Test
    fun afterATurnTheNavigationBarsStripIsStillThePages() {
        aProblemWithTwoButtons()
        ScreenDevice.turn(rule, sideways = true)
        settle()
        assertFalse("the system draws no scrim behind the navigation bar", rule.activity.window.isNavigationBarContrastEnforced)
        thePageGoesToTheBottomEdge()
    }
}
