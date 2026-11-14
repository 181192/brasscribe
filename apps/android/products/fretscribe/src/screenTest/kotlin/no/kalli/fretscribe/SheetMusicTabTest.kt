package no.kalli.fretscribe

import no.kalli.scribe.play.*
import no.kalli.scribe.tab.*

import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.FrettedInstrument
import no.kalli.scribe.engine.JobCreate
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Printed music read from pages is a tab in Fretscribe, for the player's instrument (the fixture computer answers as
 * the engine did for a short guitar line): Check the song, then the tab, which has no recording to play along with
 * and says so.
 */
@RunWith(AndroidJUnit4::class)
class SheetMusicTabTest : ScreenTest() {
    @Before
    fun aGuitarInDropD() {
        yourInstrumentStore(rule.activity).save(YourInstrument(FrettedInstrument.GUITAR_6, tuning = "drop-d"))
    }

    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        container.fixtureSource = null
        yourInstrumentStore(rule.activity).save(YourInstrument.DEFAULT)
        TabPlaces.forget()
    }

    private fun shows(id: Int) = rule.onAllNodesWithText(text(id)).fetchSemanticsNodes().isNotEmpty()

    @Test
    fun thePagesBecomeATabForThePlayersInstrument() {
        computer("guitar-line")
        pagesInHand(2)
        // What goes with the pages: the instrument as it is set, and nothing that is asked about a recording.
        val options = Fretscribe.pagesOptions(vm)
        assertEquals(FrettedInstrument.GUITAR_6 to "drop-d", options.instrument to options.tuning)
        assertNull(options.recording)
        assertNull(options.chords)

        rule.onNodeWithTag("pages-read").performClick()
        // Check the song comes first, as after a recording; What is this? is never asked of a page.
        waitForTag("fs-show-tab")
        assertEquals(listOf(Screen.HOME, Screen.OUTPUT), vm.screen.value)
        val read = vm.result.value!!
        assertEquals(Profile.SHEET_TAB, read.profile)
        checkAccessibility()
        // Written again from here, it stays a tab read from its pages.
        assertEquals("sheet-tab", Fretscribe.job(vm, JobCreate(read.audioId, read.profile.id)).profile)

        rule.onNodeWithTag("fs-show-tab").performClick()
        waitForTag("fs-tab", 30_000)
        waitUntil(30_000) { TabScreenProbe.view?.let { it.engraving.value != null && it.scale == TabScreenProbe.wanted } == true }
        waitUntil(30_000) { ViewModelProvider(rule.activity)[PracticeModel::class.java].recording != RecordingState.LOOKING }
        rest()
        // There is no recording behind it: the tab's own notes play, and Sound says why there is no recording, with
        // nothing to fetch from the computer.
        waitForTag("fs-practice-sound", 20_000)
        rule.onNodeWithTag("fs-practice-sound").performClick()
        waitUntil(10_000) { shows(R.string.fs_practice_from_pages) }
        assertEquals(0, rule.onAllNodesWithTag("fs-practice-get").fetchSemanticsNodes().size)
        checkAccessibility()
        rule.onNodeWithTag("fs-sound-done").performClick()
        rest()

        // Kept in Your songs like any other.
        waitUntil(10_000) { vm.savedScores.value.any { it.jobId == read.jobId && it.profile == "sheet-tab" } }
    }

    /**
     * A tab read from pages, opened from Your songs once the computer no longer holds those pages (here: another
     * computer, which never had them), and written again as Check the song asks: the phone let go of the pages when
     * the tab was made, so it says they must be sent again, and nothing of a recording.
     */
    @Test
    fun writtenAgainWhenTheComputerNoLongerHasThePagesItSaysToSendThemAgain() {
        computer("guitar-line")
        pagesInHand(1)
        rule.onNodeWithTag("pages-read").performClick()
        waitForTag("fs-show-tab")
        val job = vm.result.value!!.jobId
        waitUntil(10_000) { vm.savedScores.value.any { it.jobId == job } }
        rule.runOnUiThread { vm.home() }
        computer("guitar-line")
        rule.runOnUiThread { vm.openSavedScore(vm.savedScores.value.first { it.jobId == job }) }
        waitUntil(20_000) { vm.result.value?.profile == Profile.SHEET_TAB && vm.screen.value.last() == Screen.SCORE }

        rule.runOnUiThread {
            SongAnswers.set(vm.source.value, SongAnswer(again = pagesOptions(tabOptions(yourInstrumentStore(rule.activity).load(), SongAnswer())).copy(capo = 2)))
            vm.chooseProfile(Profile.SHEET_TAB)
            vm.startTranscription()
        }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM }
        rule.waitForIdle()
        assertTrue(shown(), shows(R.string.error_pages_gone))
        // (The only recording it names is in the name of Home's way in.)
        assertTrue(shown(), !shows(R.string.error_recording_gone) && !shown().contains("this recording"))
        assertEquals(R.string.error_pages_gone, ErrorWords.of(PagesGoneException()))
        checkAccessibility()
    }
}
