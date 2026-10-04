package no.brasscribe.play.fret

import android.net.Uri
import androidx.activity.compose.setContent
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsNotSelected
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.MainActivity
import no.brasscribe.play.PlayApplication
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.Product
import no.brasscribe.play.RestoredStack
import no.brasscribe.play.SavedSource
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.Recording
import no.brasscribe.play.ui.theme.PlayTheme
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
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
 * The way to a tab after the app was ended in the background, at What is this?, while the notes were
 * being written down, and on Check the song: the screens come back from what was saved, as a new process
 * builds them (a new view model on the saved state, with nothing remembered in memory), the recording is
 * still on the phone, and the song can be written down again. Also with the phone's copy of the recording
 * gone, and for a song opened from Your songs: the computer still has the recording it was sent.
 */
@RunWith(AndroidJUnit4::class)
class RestoredSongTest : ScreenTest() {
    private val first get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]

    @Before
    fun setUp() {
        yourInstrumentStore(rule.activity).save(YourInstrument(no.brasscribe.play.engine.FrettedInstrument.BASS_4))
        // The computer answers as it did for the bass line, as if the line sounded like drop D: a change is on offer.
        computer("bass-line") { name, bytes ->
            if (name != "tab.json" || bytes == null) bytes else JSONObject(String(bytes)).also { tab ->
                val fits = tab.getJSONArray("tuning_suggestions")
                val all = (0 until fits.length()).map(fits::getJSONObject)
                tab.put("tuning_suggestions", JSONArray(all.sortedBy { if (it.getString("preset") == "bass-4-drop-d") 0 else 1 }))
            }.toString().toByteArray()
        }
        waitUntil(10_000) { first.savedScores.value.isEmpty() }
    }

    private fun card(tag: String) = rule.onNode(
        SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-$tag")),
    )

    /** Open a recording and answer What is this?; with [toTheSong], on to Check the song. Returns the phone's copy of the recording. */
    private fun open(toTheSong: Boolean): File {
        val file = recording()
        rule.runOnUiThread { first.importUri(Uri.fromFile(file)) }
        waitForTag("fs-what-continue", 20_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        card("instrument").performClick()
        if (toTheSong) {
            rule.onNodeWithTag("fs-what-continue").performClick()
            waitForTag("fs-check-change-tuning")
            waitUntil(10_000) { first.savedScores.value.size == 1 }
        }
        val take = first.source.value!!.file!!
        assertTrue("the phone's copy is among the takes", take.isFile && take.parentFile?.name == "takes")
        return take
    }

    /**
     * The app as a new process shows it: a new view model on what the old one had saved ([stack], the
     * recording, and the song when a screen of it was open), with nothing kept in memory.
     */
    private fun afterTheProcessEnded(stack: List<Screen>): PlayViewModel {
        val old = first
        val state = SavedStateHandle(mapOf(
            "stack" to ArrayList(stack.map { it.name }),
            "source" to old.source.value?.let { SavedSource.of(it).encode() },
            "score" to old.savedScores.value.firstOrNull()?.id?.takeIf { RestoredStack.needsScore(stack) },
        ))
        SongAnswers.set(null, SongAnswer())
        lateinit var next: PlayViewModel
        rule.runOnUiThread {
            next = PlayViewModel(rule.activity.application, state)
            rule.activity.setContent { PlayTheme(dark = false, pink = false) { Product.Root(next) } }
        }
        rule.waitForIdle()
        return next
    }

    private fun jobOf(vm: PlayViewModel) = runBlocking { container.engine()!!.job(vm.result.value!!.jobId!!) }

    /** Use Drop D on Check the song: the song is written down again on the recording the computer has, and comes back. */
    private fun useDropD(vm: PlayViewModel, back: List<Screen>) {
        val before = jobOf(vm)
        rule.onNodeWithTag("fs-check-change-tuning").performClick()
        waitUntil(60_000) { vm.result.value?.jobId != before.id && vm.screen.value == back }
        waitForTag("fs-show-tab")
        val again = jobOf(vm)
        assertNotEquals(before.id, again.id)
        assertEquals("the same recording on the computer", before.audioId, again.audioId)
        assertEquals("tab", again.profile)
        // As it was made: the bass alone, not separated, now for drop D.
        assertTrue(again.stages.none { it.name == "stems" })
        val sent = tabOptions(yourInstrumentStore(rule.activity).load(), SongAnswers.of(vm.source.value))
        assertEquals(listOf("drop-d", Recording.INSTRUMENT), listOf(sent.tuning, sent.recording))
        assertEquals(YourInstrument(no.brasscribe.play.engine.FrettedInstrument.BASS_4), yourInstrumentStore(rule.activity).load())
    }

    @Test
    fun endedAtWhatIsThisTheRecordingIsStillThereAndIsAskedAboutAgain() {
        val take = open(toTheSong = false)
        val vm = afterTheProcessEnded(listOf(Screen.HOME, Screen.PROFILE))
        waitForTag("fs-what-continue", 10_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        assertEquals(listOf(Screen.HOME, Screen.PROFILE), vm.screen.value)
        pass(1500)
        checkAccessibility()
        assertTrue("the recording is kept", take.isFile)
        assertEquals(take, vm.source.value?.file)
        // The answer was in memory only: nothing is chosen, and nothing is sent until it is.
        card("instrument").assertIsNotSelected()
        card("song").assertIsNotSelected()
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        card("instrument").performClick()
        rule.onNodeWithTag("fs-what-continue").assertIsEnabled().performClick()
        waitForTag("fs-show-tab")
        assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT), vm.screen.value)
        assertTrue(jobOf(vm).stages.none { it.name == "stems" })
    }

    @Test
    fun endedWhileTheNotesWereWrittenDownWhatIsThisComesBackWithTheRecording() {
        val take = open(toTheSong = false)
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitUntil(10_000) { first.screen.value.last() == Screen.TRANSCRIBE }
        val stack = first.screen.value
        rule.runOnUiThread { first.cancelTranscription() }
        // Stopped, the take is kept in Your songs (a moment's work on the phone) before the process ends.
        waitUntil(5_000) { first.keptRecordings.value.size == 1 && first.source.value?.file == first.keptRecordings.value.single().file }
        val vm = afterTheProcessEnded(stack)
        waitForTag("fs-what-continue", 10_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        // Writing down the notes cannot be taken up again: the screen before it comes back.
        assertEquals(listOf(Screen.HOME, Screen.PROFILE), vm.screen.value)
        pass(1500)
        checkAccessibility()
        // The take moved into Your songs, and is still the recording in hand.
        val inHand = vm.source.value?.file
        assertTrue("the recording is kept ($inHand)", inHand != null && inHand.isFile && inHand != take)
        waitUntil(5_000) { vm.keptRecordings.value.any { it.file == inHand } }
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        card("song").performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        assertTrue("a full song is separated", jobOf(vm).stages.any { it.name == "stems" })
    }

    @Test
    fun endedOnCheckTheSongTheRecordingIsKeptAndTheSongCanBeWrittenDownAgain() {
        val take = open(toTheSong = true)
        val vm = afterTheProcessEnded(listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT))
        waitForTag("fs-check-change-tuning")
        assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT), vm.screen.value)
        pass(1500)
        // The song is shown again from what was saved, and the recording under it is still the one in hand.
        assertTrue("the recording is kept", take.isFile)
        assertEquals(take, vm.source.value?.file)
        rule.onNodeWithText("You can change this later.").assertIsDisplayed()
        checkAccessibility()

        // Back: What is this? has the recording, so Continue is there once the question is answered.
        rule.runOnUiThread { vm.back() }
        waitForTag("fs-what-continue", 10_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        assertTrue(rule.onAllNodesWithText("This recording is no longer on the phone. Open it again from Home.").fetchSemanticsNodes().isEmpty())
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        card("instrument").performClick()
        rule.onNodeWithTag("fs-what-continue").assertIsEnabled().performClick()
        waitForTag("fs-check-change-tuning")
        assertTrue("the recording was sent, not an empty file", take.length() > 44)

        // And from Check the song, the song is written down again for the tuning that fits.
        useDropD(vm, listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT))
        assertTrue(take.isFile)
    }

    @Test
    fun withThePhonesCopyGoneTheSongIsStillWrittenDownAgain() {
        val take = open(toTheSong = true)
        // The system cleared the app's cache while it was away.
        assertTrue(take.delete())
        val vm = afterTheProcessEnded(listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT))
        waitForTag("fs-check-change-tuning")
        // What is this? has nothing to ask about, so it is not among the screens that came back.
        assertEquals(listOf(Screen.HOME, Screen.OUTPUT), vm.screen.value)
        assertNull(vm.source.value?.file)
        rule.onNodeWithText("You can change this later.").assertIsDisplayed()
        checkAccessibility()
        useDropD(vm, listOf(Screen.HOME, Screen.OUTPUT))
    }

    @Test
    fun aSongOpenedFromYourSongsCanBeWrittenDownAgain() {
        open(toTheSong = true)
        rule.runOnUiThread { first.home() }
        waitUntil(10_000) { first.scores.value.size == 1 }
        // Check the song from the row's menu: the song has no recording in hand, and offers its change all the same.
        rule.runOnUiThread { first.openEntry(first.scores.value.single(), review = true) }
        waitForTag("fs-check-change-tuning")
        assertEquals(listOf(Screen.HOME, Screen.REVIEW), first.screen.value)
        assertNull(first.source.value?.file)
        checkAccessibility()
        useDropD(first, listOf(Screen.HOME, Screen.OUTPUT))
        // Still one song: the same one, written down again.
        waitUntil(10_000) { first.savedScores.value.size == 1 && first.savedScores.value.single().jobId == first.result.value?.jobId }
    }
}
