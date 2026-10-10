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
 * be? is not asked. Band, difficulty and key are in the score's ⋯ sheet by that name, and still in the "your part" chip's sheet. A band take still asks.
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

    private fun take(profile: Profile, finishLater: Boolean = true) {
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
        if (finishLater) finishLater() else keepEveryNote()
    }

    private fun finishLater() {
        rule.onNodeWithText(text(R.string.review_finish_later_confirm), substring = true).performClick()
        rule.onNodeWithText(text(R.string.review_finish_later_confirm)).performClick()
    }

    /** Keep, go to next until no note is left; then the last button goes on. */
    private fun keepEveryNote() {
        var kept = 0
        while (rule.onAllNodesWithText(text(R.string.review_keep_next)).fetchSemanticsNodes().isNotEmpty()) {
            rule.onNodeWithText(text(R.string.review_keep_next)).performClick()
            rule.waitForIdle()
            check(++kept < 200) { "the notes to check never ran out" }
        }
        // For a solo it says where it goes: the score, not How should the score be?.
        val last = if (vm.result.value?.profile == Profile.SOLO) R.string.output_apply else R.string.review_continue
        rule.onNodeWithText(text(last)).performClick()
    }

    private fun assertOnTheScoreAtYourPart() {
        waitUntil(20_000) { vm.screen.value.last() == Screen.SCORE }
        assertFalse("How should the score be? is not asked", vm.screen.value.contains(Screen.OUTPUT))
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        val st = vm.scoreController!!.state.value
        assertEquals(setOf(vm.yourPart(st.parts, vm.result.value).index), st.shown)
    }

    @Test
    fun aSoloWithEveryNoteCheckedOpensOnTheScore() {
        take(Profile.SOLO, finishLater = false)
        assertOnTheScoreAtYourPart()
    }

    @Test
    fun aSoloMadeOnThePhoneOpensOnTheScore() {
        val composition = container.core.decodeComposition(String(checkNotNull(no.brasscribe.play.screen.ScreenDevice.fixture("old-hundredth/composition.json"))))
        val xml = String(checkNotNull(no.brasscribe.play.screen.ScreenDevice.fixture("old-hundredth/brass-band.musicxml")))
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("My take.wav", SourceKind.FILE, 30.0))
            vm.result.value = TranscriptionResult(composition, xml, Profile.SOLO, onDevice = true,
                compositionJson = String(checkNotNull(no.brasscribe.play.screen.ScreenDevice.fixture("old-hundredth/composition.json"))))
            vm.navigate(Screen.REVIEW)
        }
        waitUntil(20_000) { rule.onAllNodes(isHeading() and hasText("Check ", substring = true)).fetchSemanticsNodes().isNotEmpty() }
        finishLater()
        assertOnTheScoreAtYourPart()
        // Nothing was arranged again: the score is the one the phone made.
        assertEquals(xml, vm.result.value!!.musicXml)
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
        // In ⋯, by its name.
        rule.onNodeWithTag("top-more").performClick()
        waitUntil(5_000) { rule.onAllNodesWithTag("more-change-output").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText(text(R.string.change_output)).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.OUTPUT }
        rule.runOnUiThread { vm.back() }
        waitUntil(5_000) { vm.screen.value.last() == Screen.SCORE }
        // The score is read again on the way back: the chip says whose part it is only once that is done.
        val yourPart = text(R.string.stand_part_yours, PartNames.display(st.parts[yours!!]))
        waitUntil(30_000) { rule.onAllNodesWithText(yourPart, substring = true).fetchSemanticsNodes().isNotEmpty() }
        rule.onAllNodesWithText(yourPart, substring = true).onFirst().performClick()
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
