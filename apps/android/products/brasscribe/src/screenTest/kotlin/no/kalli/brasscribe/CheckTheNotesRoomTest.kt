package no.kalli.brasscribe

import no.kalli.scribe.play.*

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Check the notes on a small phone: the bar with the note being checked is in view, whole, with Keep and Skip under
 * it, upright with larger text in bokmål, on a narrow phone and with the phone on its side; and on a narrow phone the top bar's
 * Finish later has the row to itself beside the arrow.
 */
@RunWith(AndroidJUnit4::class)
class CheckTheNotesRoomTest : ScreenTest() {
    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    private fun checkTheNotes() {
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        // (The bar is part of the note's card, which is read as one.)
        waitUntil(20_000) { rule.onAllNodesWithTag("review-bar", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        rest()
    }

    private fun whole(tag: String) {
        val node = rule.onNodeWithTag(tag, useUnmergedTree = true).fetchSemanticsNode()
        assertTrue("$tag has a height", node.size.height > 0)
        assertEquals("$tag is in view, whole", node.size.height.toFloat(), node.boundsInWindow.height, 1f)
    }

    @Test
    fun aSmallPhoneWithLargerTextShowsTheBarBeingChecked() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        checkTheNotes()
        shot("check-the-notes-small")
        whole("review-bar")
    }

    @Test
    fun aSmallPhoneOnItsSideShowsTheBarBeingChecked() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        checkTheNotes()
        shot("check-the-notes-small-landscape")
        whole("review-bar")
        // Keep and Skip are one row here, so the bar has the height.
        val keep = rule.onNodeWithText(text(R.string.review_keep_next)).fetchSemanticsNode().boundsInWindow
        val skip = rule.onNodeWithText(text(R.string.review_skip)).fetchSemanticsNode().boundsInWindow
        assertTrue("Skip is beside Keep", skip.left >= keep.right && skip.top < keep.bottom)
    }

    @Test
    fun aNarrowPhoneKeepsFinishLaterClearOfTheBackButton() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 320, 568))
        language("nb-NO")
        checkTheNotes()
        shot("check-the-notes-narrow")
        whole("review-bar")
        val later = rule.onNode(hasText(text(R.string.review_finish_later, 4))).fetchSemanticsNode().boundsInWindow
        val back = rule.onNode(androidx.compose.ui.test.hasContentDescription(text(R.string.back))).fetchSemanticsNode().boundsInWindow
        assertTrue("Finish later starts after the back button", later.left >= back.right)
        // And where the three do not fit on a line, Keep is over Skip, each with its words on one line.
        val keep = rule.onNodeWithText(text(R.string.review_keep_next)).fetchSemanticsNode().boundsInWindow
        val skip = rule.onNodeWithText(text(R.string.review_skip)).fetchSemanticsNode().boundsInWindow
        assertTrue("Keep and Skip do not overlap", skip.left >= keep.right || skip.top >= keep.bottom)
    }
}
