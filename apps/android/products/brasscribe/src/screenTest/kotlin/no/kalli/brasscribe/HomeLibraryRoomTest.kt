package no.kalli.brasscribe

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.longClick
import androidx.compose.ui.test.performTouchInput
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

    private fun aScore() {
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { rule.onAllNodesWithTag("score-options").fetchSemanticsNodes().isNotEmpty() }
        rest()
    }

    /** The first score's row (its name and the line under it, read as one) is inside the window, whole. */
    private fun firstScoreIsWhole() {
        val row = rule.onNode(hasText("Old Hundredth", substring = true)).fetchSemanticsNode()
        val window = rule.activity.window.decorView.let { androidx.compose.ui.geometry.Rect(0f, 0f, it.width.toFloat(), it.height.toFloat()) }
        assertEquals("the first score is in view, whole", row.size.height.toFloat(), row.boundsInWindow.height, 1f)
        assertTrue("its name and the line under it are inside the window", row.boundsInWindow.bottom <= window.bottom && row.boundsInWindow.top >= window.top)
        assertTrue("its name and the line under it are read with it: ${row.config}",
            row.config.getOrElseNullable(androidx.compose.ui.semantics.SemanticsProperties.Text) { null }.orEmpty().size >= 2)
    }

    /** On its side the connection is in the lockup's row and the ways in are one row, so the list starts on the first screen. */
    @Test
    fun onItsSideTheFirstScoreIsOnTheFirstScreen() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        language("nb-NO")
        aScore()
        shot("home-with-a-score-small-landscape")
        firstScoreIsWhole()
        val connect = rule.onNode(hasText(text(no.kalli.scribe.play.R.string.companion_connect))).fetchSemanticsNode().boundsInWindow
        val open = rule.onNode(hasText(text(R.string.home_import))).fetchSemanticsNode().boundsInWindow
        assertTrue("the connection is above the ways in, in the lockup's row", connect.bottom <= open.top)
        // The other ways in are beside Open a recording, by their icons, named in full.
        for ((tag, words) in listOf("home-record-mic" to R.string.home_record_mic, "home-record-device" to R.string.home_record_device)) {
            val b = rule.onNodeWithTag(tag).fetchSemanticsNode()
            assertTrue("$tag is beside Open a recording", b.boundsInWindow.top < open.bottom && b.boundsInWindow.left >= open.right)
            assertEquals(text(words), b.config[androidx.compose.ui.semantics.SemanticsProperties.ContentDescription].single())
        }
        checkAccessibility()
    }

    /** On a narrow phone the list starts on the first screen (its first score's name), and nothing is cut. */
    @Test
    fun onANarrowPhoneTheListStartsOnTheFirstScreen() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 320, 568))
        language("nb-NO")
        aScore()
        shot("home-with-a-score-narrow")
        // The list's heading and the first score's name are whole on the first screen.
        val name = rule.onAllNodes(hasText("Old Hundredth"), useUnmergedTree = true).fetchSemanticsNodes().first()
        assertEquals("the first score's name is in view, whole", name.size.height.toFloat(), name.boundsInWindow.height, 1f)
        val heading = rule.onNode(hasText(text(no.kalli.scribe.play.R.string.home_your_scores).uppercase()), useUnmergedTree = true).fetchSemanticsNode()
        assertEquals("Your scores is in view, whole", heading.size.height.toFloat(), heading.boundsInWindow.height, 1f)
        assertNoTextIsClipped()
    }

    private fun chevrons() = rule.onAllNodesWithTag("row-chevron", useUnmergedTree = true).fetchSemanticsNodes().size

    /** With a library the ways in keep their chevrons where their words keep to one line beside them, and only there. */
    @Test
    fun theWaysInKeepTheirChevronsWhereTheWordsFit() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 412, 915))
        aScore()
        assertEquals("a chevron on each of the three ways in on a common phone", 3, chevrons())
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        rule.runOnUiThread { vm.home() }
        rest()
        // "Spill inn med mikrofonen" and "Spill inn det som spilles" keep to one line only without it there; the short
        // "Åpne noter" keeps its chevron.
        val kept = rule.onAllNodesWithTag("row-chevron", useUnmergedTree = true).fetchSemanticsNodes().map { it.boundsInWindow.center.y }
        val open = rule.onNodeWithTag("home-open").fetchSemanticsNode().boundsInWindow
        assertEquals("one chevron, on the short row ($kept)", 1, kept.size)
        assertTrue("the chevron kept is the short row's", kept.single() in open.top..open.bottom)
        firstScoreIsWhole()
    }

    /** On its side the ways in by their icons show their words on a long press. */
    @Test
    fun onItsSideAnIconsWordsAreShownOnALongPress() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        aScore()
        rule.onNodeWithTag("home-record-mic").performTouchInput { longClick() }
        rest()
        assertTrue("the tooltip says Record with the microphone",
            rule.onAllNodesWithText(text(R.string.home_record_mic)).fetchSemanticsNodes().isNotEmpty())
    }

    /** At the largest text Home with a library has nothing cut; the list is a scroll away. */
    @Test
    fun withTheLargestTextNothingIsCut() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(2f)
        aScore()
        shot("home-with-a-score-small-200")
        assertNoTextIsClipped()
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
        // The first score's row, its name and the line under it, is in view, whole.
        firstScoreIsWhole()
        // Not connected is one line, with its button beside it.
        val words = rule.onNode(hasText(text(no.kalli.scribe.play.R.string.conn_offline_brief))).fetchSemanticsNode()
        val connect = rule.onNode(hasText(text(no.kalli.scribe.play.R.string.companion_connect))).fetchSemanticsNode()
        assertTrue("Connect is beside the words", connect.boundsInWindow.left >= words.boundsInWindow.right && connect.boundsInWindow.top < words.boundsInWindow.bottom)
    }
}
