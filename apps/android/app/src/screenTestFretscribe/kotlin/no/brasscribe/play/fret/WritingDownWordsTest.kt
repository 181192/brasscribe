package no.brasscribe.play.fret

import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.Source
import no.brasscribe.play.SourceKind
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
 * tab is in Your songs. Stopping says the recording is in hand on What is this?, never that it is kept (Fretscribe
 * keeps no recordings). In English and in Bokmål.
 */
@RunWith(AndroidJUnit4::class)
class WritingDownWordsTest : ScreenTest() {
    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        container.fixtureSource = null
    }

    private fun writing() {
        computer("bass-line")
        container.fixtureStageSeconds = 60.0
        val file = recording()
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Bass line.wav", SourceKind.FILE, 2.0, file = file))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.TAB)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running }
        rule.waitForIdle()
    }

    private fun check(lang: String, leave: String, kept: String, back: String, stopped: String) {
        writing()
        val shown = shown()
        assertTrue("$lang: $shown", shown.contains(leave))
        assertFalse("$lang: no longer says to keep the app open: $shown", shown.contains("Fretscribe open") || shown.contains("Fretscribe åpen"))
        ScreenDevice.back(rule)
        val asked = shown()
        assertTrue("$lang: $asked", asked.contains(back))
        assertFalse("$lang: the recording is not said to be kept: $asked", asked.contains(kept))
        rule.onNodeWithText(text(R.string.transcribe_cancel_confirm)).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.PROFILE }
        val said = vm.status.value?.text.orEmpty()
        assertTrue("$lang: $said", said.contains(stopped))
        assertFalse("$lang: $said", said.contains(kept))
    }

    @Test
    fun theWordsSayWhatHappensToTheJobAndTheRecording() {
        check("en", "You can switch to another app: when the tab is ready, it is in Your songs", "is kept", "What is this?", "Stopped.")
        language("nb")
        check("nb", "Du kan bytte til en annen app: når tabben er klar, ligger den i Sangene dine", "tatt vare på.", "Hva er dette?", "Stoppet.")
    }
}
