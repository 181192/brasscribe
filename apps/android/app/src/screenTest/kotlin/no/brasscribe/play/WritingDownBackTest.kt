package no.brasscribe.play

import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * While a recording is being written down on the computer, Back (the gesture or the top bar's button) asks before it
 * stops the job, as Cancel does: Keep going leaves the job running; Stop ends it and goes back to What is this?.
 * In both apps (the transcribing screen is shared).
 */
@RunWith(AndroidJUnit4::class)
class WritingDownBackTest : ScreenTest() {
    private val tab = Product.NAME == "Fretscribe"

    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        container.fixtureSource = null
    }

    private fun asks(): Boolean = rule.onAllNodesWithText(text(R.string.transcribe_cancel_title)).fetchSemanticsNodes().isNotEmpty()

    private fun stillWriting() {
        rule.waitForIdle()
        assertEquals(Screen.TRANSCRIBE, vm.screen.value.last())
        assertTrue("the job still runs", vm.transcribe.value.running)
    }

    @Test
    fun backAsksBeforeItStopsTheJob() {
        // A computer that takes its time: each step a minute.
        computer(if (tab) "bass-line" else "old-hundredth")
        container.fixtureStageSeconds = 60.0
        val file = recording("Back test.wav")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Back test.wav", SourceKind.FILE, 2.0, file = file))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(if (tab) Profile.TAB else Profile.BRASS_BAND)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running }

        // The phone's Back asks; Keep going leaves the job as it was.
        ScreenDevice.back(rule)
        assertTrue("Back asks first", asks())
        stillWriting()
        checkAccessibility()
        rule.onNodeWithText(text(R.string.transcribe_cancel_keep)).performClick()
        rule.waitForIdle()
        assertTrue(!asks())
        stillWriting()

        // So does the top bar's button.
        rule.onNodeWithText(text(R.string.home)).performClick()
        assertTrue("the top bar's back asks first", asks())
        stillWriting()

        // Stop ends the job, and the recording is in hand on What is this?.
        rule.onNodeWithText(text(R.string.transcribe_cancel_confirm)).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.PROFILE }
        assertTrue("the job stopped", !vm.transcribe.value.running)
        assertEquals("Back test.wav", vm.source.value?.name)
    }
}
