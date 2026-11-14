package no.kalli.brasscribe

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
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
        // Continue is docked with the one line that says why it waits: the rest of the screen is the choices'.
        whole("seat-hint")
        assertEquals("the reason Continue waits is one line", 1, textLines("seat-hint"))
        val screen = rule.activity.window.decorView.height / density
        val under = screen - node("seat-hint").boundsInWindow.top / density
        assertTrue("only the reason and Continue are docked ($under dp from the reason to the bottom edge)", under <= 130f)
        // "I conduct or listen" is the first choice, on the first screen.
        whole("seat-none")
        assertTrue("I conduct or listen is above the band", node("seat-none").boundsInWindow.bottom <= node("seat-hint").boundsInWindow.top)
    }

    private fun firstRun() {
        rule.runOnUiThread { container.updateSeat(SeatChoice.NotSet); container.firstRunDone = false; vm.finishFirstRun() }
        waitForTag("seat-continue", 5_000)
        rest()
    }

    /** The lines of the text [tag] (a text, not a button). */
    private fun textLines(tag: String): Int {
        val layouts = mutableListOf<TextLayoutResult>()
        node(tag).config[SemanticsActions.GetTextLayoutResult].action?.invoke(layouts)
        return layouts.single().lineCount
    }

    @Test
    fun onItsSideTheChoicesStartOnTheFirstScreen() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        language("nb-NO")
        firstRun()
        shot("what-do-you-play-small-landscape")
        // The lead steps aside: I conduct or listen and the first instruments are in view without scrolling.
        whole("seat-none")
        whole("instrument-bb-cornet")
        whole("seat-continue")
        assertTrue("an instrument is above the band", node("instrument-bb-cornet").boundsInWindow.bottom <= node("seat-hint").boundsInWindow.top)
    }

    @Test
    fun everyInstrumentIsAsHighAsTheOthers() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        firstRun()
        val heights = rule.onAllNodes(androidx.compose.ui.test.SemanticsMatcher("an instrument") {
            it.config.getOrElseNullable(androidx.compose.ui.semantics.SemanticsProperties.TestTag) { null }?.startsWith("instrument-") == true
        }, useUnmergedTree = true).fetchSemanticsNodes().map { it.size.height }
        assertTrue("instruments: $heights", heights.size > 4)
        assertEquals("every row is as high as the others: $heights", 1, heights.toSet().size)
    }

    @Test
    fun aChosenInstrumentFurtherDownStaysInView() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        firstRun()
        // Picked: it stays where it was tapped, in view.
        rule.onNodeWithTag("instrument-bb-bass").performScrollTo().performClick()
        rest()
        whole("instrument-bb-bass")
        // Opened again from Settings with it chosen: it is in view, not at the bottom of the list out of sight.
        val seat = container.seats.first { it.instrument == "bb-bass" }
        rule.runOnUiThread { vm.skipSeat() }
        waitUntil(5_000) { rule.onAllNodesWithTag("seat-continue").fetchSemanticsNodes().isEmpty() }
        rule.runOnUiThread {
            container.updateSeat(SeatChoice.Player(seat.id, null))
            vm.openSeatPicker(no.kalli.scribe.play.SeatPickerMode.SETTINGS)
        }
        waitForTag("seat-continue", 5_000)
        rest()
        assertTrue("it is Settings' picker, opened anew", rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isEmpty())
        shot("what-do-you-play-reopened")
        whole("instrument-bb-bass")
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
