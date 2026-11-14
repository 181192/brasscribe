package no.kalli.brasscribe

import no.kalli.scribe.play.*

import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Printed music read from pages is a score in Brasscribe (the fixture computer serves "Old Hundredth"): it opens on
 * the score with no question about a band, is kept in Your scores, and is opened from there as the score it is.
 */
@RunWith(AndroidJUnit4::class)
class SheetMusicScoreTest : ScreenTest() {
    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        container.fixtureSource = null
    }

    private fun shows(id: Int) = rule.onAllNodesWithText(text(id)).fetchSemanticsNodes().isNotEmpty()

    @Test
    fun thePagesBecomeAScoreThatIsNotArranged() {
        computer("old-hundredth")
        pagesInHand(2)
        rule.onNodeWithTag("pages-read").performClick()
        waitUntil(60_000) { vm.result.value != null && vm.screen.value.last() == Screen.SCORE }
        // Straight to the score: no Check the notes and no How should the score be? on the way.
        assertEquals(listOf(Screen.HOME, Screen.SCORE), vm.screen.value)
        val read = vm.result.value!!
        assertEquals(Profile.SHEET, read.profile)
        assertFalse("written as it stands on the page", Brasscribe.arranges(read.profile))
        waitForEngravedScore()
        // It is the score the computer wrote, on the screen, with nothing about choosing a band for it.
        assertTrue(read.musicXml.contains("score-partwise"))
        assertFalse(shows(R.string.change_output) || shows(R.string.write_for_another))
        // No part is said to come from a recording: there is none.
        rest()
        assertFalse(shown(), shows(R.string.source_recording) || shows(R.string.source_yours))
        checkAccessibility()

        // Kept in Your scores, where its row says what it was made from, and opened from there on the score again.
        waitUntil(10_000) { vm.savedScores.value.any { it.jobId == read.jobId } }
        rule.runOnUiThread { vm.home() }
        rest()
        assertTrue(shown(), shown().contains(text(R.string.profile_sheet)))
        checkAccessibility()
        val before = vm.scoreController
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first { it.jobId == read.jobId }) }
        waitUntil(20_000) { vm.screen.value == listOf(Screen.HOME, Screen.SCORE) && vm.result.value?.profile == Profile.SHEET }
        waitForEngravedScore(before)
    }

    /** A job that finished while the app was away opens from its notice, as a recording's does. */
    @Test
    fun aScoreReadWhileTheAppWasAwayOpensFromItsNotice() {
        computer("old-hundredth")
        pagesInHand(1)
        rule.onNodeWithTag("pages-read").performClick()
        waitUntil(60_000) { vm.result.value != null && vm.screen.value.last() == Screen.SCORE }
        val job = vm.result.value!!.jobId!!
        waitUntil(10_000) { vm.savedScores.value.any { it.jobId == job } }
        waitForEngravedScore()
        val before = vm.scoreController
        rule.runOnUiThread { vm.home(); vm.openFinishedJob(job) }
        waitUntil(20_000) { vm.screen.value == listOf(Screen.HOME, Screen.SCORE) && vm.result.value?.jobId == job }
        assertEquals(Profile.SHEET, vm.result.value?.profile)
        waitForEngravedScore(before)
    }
}
