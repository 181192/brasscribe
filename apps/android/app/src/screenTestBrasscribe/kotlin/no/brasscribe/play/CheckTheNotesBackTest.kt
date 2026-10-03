package no.brasscribe.play

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Check the notes after a score is made: Back (the gesture or the top bar's button, which names the score) goes to
 * the score, which is already saved, never to What is this?, where Continue would send the recording again. Show the
 * score and Check them go back to that score instead of piling up new ones.
 */
@RunWith(AndroidJUnit4::class)
class CheckTheNotesBackTest : ScreenTest() {
    @Before
    fun setUp() {
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
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
        waitUntil(20_000) { rule.onAllNodes(isHeading() and hasText("Check ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
    }

    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    @Test
    fun backFromCheckTheNotesGoesToTheScore() {
        assertEquals(listOf(Screen.HOME, Screen.SCORE, Screen.REVIEW), vm.screen.value)
        ScreenDevice.back(rule)
        waitUntil(5_000) { vm.screen.value.last() == Screen.SCORE }
        assertEquals(listOf(Screen.HOME, Screen.SCORE), vm.screen.value)
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        checkAccessibility()

        // Check them (as its button does), then the top bar's back: the score again.
        rule.runOnUiThread { vm.navigate(Screen.REVIEW) }
        waitUntil(5_000) { vm.screen.value.last() == Screen.REVIEW }
        val title = vm.result.value!!.composition!!.title
        rule.onNodeWithText(no.brasscribe.play.ui.PartNames.shortTitle(title)).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.SCORE }
        assertEquals(listOf(Screen.HOME, Screen.SCORE), vm.screen.value)
    }

    @Test
    fun finishLaterAndShowTheScoreGoBackToTheSameScore() {
        rule.onNodeWithText(text(R.string.review_finish_later_confirm), substring = true).performClick()
        rule.onNodeWithText(text(R.string.review_finish_later_confirm)).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.OUTPUT }
        rule.onNodeWithText(text(R.string.output_apply)).performClick()
        waitUntil(20_000) { vm.screen.value.last() == Screen.SCORE }
        assertEquals(listOf(Screen.HOME, Screen.SCORE), vm.screen.value)
    }
}
