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
    private fun theTab() {
        computer("bass-line-marks")
        showing = false
        openFromHome(recording())
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
        assertTrue("the player is lower ($before -> ${height("fs-practice")} dp)", height("fs-practice") <= before - 40f)
        assertTrue("the tab keeps room for the note being checked (${height("fs-tab-scroll")} dp)", height("fs-tab-scroll") >= 170f)

        rule.onNodeWithTag("fs-tab-note-close").performClick()
        rest()
        assertTrue("and comes back when it closes", there("fs-practice-place"))
    }
}
