package no.kalli.fretscribe

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The tab on a small phone keeps the room to be read in: on its side the player is one row, and upright with a note
 * open under it the player is a row lower.
 */
@RunWith(AndroidJUnit4::class)
class TabRoomTest : TabScreenTest() {
    private val density get() = rule.density.density
    private fun height(tag: String) = rule.onNodeWithTag(tag).fetchSemanticsNode().size.height / density
    private fun there(tag: String) = rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()

    /** The tab with its player, by the way a player gets there (every step scrolled to: the screen is small). */
    private fun theTab(file: String = "Bass line.wav") {
        computer("bass-line-marks")
        showing = false
        openFromHome(recording(file))
        waitForTag("fs-what-continue", 20_000)
        rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-instrument"))).performScrollTo().performClick()
        tap("fs-what-continue")
        waitForTag("fs-show-tab")
        showing = true
        tap("fs-show-tab")
        engraved()
        waitForTag("fs-practice-play", 30_000)
        rest()
    }

    private fun theTabView(): TabView { theTab(); return engraved() }

    /** A button that is docked under what scrolls, or, where the screen is short, at the end of it. */
    private fun tap(tag: String) {
        runCatching { rule.onNodeWithTag(tag).performScrollTo() }
        rule.onNodeWithTag(tag).performClick()
    }

    private fun openANote() {
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo().performClick()
        waitForTag("fs-tab-note", 5_000)
        rest()
    }

    @Test
    fun onItsSideThePlayerIsOneRowAndTheTabHasTheRest() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        theTab()
        shot("tab-small-landscape")
        // The tuning is in the top bar, where the line with it is a scroll up.
        rule.onNode(androidx.compose.ui.test.isHeading() and androidx.compose.ui.test.hasText("Standard", substring = true)).assertExists()
        // One row: Play's 64 dp and the space around it.
        assertTrue("the player is one row (${height("fs-practice")} dp)", height("fs-practice") <= 84f)
        assertTrue("the tab has half the screen (${height("fs-tab-scroll")} dp)", height("fs-tab-scroll") >= 180f)
        // What is shorter to the eye is whole to the ear.
        assertEquals(text(R.string.fs_practice_repeat), rule.onNodeWithTag("fs-practice-repeat").fetchSemanticsNode().config[SemanticsProperties.ContentDescription].single())

