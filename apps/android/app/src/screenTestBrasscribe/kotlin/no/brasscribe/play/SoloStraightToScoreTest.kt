package no.brasscribe.play

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.ui.PartNames
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * A solo ("One instrument") goes from Check the notes straight to the score, on the player's part: How should the score
 * be? is not asked. Band, difficulty and key stay one tap away, in the sheet of the score's "your part" chip. A band take still asks.
 */
@RunWith(AndroidJUnit4::class)
class SoloStraightToScoreTest : ScreenTest() {
    @Before
    fun setUp() {
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth")
    }

    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    private fun take(profile: Profile) {
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(profile)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        waitUntil(20_000) { rule.onAllNodes(isHeading() and hasText("Check ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText(text(R.string.review_finish_later_confirm), substring = true).performClick()
        rule.onNodeWithText(text(R.string.review_finish_later_confirm)).performClick()
    }

    @Test
    fun aSoloOpensOnTheScoreAtThePlayersPart() {
        take(Profile.SOLO)
        waitUntil(20_000) { vm.screen.value.last() == Screen.SCORE }
        assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.SCORE), vm.screen.value)
        assertFalse("How should the score be? is not asked", vm.screen.value.contains(Screen.OUTPUT))
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        val st = vm.scoreController!!.state.value
        val yours = vm.yourPart(st.parts, vm.result.value).index
        assertNotNull("the solo has a part of the player's", yours)
        assertEquals(setOf(yours), st.shown)
        checkAccessibility()

        // Band, difficulty and key are where they were: the part's sheet (the "your part" chip) has the way back to them.
        rule.onAllNodesWithText(text(R.string.stand_part_yours, PartNames.display(st.parts[yours!!])), substring = true).onFirst().performClick()
        waitUntil(5_000) { rule.onAllNodesWithTag("change-output").fetchSemanticsNodes().isNotEmpty() }
        rule.waitForIdle()
        rule.onNodeWithTag("change-output").performScrollTo().performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.OUTPUT }
    }

    @Test
    fun aBandTakeStillAsksHowTheScoreShouldBe() {
        take(Profile.ORCHESTRA_WITH_SOLOIST)
        waitUntil(5_000) { vm.screen.value.last() == Screen.OUTPUT }
    }
}
