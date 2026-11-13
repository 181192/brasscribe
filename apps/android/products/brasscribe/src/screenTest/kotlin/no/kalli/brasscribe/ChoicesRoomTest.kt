package no.kalli.brasscribe

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.text.TextLayoutResult
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.Screen
import no.kalli.scribe.play.SeatChoice
import no.kalli.scribe.play.Source
import no.kalli.scribe.play.SourceKind
import no.kalli.scribe.play.Where
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * What do you play? and Share or print on a small phone with larger text in bokmål: the choices have the screen, with
 * the one button docked under them, and Share and Save are whole, each with its words on one line.
 */
@RunWith(AndroidJUnit4::class)
class ChoicesRoomTest : ScreenTest() {
    @After
    fun clean() = rule.runOnUiThread { container.firstRunDone = true; vm.home() }

    private val density get() = rule.density.density
    private fun node(tag: String): SemanticsNode = rule.onNodeWithTag(tag, useUnmergedTree = true).fetchSemanticsNode()
    private fun whole(tag: String) = node(tag).let { assertEquals("$tag is in view, whole", it.size.height.toFloat(), it.boundsInWindow.height, 1f) }

    /** The lines the words of the button [tag] take. */
    private fun lines(tag: String): Int {
        val text = rule.onAllNodes(androidx.compose.ui.test.hasAnyAncestor(androidx.compose.ui.test.hasTestTag(tag)) and
            androidx.compose.ui.test.SemanticsMatcher.keyIsDefined(SemanticsActions.GetTextLayoutResult), useUnmergedTree = true).fetchSemanticsNodes().first()
        val layouts = mutableListOf<TextLayoutResult>()
        text.config[SemanticsActions.GetTextLayoutResult].action?.invoke(layouts)
        return layouts.single().lineCount
    }

    @Test
    fun whatDoYouPlayKeepsTheScreenForTheInstruments() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        rule.runOnUiThread { container.updateSeat(SeatChoice.NotSet); container.firstRunDone = false; vm.finishFirstRun() }
        waitForTag("seat-continue", 5_000)
        rest()
        shot("what-do-you-play-small")
        whole("seat-continue")
        // Continue alone is docked: the band is a button high, and the rest of the screen is the choices'.
        val screen = rule.activity.window.decorView.height / density
        val under = screen - node("seat-continue").boundsInWindow.top / density
        assertTrue("only Continue is docked ($under dp from its top to the bottom edge)", under <= 100f)
        // "I conduct or listen" is among the choices, not in the band.
        assertTrue("I conduct or listen is a choice", rule.onAllNodesWithTag("seat-none").fetchSemanticsNodes().isNotEmpty())
    }

    private fun shareOrPrint() {
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        rule.runOnUiThread { vm.navigate(Screen.SCORE) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.navigate(Screen.EXPORT) }
        waitForTag("share", 10_000)
        rest()
    }

    @Test
    fun shareAndSaveHaveTheirWordsOnOneLine() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        shareOrPrint()
        shot("share-or-print-small")
        for (tag in listOf("print", "share", "save")) {
            whole(tag)
            assertEquals("$tag has its words on one line", 1, lines(tag))
        }
        assertNoTextIsClipped()
    }

    @Test
    fun onANarrowPhoneTheyStillHaveTheirWordsOnOneLine() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 320, 568))
        textSize(1.3f)
        language("nb-NO")
        shareOrPrint()
        shot("share-or-print-narrow")
        for (tag in listOf("print", "share", "save")) {
            whole(tag)
            assertEquals("$tag has its words on one line", 1, lines(tag))
        }
    }
}