        openANote()
        shot("tab-note-small-landscape")
        // The note takes the player's place, so the staff of the note being checked is whole: the tab has what it had.
        assertTrue("the player steps aside for the note", !there("fs-practice"))
        assertTrue("the tab keeps its room with a note open (${height("fs-tab-scroll")} dp)", height("fs-tab-scroll") >= 180f)
        assertEquals(text(R.string.fs_tab_note_slowly), rule.onNodeWithTag("fs-tab-note-slowly").fetchSemanticsNode().config[SemanticsProperties.ContentDescription].single())
    }

    /**
     * On its side the top bar carries the tuning after the title: a long title gives way to it with "…", and the
     * buttons and the tuning stay whole in the bar.
     */
    @Test
    fun onItsSideALongTitleGivesWayToTheTuningAndTheButtons() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        val long = "The long walk home through the hills, as the band played it at the spring concert"
        theTab("$long.wav")
        shot("tab-long-title-small-landscape")
        val title = rule.onNodeWithTag("top-bar-title", useUnmergedTree = true).fetchSemanticsNode()
        val tail = rule.onNodeWithTag("top-bar-title-tail", useUnmergedTree = true).fetchSemanticsNode()
        // The title is cut with "…"; the tuning is whole.
        val layouts = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
        title.config[androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult].action?.invoke(layouts)
        assertTrue("the long title is cut with …", layouts.single().isLineEllipsized(0))
        val tailLayouts = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
        tail.config[androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult].action?.invoke(tailLayouts)
        val t = tailLayouts.single()
        assertTrue("the tuning is not cut", !t.isLineEllipsized(0) && t.lineCount == 1 && t.getLineRight(0) <= t.size.width + 1f)
        assertEquals("the tuning is in view, whole", tail.size.width.toFloat(), tail.boundsInWindow.width, 1f)
        assertTrue("the tuning is said", tail.config[SemanticsProperties.Text].joinToString("") { it.text }.contains("Standard"))
        // The buttons are in the window, whole, and right of the tuning.
        val window = rule.activity.window.decorView.width.toFloat()
        for (tag in listOf("fs-tab-full-screen")) {
            val b = rule.onNodeWithTag(tag).fetchSemanticsNode().boundsInWindow
            assertTrue("$tag is inside the window", b.right <= window + 0.5f && b.width >= 47f * density)
            assertTrue("$tag is right of the tuning", b.left >= tail.boundsInWindow.right)
        }
        // The heading is read whole: the full title and the tuning.
        rule.onNode(androidx.compose.ui.test.isHeading() and androidx.compose.ui.test.hasText(long, substring = true)).assertExists()
    }

    /**
     * With the largest text on a phone on its side the note's words take three lines and the tab less room: the page
     * is moved so the column of the note being checked, its mark and its numerals, is whole all the same.
     */
    @Test
    fun onItsSideWithTheLargestTextTheNoteBeingCheckedIsWhole() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        textSize(2f)
        val tab = theTabView()
        openANote()
        shot("tab-note-small-landscape-200")
        val box = tab.engraving.value!!.boxes.first()
        val mark = rule.onNodeWithTag("fs-tab-mark-0").fetchSemanticsNode()
        val page = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow
        val top = mark.positionInWindow.y
        val bottom = top + (box.columnBottom - box.top)
        assertTrue("the mark is in view ($top in ${page.top}..${page.bottom})", top >= page.top - 1f)
        assertTrue("the numerals under it are in view ($bottom in ${page.top}..${page.bottom})", bottom <= page.bottom + 1f)
    }

    /**
     * On its side the line with the tuning and "Check it" is a scroll up from where the tab opens (the tab and the
     * player have the screen). Scrolled to, it opens the first note marked "?".
     */
    @Test
    fun onItsSideCheckItOpensTheFirstMarkedNote() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        theTab()
        rule.onNodeWithTag("fs-tab-marked").performScrollTo()
        rest()
        rule.onNodeWithTag("fs-tab-marked").assertIsDisplayed().performClick()
        waitForTag("fs-tab-note", 5_000)
        rule.onNodeWithTag("fs-tab-note-close").performClick()
        rest()
        assertTrue("the player is back when the note closes", there("fs-practice"))
    }

    @Test
    fun uprightWithANoteOpenThePlayerIsARowLower() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        theTab()
        val before = height("fs-practice")

        openANote()
        shot("tab-note-small")
        // Play, the speed and the repeat stay; where the song is steps aside, and the player is a row lower.
        assertTrue("Play, the speed and the repeat stay", there("fs-practice-play") && there("fs-practice-speed") && there("fs-practice-repeat"))
        assertTrue("where the song is steps aside for the note", !there("fs-practice-place"))
        // (At this text size Repeat bars is its icon beside the transport, so the player is two rows with or without a note.)
        assertTrue("the player is no higher ($before -> ${height("fs-practice")} dp)", height("fs-practice") <= before)
        assertTrue("the tab keeps room for the note being checked (${height("fs-tab-scroll")} dp)", height("fs-tab-scroll") >= 170f)
        // And the note being checked is in it: its mark, and the numerals under it.
        val box = TabScreenProbe.view!!.engraving.value!!.boxes.first()
        val mark = rule.onNodeWithTag("fs-tab-mark-0").fetchSemanticsNode()
        val page = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow
        assertTrue("the mark is in view (${mark.positionInWindow.y} in ${page.top}..${page.bottom}, column ${box.top}..${box.columnBottom}, lines ${TabScreenProbe.view!!.engraving.value!!.lines})", mark.positionInWindow.y >= page.top - 1f)
        assertTrue("the numerals under it are in view", mark.positionInWindow.y + (box.columnBottom - box.top) <= page.bottom + 1f)

        rule.onNodeWithTag("fs-tab-note-close").performClick()
        rest()
        assertTrue("and comes back when it closes", there("fs-practice-place"))
    }
}
