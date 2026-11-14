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

    /** [twoInABar]: the two notes the computer grouped in one bar are two places to check, so the bar has more than one. */
    private fun checkTheNotes(twoInABar: Boolean = false) {
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth") { name, bytes ->
            if (!twoInABar || name != "composition.json" || bytes == null) bytes else org.json.JSONObject(String(bytes)).also { c ->
                val review = c.getJSONArray("review")
                val split = org.json.JSONArray()
                for (i in 0 until review.length()) {
                    val g = review.getJSONObject(i)
                    if (g.getInt("notes") != 2) { split.put(g); continue }
                    val middle = (g.getInt("start") + g.getInt("end")) / 2
                    split.put(org.json.JSONObject(g.toString()).put("end", middle).put("notes", 1))
                    split.put(org.json.JSONObject(g.toString()).put("start", middle).put("notes", 1))
                }
                c.put("review", split)
            }.toString().toByteArray()
        }
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
        assertTrue("Skip is under Keep", skip.top >= keep.bottom)
    }

    /** The second place to check shares its bar with the third, so there is a third button: Keep the rest of this bar. */
    private fun aBarWithTwoNotesToCheck() {
        rule.onNodeWithText(text(R.string.review_skip)).performClick()
        waitUntil(10_000) { rule.onAllNodesWithTag("review-keep-bar", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        // (The next note is said in a message over the buttons; it is looked at when that has gone.)
        pass(no.kalli.scribe.play.ui.STATUS_MS + 1_000)
        rest()
    }

    private fun bounds(words: String) = rule.onNodeWithText(words).fetchSemanticsNode().boundsInWindow

    @Test
    fun onItsSideThreeButtonsAreOneRowAndListenIsBesideTheBar() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        checkTheNotes(twoInABar = true)
        // Listen and Change stand beside the bar, in view with it.
        val bar = rule.onNodeWithTag("review-bar", useUnmergedTree = true).fetchSemanticsNode().boundsInWindow
        val listen = rule.onNodeWithText(text(R.string.action_listen_bar)).fetchSemanticsNode()
        assertEquals("Listen is in view, whole", listen.size.height.toFloat(), listen.boundsInWindow.height, 1f)
        assertTrue("Listen is beside the bar", listen.boundsInWindow.left >= bar.right)
        aBarWithTwoNotesToCheck()
        shot("check-the-notes-bar-small-landscape")
        whole("review-bar")
        val keep = bounds(text(R.string.review_keep_next))
        val skip = bounds(text(R.string.review_skip))
        val keepBar = rule.onNodeWithTag("review-keep-bar", useUnmergedTree = true).fetchSemanticsNode().boundsInWindow
        assertTrue("Keep, Skip and Keep the bar are one row", skip.left >= keep.right && keepBar.left >= skip.right && skip.top < keep.bottom && keepBar.top < keep.bottom)
    }

    @Test
    fun onItsSideWithLargerTextInBokmalThreeButtonsAreStillOneRow() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        textSize(1.3f)
        language("nb-NO")
        checkTheNotes(twoInABar = true)
        aBarWithTwoNotesToCheck()
        shot("check-the-notes-bar-small-landscape-nb-130")
        whole("review-bar")
        val keep = bounds(text(R.string.review_keep_next))
        val skip = bounds(text(R.string.review_skip))
        val keepBar = rule.onNodeWithTag("review-keep-bar", useUnmergedTree = true).fetchSemanticsNode()
        val k = keepBar.boundsInWindow
        assertTrue("Keep, Skip and Keep the rest are one row", skip.left >= keep.right && k.left >= skip.right && skip.top < keep.bottom && k.top < keep.bottom)
        // Its words are short here; its name is said in full.
        assertEquals(rule.activity.resources.getQuantityString(R.plurals.review_keep_bar, 2, 2), keepBar.config[androidx.compose.ui.semantics.SemanticsProperties.ContentDescription].single())
        assertNoTextIsClipped()
    }

    @Test
    fun aCommonPhoneShowsKeepOverSkipAndKeepTheRest() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 412, 915))
        checkTheNotes(twoInABar = true)
        aBarWithTwoNotesToCheck()
        shot("check-the-notes-bar-common")
        whole("review-bar")
        // Keep has a row; Skip and Keep the rest of this bar share the one under it, each with its words on one line.
        val keep = bounds(text(R.string.review_keep_next))
        val skip = bounds(text(R.string.review_skip))
        val keepBar = rule.onNodeWithTag("review-keep-bar", useUnmergedTree = true).fetchSemanticsNode().boundsInWindow
        assertTrue("Skip is under Keep", skip.top >= keep.bottom)
        assertTrue("Keep the rest is beside Skip", keepBar.left >= skip.right && keepBar.top < skip.bottom && skip.top < keepBar.bottom)
        rule.onNodeWithText(rule.activity.resources.getQuantityString(R.plurals.review_keep_bar, 2, 2)).assertExists()
        assertNoTextIsClipped()
    }

    @Test
    fun aNarrowPhoneShowsTheBarOverThreeButtons() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 320, 568))
        language("nb-NO")
        checkTheNotes(twoInABar = true)
        aBarWithTwoNotesToCheck()
        shot("check-the-notes-bar-narrow")
        whole("review-bar")
        // The three have a row each here: none has room for its words on one line beside another.
        val keep = bounds(text(R.string.review_keep_next))
        val skip = bounds(text(R.string.review_skip))
        val keepBar = rule.onNodeWithTag("review-keep-bar", useUnmergedTree = true).fetchSemanticsNode().boundsInWindow
        assertTrue("Keep, Skip and Keep the bar are one under the other", skip.top >= keep.bottom && keepBar.top >= skip.bottom)
        assertNoTextIsClipped()
    }

    /** With the largest text on a 360 dp phone Finish later has the top bar beside the arrow, whole. */
    @Test
    fun withTheLargestTextFinishLaterIsWhole() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(2f)
        checkTheNotes()
        shot("check-the-notes-small-200")
        whole("review-bar")
        val later = rule.onNode(hasText(text(R.string.review_finish_later, 4))).fetchSemanticsNode()
        val back = rule.onNode(androidx.compose.ui.test.hasContentDescription(text(R.string.back))).fetchSemanticsNode().boundsInWindow
        assertTrue("Finish later starts after the back button", later.boundsInWindow.left >= back.right)
        assertEquals("Finish later is in view, whole", later.size.height.toFloat(), later.boundsInWindow.height, 1f)
        assertNoTextIsClipped()
    }
}
