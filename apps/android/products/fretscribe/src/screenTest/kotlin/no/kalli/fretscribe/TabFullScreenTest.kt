package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.click
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** The tab in full screen: one control in, the tab with the whole screen, a tap or back to the controls. */
@RunWith(AndroidJUnit4::class)
class TabFullScreenTest : TabScreenTest() {
    private fun gone(tag: String) = assertTrue("$tag is gone", rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isEmpty())
    private fun there(tag: String) = rule.onNodeWithTag(tag).assertIsDisplayed()
    private fun tabHeight() = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().size.height

    private fun enter() {
        rule.onNodeWithTag("fs-tab-full-screen").assertContentDescriptionEquals("Full screen").performClick()
        settle()
    }

    private fun theTabInFullScreen() {
        computer("bass-line-marks")
        showTheTab()
        enter()
    }

    @Test
    fun theTabTakesTheWholeScreenAndOnlyPlayAndLeaveStay() {
        computer("bass-line-marks")
        showTheTab()
        val before = tabHeight()
        listOf("fs-tab-full-screen", "fs-tab-zoom-in", "fs-tab-tuning", "fs-tab-marked", "fs-practice").forEach(::there)
        enter()
        listOf("fs-tab-full-screen", "fs-tab-zoom-in", "fs-tab-tuning", "fs-tab-marked", "fs-tab-no-place", "fs-practice").forEach(::gone)
        there("fs-tab-focus-minimal")
        there("fs-tab-focus-play")
        there("fs-tab-full-screen-leave")
        assertTrue("the tab has more room: $before -> ${tabHeight()}", tabHeight() > before)
    }

    @Test
    fun aTapOnTheTabShowsTheControlsAndAnotherHidesThem() {
        theTabInFullScreen()
        rule.onNodeWithTag("fs-tab-scroll").performTouchInput { click(Offset(2f, center.y)) }
        settle()
        listOf("fs-tab-focus-controls", "fs-practice", "fs-tab-zoom-in", "fs-tab-zoom-out", "fs-tab-full-screen-leave").forEach(::there)
        gone("fs-tab-focus-minimal")
        rule.onNodeWithTag("fs-tab-scroll").performTouchInput { click(Offset(2f, center.y)) }
        settle()
        gone("fs-practice")
        there("fs-tab-focus-minimal")
    }

    @Test
    fun leavingBringsTheScreenBack() {
        theTabInFullScreen()
        rule.onNodeWithTag("fs-tab-full-screen-leave").assertContentDescriptionEquals("Leave full screen").performClick()
        settle()
        listOf("fs-tab-full-screen", "fs-tab-zoom-in", "fs-tab-tuning", "fs-practice").forEach(::there)
        gone("fs-tab-focus-minimal")
    }

    @Test
    fun backLeavesFullScreenBeforeItLeavesTheTab() {
        theTabInFullScreen()
        val screen = vm.screen.value.last()
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        settle()
        there("fs-tab-full-screen")
        assertEquals(screen, vm.screen.value.last())
    }

    @Test
    fun withAScreenReaderTheControlsStayUp() {
        computer("bass-line-marks")
        container.touchExplorationOverride = true
        showTheTab()
        enter()
        there("fs-tab-focus-controls")
        there("fs-practice")
        there("fs-tab-full-screen-leave")
    }
}
