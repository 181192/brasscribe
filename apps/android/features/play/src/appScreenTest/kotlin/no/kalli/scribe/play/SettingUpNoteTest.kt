package no.kalli.scribe.play

import androidx.compose.ui.test.onAllNodesWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.screen.ScreenTest
import no.kalli.scribe.play.screen.testedProduct
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * While the computer is still setting up (downloading) what a started stage needs, the writing-down screen says so,
 * without naming the model; the note is gone once the stage has it. In both apps (the screen is shared).
 */
@RunWith(AndroidJUnit4::class)
class SettingUpNoteTest : ScreenTest() {
    private val tab get() = testedProduct.name == "Fretscribe"

    @After
    fun clean() {
        container.fixtureSettingUp = null
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        container.fixtureSource = null
    }

    private fun noteShown() = rule.onAllNodesWithTag("transcribe-setting-up").fetchSemanticsNodes().isNotEmpty()

    @Test
    fun theNoteShowsWhileTheComputerSetsUpAndGoesAfter() {
        computer(if (tab) "bass-line" else "old-hundredth")
        container.fixtureSettingUp = "separator"
        val file = recording("Setting up.wav")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Setting up.wav", SourceKind.FILE, 2.0, file = file))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(if (tab) Profile.TAB else Profile.BRASS_BAND)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.settingUp }
        waitUntil(5_000) { noteShown() }
        assertTrue(vm.transcribe.value.running)
        container.fixtureSettingUp = null
        waitUntil(10_000) { !vm.transcribe.value.settingUp }
        waitUntil(5_000) { !noteShown() }
        assertEquals(false, vm.transcribe.value.settingUp)
    }
}
