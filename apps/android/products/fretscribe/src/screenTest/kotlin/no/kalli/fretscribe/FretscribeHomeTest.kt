package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenTest
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Home offers no "Open a tab" until an imported tab opens in the tab view: today a MusicXML file would open in
 * Brasscribe's score screen. The other ways in stay. With a song in Your songs, the song is on the first screen of a
 * small phone, upright and on its side.
 */
@RunWith(AndroidJUnit4::class)
class FretscribeHomeTest : ScreenTest() {
    private fun home(): String {
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
        return shown()
    }

    /** A guitar line from the test computer, through What is this?, to Check the song: a song in Your songs. */
    private fun aSong() {
        computer("guitar-line")
        openFromHome(recording("Guitar line.wav"))
        waitForTag("fs-what-continue", 20_000)
        waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        rule.onNode(androidx.compose.ui.test.SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.Role, androidx.compose.ui.semantics.Role.RadioButton) and
            androidx.compose.ui.test.hasAnyAncestor(androidx.compose.ui.test.hasTestTag("fs-what-instrument"))).performScrollTo().performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        waitUntil(10_000) { vm.savedScores.value.isNotEmpty() }
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { vm.scores.value.isNotEmpty() && rule.onAllNodesWithTag("score-options").fetchSemanticsNodes().isNotEmpty() }
        rest()
    }

    /** The song's row in Your songs, read as one, is in view and whole. */
    private fun theSongIsWhole() {
        val row = rule.onNode(androidx.compose.ui.test.hasAnyDescendant(androidx.compose.ui.test.hasTestTag("score-options")) and
            androidx.compose.ui.test.hasClickAction()).fetchSemanticsNode()
        assertEquals("the song is in view, whole", row.size.height.toFloat(), row.boundsInWindow.height, 1f)
    }

    @Test
    fun aSmallPhoneShowsTheSongWithoutScrolling() {
        org.junit.Assume.assumeTrue("this device keeps its own size", no.kalli.scribe.play.screen.ScreenDevice.size(rule, 360, 640))
        aSong()
        shot("home-with-a-song-small")
        theSongIsWhole()
    }

    @Test
    fun onItsSideTheSongIsOnTheFirstScreen() {
        org.junit.Assume.assumeTrue("this device keeps its own size", no.kalli.scribe.play.screen.ScreenDevice.size(rule, 640, 360))
        language("nb-NO")
        aSong()
        shot("home-with-a-song-small-landscape")
        theSongIsWhole()
        checkAccessibility()
    }

    @Test
    fun homeHasNoOpenATab() {
        val en = home()
        assertTrue(en, en.contains("Record with the microphone"))
        assertFalse(en, en.contains("Open a tab"))
        assertFalse(en, en.contains("MusicXML"))
        language("nb")
        val nb = home()
        assertTrue(nb, nb.contains("Spill inn med mikrofonen"))
        assertFalse(nb, nb.contains("Åpne en tab"))
        assertFalse(nb, nb.contains("MusicXML"))
    }
}
