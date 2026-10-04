package no.brasscribe.play

import android.net.Uri
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.activity.compose.setContent
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.Profile
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A score made from a recording, after the app was ended in the background on one of the score's screens:
 * the score comes back, and the recording it was made from is still the one in hand (What is this? is
 * under the score, and sends it), not deleted from the phone. And a bass tab in the computer's list, which
 * opens in Fretscribe: Open on the music stand on its row opens nothing and leaves nothing behind.
 */
@RunWith(AndroidJUnit4::class)
class RestoredTakeTest : ScreenTest() {

    @Before
    fun setUp() {
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth")
        waitUntil(10_000) { vm.savedScores.value.isEmpty() }
    }

    @Test
    fun theRecordingUnderARestoredScoreIsKeptAndIsStillTheOneInHand() {
        val file = recording()
        rule.runOnUiThread { vm.importUri(Uri.fromFile(file)) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread { vm.chooseProfile(Profile.BRASS_BAND); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.savedScores.value.size == 1 }
        val take = vm.source.value!!.file!!
        assertTrue(take.isFile && take.parentFile?.name == "takes")
        val stack = vm.screen.value
        assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.SCORE, Screen.REVIEW), stack)

        // A new process: a new view model on what the old one had saved.
        val state = SavedStateHandle(mapOf(
            "stack" to ArrayList(stack.map { it.name }),
            "source" to SavedSource.of(vm.source.value!!).encode(),
            "score" to vm.savedScores.value.single().id,
        ))
        lateinit var restored: PlayViewModel
        rule.runOnUiThread { restored = PlayViewModel(rule.activity.application, state) }
        waitUntil(20_000) { restored.result.value != null && restored.screen.value == stack }
        // The copies nothing refers to are cleared after a restore: this one is still referred to.
        pass(1500)
        assertTrue("the recording is still on the phone", take.isFile)
        assertEquals(take, restored.source.value?.file)
        assertEquals(SourceKind.FILE, restored.source.value?.kind)
        // Back to the score, then to What is this?: Continue sends the recording, not an empty file.
        rule.runOnUiThread { restored.back() }
        assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.SCORE), restored.screen.value)
        rule.runOnUiThread { restored.back() }
        assertEquals(listOf(Screen.HOME, Screen.PROFILE), restored.screen.value)
        assertEquals(take, restored.source.value?.file)
        assertTrue(restored.source.value!!.file!!.length() > 44)
    }

    @Test
    fun aScoreOpenedFromYourScoresStillComesBackAsAScore() {
        // No recording under it: the restored source is the score itself, as before.
        rule.runOnUiThread { vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0)); vm.chooseProfile(Profile.BRASS_BAND); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.savedScores.value.size == 1 }
        val saved = vm.savedScores.value.single()
        val state = SavedStateHandle(mapOf(
            "stack" to arrayListOf(Screen.HOME.name, Screen.SCORE.name),
            "source" to SavedSource(saved.title, SourceKind.SCORE, 0.0, null).encode(),
            "score" to saved.id,
        ))
        lateinit var restored: PlayViewModel
        rule.runOnUiThread { restored = PlayViewModel(rule.activity.application, state) }
        // (The score screens come back once the score is read: a moment after its result.)
        runCatching { waitUntil(20_000) { restored.result.value != null && restored.screen.value.last() == Screen.SCORE } }
        assertEquals("the screens, with the score read: ${restored.result.value != null}", listOf(Screen.HOME, Screen.SCORE), restored.screen.value)
        assertEquals(Source(saved.title, SourceKind.SCORE, 0.0), restored.source.value)
    }

    @Test
    fun openOnTheMusicStandOnABassTabsRowOpensNothingAndLeavesNoStandBehind() {
        // A tab of any instrument, and a bass tab an older app made: neither is this app's.
        for (profile in listOf("bass-tab", "tab")) {
            val tab = ScoreEntry("job:$profile-1", "Riff", System.currentTimeMillis(), profile, jobId = "$profile-1")
            rule.runOnUiThread { vm.openEntry(tab, stand = true) }
            waitUntil(5_000) { rule.onAllNodesWithText("This is a tab. Open it in Fretscribe.").fetchSemanticsNodes().isNotEmpty() }
            assertEquals(profile, listOf(Screen.HOME), vm.screen.value)
            // The next score opened is not put on the music stand.
            assertNull(vm.standFromLibrary.value)
            assertNull(vm.openingScore.value)
            // (The message goes away before the next one is asked for.)
            waitUntil(15_000) { rule.onAllNodesWithText("This is a tab. Open it in Fretscribe.").fetchSemanticsNodes().isEmpty() }
        }
    }

    /** The row menu of [entry], opened: the actions it offers. */
    private fun menuOf(entry: ScoreEntry): List<String> {
        rule.runOnUiThread {
            rule.activity.setContent { no.brasscribe.play.ui.theme.PlayTheme(dark = false, pink = false) { no.brasscribe.play.ui.ScoreOptionsButton(vm, entry) } }
        }
        rule.onNodeWithContentDescription(rule.activity.getString(R.string.score_options, entry.title)).performClick()
        rule.waitForIdle()
        return listOf(R.string.edit_title, R.string.stand_open_from_library, R.string.check_notes, R.string.delete)
            .map { rule.activity.getString(it) }.filter { rule.onAllNodesWithText(it).fetchSemanticsNodes().isNotEmpty() }
    }

    @Test
    fun aBassTabsRowOffersNeitherTheMusicStandNorCheckTheNotes() {
        val now = System.currentTimeMillis()
        assertEquals(listOf("Edit title", "Delete"), menuOf(ScoreEntry("job:tab-1", "Bass line", now, "bass-tab", jobId = "tab-1")))
        assertEquals(listOf("Edit title", "Delete"), menuOf(ScoreEntry("job:tab-2", "Guitar line", now, "tab", jobId = "tab-2")))
        // A band score in the same list has them all, as before.
        assertEquals(listOf("Edit title", "Open on the music stand", "Check the notes", "Delete"),
            menuOf(ScoreEntry("job:band-1", "Old Hundredth", now, "brass-band", jobId = "band-1")))
    }
}
