package no.brasscribe.play.fret

import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.Where
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * While the notes are written down, the screen says what really happens: the player may switch apps, and a finished
 * tab is in Your songs. Stopping says the take stays in Your songs for 30 days, and it is there. In English and in Bokmål.
 */
@RunWith(AndroidJUnit4::class)
class WritingDownWordsTest : ScreenTest() {
    /** The fixture computer's pace before this test made it slow: put back, also for the tests after it on a device. */
    private var pace = 0.0

    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.keptRecordings.value.forEach(vm::deleteKept); vm.home() }
        container.fixtureSource = null
        if (pace > 0) container.fixtureStageSeconds = pace
    }

    private fun writing() {
        computer("bass-line")
        if (pace == 0.0) pace = container.fixtureStageSeconds
        container.fixtureStageSeconds = 60.0
        // Opened as a player opens it: the app's own copy, which is what is kept.
        rule.runOnUiThread { vm.home(); vm.importUri(android.net.Uri.fromFile(recording())) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread {
            vm.chooseProfile(Profile.TAB)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running }
        rule.waitForIdle()
    }

    private fun check(lang: String, leave: String, back: String, stopped: String) {
        writing()
        val shown = shown()
        assertTrue("$lang: $shown", shown.contains(leave))
        assertFalse("$lang: no longer says to keep the app open: $shown", shown.contains("Fretscribe open") || shown.contains("Fretscribe åpen"))
        ScreenDevice.back(rule)
        val asked = shown()
        assertTrue("$lang: $asked", asked.contains(back))
        rule.onNodeWithText(text(R.string.transcribe_cancel_confirm)).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.PROFILE }
        // Said once it is kept, and it is.
        waitUntil(5_000) { vm.status.value?.text.orEmpty().contains(stopped) }
        waitUntil(5_000) { vm.keptRecordings.value.size == 1 }
        rule.runOnUiThread { vm.keptRecordings.value.forEach(vm::deleteKept) }
    }

    @Test
    fun theWordsSayWhatHappensToTheJobAndTheRecording() {
        check("en", "You can switch to another app: when the tab is ready, it is in Your songs",
            "The recording stays in Your songs for 30 days.", "Stopped. The recording is in Your songs.")
        language("nb")
        check("nb", "Du kan bytte til en annen app: når tabben er klar, ligger den i Sangene dine",
            "Opptaket blir liggende i Sangene dine i 30 dager.", "Stoppet. Opptaket ligger i Sangene dine.")
    }
}
