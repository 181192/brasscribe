package no.brasscribe.play

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * With no computer paired, a score that needs the computer can't be made by trying again: the way forward is to
 * connect it. The problem screens then make "Connect your computer" the primary, and it opens the pairing screen.
 */
@RunWith(AndroidJUnit4::class)
class NothingPairedTest : ScreenTest() {
    @Before
    fun noComputer() {
        container.fixtureSource = null
        container.settings.paired = false
    }

    @After
    fun clean() {
        rule.runOnUiThread {
            vm.cancelTranscription()
            vm.keptRecordings.value.forEach(vm::deleteKept)
            vm.home()
        }
        container.fixtureSource = null
    }

    private fun shows(id: Int) = rule.onAllNodesWithText(text(id)).fetchSemanticsNodes().isNotEmpty()

    private fun primary(): String = rule.onNodeWithTag("problem-primary").fetchSemanticsNode()
        .config[SemanticsProperties.Text].joinToString(" ") { it.text }

    /** Connect goes to the pairing screen, and Back comes back to the problem with the recording still in hand. */
    private fun connectLeadsToPairing() {
        rule.onNodeWithTag("problem-primary").performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.COMPANION }
        rule.runOnUiThread { vm.back() }
        waitUntil(5_000) { vm.screen.value.last() == Screen.PROBLEM }
    }

    @Test
    fun aScoreThatNeedsTheComputerOffersToConnectIt() {
        val file = recording("Band practice.wav")
        rule.runOnUiThread { vm.importUri(android.net.Uri.fromFile(file)) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread { vm.chooseProfile(Profile.BRASS_BAND); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM && shows(R.string.problem_score_title) }
        assertEquals(text(R.string.problem_connect_computer), primary())
        // Try again stays, for once the computer is connected.
        assertTrue(shows(R.string.retry))
        // Nothing ran, and the words say why rather than "something went wrong".
        assertTrue(shows(R.string.problem_score_body_unpaired) && !shows(R.string.problem_score_body))
        checkAccessibility()
        connectLeadsToPairing()
        assertEquals("Band practice.wav", vm.source.value?.name)

        // Paired from there (here the fixture computer comes): back on the problem, "connect first" is gone, and Try again
        // is the way forward.
        rule.onNodeWithTag("problem-primary").performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.COMPANION }
        computer("old-hundredth")
        rule.runOnUiThread { vm.back() }
        waitUntil(5_000) { vm.screen.value.last() == Screen.PROBLEM }
        rule.waitForIdle()
        assertTrue("no longer 'connect first'", !shows(R.string.where_companion_missing))
        assertEquals(text(R.string.retry), primary())
    }

    @Test
    fun aTakeTooLongForADraftOffersToConnectTheComputer() {
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Band practice.wav", SourceKind.FILE, 900.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.BRASS_BAND)
            vm.showProblem(Problem.DRAFT_TOO_LONG)
        }
        waitUntil(5_000) { shows(R.string.draft_too_long_title) }
        assertEquals(text(R.string.problem_connect_computer), primary())
        assertTrue(shows(R.string.problem_choose_another_recording))
        checkAccessibility()
        connectLeadsToPairing()
    }

    @Test
    fun aScoreThatFailedOnAComputerThatIsThereIsTriedAgain() {
        // The computer is there (the fixture): trying again is the likely fix, as before.
        computer("old-hundredth")
        rule.runOnUiThread { vm.showProblem(Problem.SCORE_FAILED, "job failed", R.string.error_engine_failed) }
        waitUntil(5_000) { shows(R.string.problem_score_title) }
        assertEquals(text(R.string.retry), primary())
    }
}
