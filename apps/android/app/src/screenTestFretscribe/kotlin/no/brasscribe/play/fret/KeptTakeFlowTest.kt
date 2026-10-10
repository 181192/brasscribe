package no.brasscribe.play.fret

import android.net.Uri
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.lifecycle.SavedStateHandle
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.Product
import no.brasscribe.play.Screen
import no.brasscribe.play.Where
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Fretscribe keeps a take whose tab could not be made, as Brasscribe keeps its recordings: it is a row of Your songs
 * after the app was closed and opened again, Settings says what the kept takes use and that one with no tab is
 * deleted after 30 days, and the problem says where it is.
 */
@RunWith(AndroidJUnit4::class)
class KeptTakeFlowTest : ScreenTest() {
    @Before
    fun noComputer() {
        rule.runOnUiThread { container.fixtureSource = null; vm.keptRecordings.value.forEach(vm::deleteKept); vm.home() }
        waitUntil(10_000) { vm.keptRecordings.value.isEmpty() }
    }

    @After
    fun tearDown() {
        rule.runOnUiThread { vm.keptRecordings.value.forEach(vm::deleteKept); vm.home() }
    }

    @Test
    fun stoppedTheTakeMovesIntoYourSongsWithWhatIsThisAnswerKept() {
        computer("bass-line")
        val pace = container.fixtureStageSeconds
        container.fixtureStageSeconds = 60.0
        try {
            rule.runOnUiThread { vm.importUri(Uri.fromFile(recording())) }
            waitForTag("fs-what-continue", 20_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
            fun song() = rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
                hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-song")))
            song().performClick()
            rule.onNodeWithTag("fs-what-continue").performClick()
            waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running }
            // Stop, as the dialog does: the take moves into Your songs and is still the recording in hand.
            rule.runOnUiThread { vm.cancelTranscription(); vm.back() }
            waitUntil(10_000) { vm.keptRecordings.value.size == 1 && vm.source.value?.file == vm.keptRecordings.value.single().file }
            waitForTag("fs-what-continue", 10_000)
            // What is this? still has the answer given for it.
            song().assertIsSelected()
        } finally {
            container.fixtureStageSeconds = pace
            container.fixtureSource = null
        }
    }

    @Test
    fun aTakeWhoseTabCouldNotBeMadeIsKeptInYourSongsFor30Days() {
        assertTrue(Product.KEEPS_RECORDINGS)
        assertEquals(30, Product.KEPT_RECORDING_DAYS)
        rule.runOnUiThread { vm.importUri(Uri.fromFile(recording("Riff.wav"))) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread { vm.chooseProfile(Profile.TAB); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM && vm.keptRecordings.value.size == 1 }
        val kept = vm.keptRecordings.value.single()
        assertTrue(rule.onAllNodesWithText("Your recording is kept in Your songs for 30 days. You can try again now or later.")
            .fetchSemanticsNodes().isNotEmpty())

        // A new process lists it.
        lateinit var restored: PlayViewModel
        rule.runOnUiThread { restored = PlayViewModel(rule.activity.application, SavedStateHandle()) }
        waitUntil(10_000) { restored.keptRecordings.value.map { it.id } == listOf(kept.id) }

        // A row of Your songs, with no tab yet.
        rule.runOnUiThread { vm.home() }
        waitUntil(5_000) { rule.onAllNodesWithTag("kept-${kept.id}").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(rule.onAllNodesWithText("No tab yet", substring = true).fetchSemanticsNodes().isNotEmpty())

        // Settings says what they use, and how long one without a tab stays.
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
        rule.waitForIdle()
        rule.onNodeWithTag("kept-storage", useUnmergedTree = true).performScrollTo()
        assertTrue(shown(), Regex("""Recordings kept in Your songs use \S+ \S+\. One with no tab after 30 days is deleted\.""").containsMatchIn(shown()))
        language("nb")
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
        rule.waitForIdle()
        assertTrue(shown(), shown().contains("Et opptak uten tab etter 30 dager slettes."))
    }
}
