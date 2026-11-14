package no.kalli.brasscribe

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Home on a small phone. With nothing made yet it says what the app is for; with a score in Your scores the list starts
 * on the first screen, under the ways to make a new one, and the headline has stepped aside for it.
 */
@RunWith(AndroidJUnit4::class)
class HomeLibraryRoomTest : ScreenTest() {
    private fun headline() = rule.onAllNodesWithText(text(R.string.home_hero_start), substring = true).fetchSemanticsNodes().isNotEmpty()

    @Test
    fun aSmallPhoneShowsTheFirstScoreWithoutScrolling() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        rule.runOnUiThread { vm.home() }
        settle()
        assertTrue("with nothing made yet, Home says what the app is for", headline())

        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { rule.onAllNodesWithTag("score-options").fetchSemanticsNodes().isNotEmpty() }
        rest()
        shot("home-with-a-score-small")

        assertTrue("with a score, the headline steps aside", !headline())
        val row = rule.onNode(hasText("Old Hundredth")).fetchSemanticsNode()
        assertEquals("the first score is in view, whole", row.size.height.toFloat(), row.boundsInWindow.height, 1f)
        // The ways to make a new one are still above it.
        val open = rule.onNode(hasText(text(R.string.home_import))).fetchSemanticsNode()
        assertTrue("Open a recording is above the list", open.boundsInWindow.bottom <= row.boundsInWindow.top)
    }

    /** With larger text in bokmål the list still starts on the first screen: its heading and the first score's name. */
    @Test
    fun withLargerTextTheListStillStartsOnTheFirstScreen() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { rule.onAllNodesWithTag("score-options").fetchSemanticsNodes().isNotEmpty() }
        rest()
        shot("home-with-a-score-small-large-text")
        val name = rule.onNode(hasText("Old Hundredth")).fetchSemanticsNode()
        assertTrue("the first score's name is in view", name.boundsInWindow.height > 0f)
        // Not connected is one line, with its button beside it.
        val words = rule.onNode(hasText(text(no.kalli.scribe.play.R.string.conn_offline_brief))).fetchSemanticsNode()
        val connect = rule.onNode(hasText(text(no.kalli.scribe.play.R.string.companion_connect))).fetchSemanticsNode()
        assertTrue("Connect is beside the words", connect.boundsInWindow.left >= words.boundsInWindow.right && connect.boundsInWindow.top < words.boundsInWindow.bottom)
    }
}
