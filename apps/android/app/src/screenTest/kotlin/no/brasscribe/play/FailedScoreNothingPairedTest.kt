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
import org.junit.Test
import org.junit.runner.RunWith

/**
 * In both apps: a recording sent to the computer with nothing paired can't be made by trying again, so the problem
 * screen's primary is Connect your computer, which opens the pairing screen; Try again stays for once it is connected.
 */
@RunWith(AndroidJUnit4::class)
class FailedScoreNothingPairedTest : ScreenTest() {
    private val tab = Product.NAME == "Fretscribe"

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

    @Test
    fun aRecordingSentWithNothingPairedOffersToConnectTheComputer() {
        container.fixtureSource = null
        container.settings.paired = false
        val file = recording("Practice take.wav")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Practice take.wav", SourceKind.FILE, 2.0, file = file))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(if (tab) Profile.TAB else Profile.BRASS_BAND)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM && shows(R.string.problem_score_title) }
        assertEquals(text(R.string.problem_connect_computer),
            rule.onNodeWithTag("problem-primary").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString(" ") { it.text })
        assertTrue(shows(R.string.retry))
        checkAccessibility()
        rule.onNodeWithTag("problem-primary").performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.COMPANION }
        rule.runOnUiThread { vm.back() }
        waitUntil(5_000) { vm.screen.value.last() == Screen.PROBLEM }
        assertEquals("Practice take.wav", vm.source.value?.name)
    }
}
