package no.kalli.fretscribe

import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.tab.TabIndex
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Tuning and capo from the tab, on a fixture computer: another tuning writes the tab again on the phone (a note that
 * had no place gets one), and a capo keeps the sound or the shapes; the page, its header and the saved song follow.
 */
@RunWith(AndroidJUnit4::class)
class TuningSheetTest : TabScreenTest() {
    override val shots = "fretscribe/tuning"

    private val xml get() = vm.result.value!!.musicXml
    private fun index() = TabIndex.parse(xml)
    private fun there(tag: String) = rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    private fun notes(index: TabIndex) = index.pieces.filter { it.staff == index.markStaff && it.first }

    @Test
    fun anotherTuningWritesTheTabAgainOnThePhone() {
        assumeTrue("the core that writes a tab is not in this build", TabRewrite.available)
        // The bass line has a D below a bass in standard tuning: a note with no place.
        computer("bass-line-marks")
        showTheTab()
        val before = index()
        rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Tuning: Standard, no capo")
        assertTrue(there("fs-tab-no-place"))
        rule.onNodeWithTag("fs-tab-tuning").performClick()
        waitForTag("fs-tuning-write", 5_000)
        // The bass's tunings, the one the tab is in chosen; nothing to write yet, and no capo for a bass.
        rule.onNodeWithTag("fs-tuning-standard").assertIsSelected()
        rule.onNodeWithTag("fs-tuning-write").assertIsNotEnabled()
        assertFalse(there("fs-tuning-capo-up"))
        checkAccessibility()
        shot("tuning-and-capo")

        rule.onNodeWithTag("fs-tuning-drop-d").performScrollTo().performClick()
        rule.onNodeWithTag("fs-tuning-drop-d").assertIsSelected()
        rule.onNodeWithTag("fs-tuning-write").assertIsEnabled().performClick()
        waitUntil(20_000) { !there("fs-tuning-write") && TabRewrite.rewritten(xml) }
        // In drop D the low D is the open fourth string: every note has a place, and the header says the tuning.
        val after = index()
        assertTrue(after.noPlace.isEmpty())
        assertEquals(notes(before).size + 1, notes(after).size)
        assertEquals(4 to 0, notes(after).single { it.pitch == 26 }.let { it.string to it.fret })
        engraved()
        waitUntil(10_000) { runCatching { rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Tuning: Drop D, no capo") }.isSuccess }
        waitUntil(10_000) { !there("fs-tab-no-place") }
        rule.onNodeWithTag("fs-tab-marked").assertTextContains("2 notes marked ?", substring = true)
        assertTrue(vm.result.value!!.changedOnPhone)
        checkAccessibility()

        // The song is saved as it is now: opened again from Your songs it is in drop D.
        val written = xml
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { vm.scores.value.isNotEmpty() }
        settle()
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        assertEquals(written, xml)
        waitUntil(10_000) { runCatching { rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Tuning: Drop D, no capo") }.isSuccess }
    }

    @Test
    fun aCapoKeepsTheSoundOrTheShapes() {
        assumeTrue("the core that writes a tab is not in this build", TabRewrite.available)
        computer("guitar-line")
        showTheTab()
        val before = index()
        rule.onNodeWithTag("fs-tab-tuning").performClick()
        waitForTag("fs-tuning-capo-up", 5_000)
        rule.onNodeWithTag("fs-tuning-capo").assertTextContains("None")
        // What is kept is asked once the capo has been moved: until then it is off.
        rule.onNodeWithTag("fs-tuning-keep-shapes").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("fs-tuning-capo-down").assertIsNotEnabled()
        repeat(2) { rule.onNodeWithTag("fs-tuning-capo-up").performScrollTo().performClick() }
        rule.onNodeWithTag("fs-tuning-capo").assertTextContains("Fret 2")
        rule.onNodeWithTag("fs-tuning-keep-shapes").performScrollTo().assertIsEnabled()
        rule.onNodeWithTag("fs-tuning-keep-sound").performScrollTo().assertIsSelected()
        checkAccessibility()
        shot("capo-moved")
        // Keep the shapes: the same strings and frets, two semitones higher, and the header says the capo.
        rule.onNodeWithTag("fs-tuning-keep-shapes").performScrollTo().performClick()
        rule.onNodeWithTag("fs-tuning-write").performClick()
        waitUntil(20_000) { !there("fs-tuning-write") && TabRewrite.rewritten(xml) }
        val shapes = index()
        assertEquals(2, shapes.capo)
        assertEquals(notes(before).map { it.string to it.fret }, notes(shapes).map { it.string to it.fret })
        assertEquals(notes(before).map { it.pitch + 2 }, notes(shapes).map { it.pitch })
        engraved()
        waitUntil(10_000) { runCatching { rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Tuning: Standard, capo 2") }.isSuccess }

        // The capo taken off again with the sound kept: the notes stay two semitones up, at new frets.
        rule.onNodeWithTag("fs-tab-tuning").performClick()
        waitForTag("fs-tuning-capo-down", 5_000)
        rule.onNodeWithTag("fs-tuning-capo").assertTextContains("Fret 2")
        repeat(2) { rule.onNodeWithTag("fs-tuning-capo-down").performScrollTo().performClick() }
        rule.onNodeWithTag("fs-tuning-keep-sound").performScrollTo().assertIsSelected()
        rule.onNodeWithTag("fs-tuning-write").performClick()
        waitUntil(20_000) { !there("fs-tuning-write") && index().capo == 0 }
        val sound = index()
        // (The line has notes below and above the guitar, named over a "!": they are notes of the song all the same.)
        fun every(index: TabIndex) = (notes(index).map { it.pitch } + index.noPlace.flatMap { n -> n.names.mapNotNull(TabRewrite::pitchOf) }).sorted()
        assertEquals(every(shapes), every(sound))
        assertTrue(notes(sound).map { it.string to it.fret } != notes(shapes).map { it.string to it.fret })
    }

    /** On a small phone and with the largest text, a guitar's sheet keeps Write and the capo in view: the tunings scroll. */
    @Test
    fun onASmallPhoneWriteAndTheCapoAreInView() {
        assumeTrue("the core that writes a tab is not in this build", TabRewrite.available)
        assumeTrue("this device keeps its own size", no.kalli.scribe.play.screen.ScreenDevice.size(rule, 360, 640))
        computer("guitar-line")
        textSize(2.0f)
        showTheTab()
        rule.onNodeWithTag("fs-tab-tuning").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.OnClick)
        waitForTag("fs-tuning-write", 5_000)
        rest()
        val window = rule.activity.window.decorView.let { androidx.compose.ui.geometry.Rect(0f, 0f, it.width.toFloat(), it.height.toFloat()) }
        for (tag in listOf("fs-tuning-write", "fs-tuning-cancel", "fs-tuning-capo-up", "fs-tuning-capo-down")) {
            val b = rule.onNodeWithTag(tag).fetchSemanticsNode().boundsInWindow
            assertTrue("$tag is in view ($b of $window)", b.top >= window.top && b.bottom <= window.bottom && b.height > 0f)
        }
        checkAccessibility()
        shot("guitar-small-200")
        textSize(1.0f)
    }

    /**
     * A tab with fixes written again for another tuning: with a note moved, it asks first, naming it, and Cancel keeps
     * everything; written, the note left out and the ghost note go with their notes, and the moved one is back.
     */
    @Test
    fun aTabWithFixesAsksBeforeItsMovedNotesGoAndKeepsTheRest() {
        assumeTrue("the core that writes a tab is not in this build", TabRewrite.available)
        computer("guitar-line")
        showTheTab()
        val pieces = notes(index()).filter { it.string != null && it.pitch >= 45 }
        val (out, moved) = pieces[0] to pieces[1]
        val elsewhere = FixNote.places(moved.pitch, SongFacts.openStrings(xml)).first { it.string != moved.string }
        rule.runOnUiThread {
            vm.changeScore(no.kalli.scribe.tab.TabEdits.place(no.kalli.scribe.tab.TabEdits.leaveOut(xml, out.note), moved.note, elsewhere.string, elsewhere.fret))
        }
        waitUntil(10_000) { no.kalli.scribe.tab.TabEdits.moved(xml) == 1 }
        engraved()
        val fixed = xml
        rule.onNodeWithTag("fs-tab-tuning").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.OnClick)
        waitForTag("fs-tuning-write", 5_000)
        rule.onNodeWithTag("fs-tuning-drop-d").performScrollTo().performClick()
        rule.onNodeWithTag("fs-tuning-write").performClick()
        waitForTag("fs-tuning-again", 5_000)
        rule.onNode(androidx.compose.ui.test.hasText("The note you moved goes back to where Fretscribe wrote it", substring = true)).assertExists()
        checkAccessibility()
        shot("moved-notes-asked")
        rule.onNodeWithTag("fs-tuning-again-cancel").performClick()
        waitUntil(5_000) { !there("fs-tuning-again") }
        settle()
        assertEquals(fixed, xml)
        rule.onNodeWithTag("fs-tuning-write").performClick()
        waitForTag("fs-tuning-again", 5_000)
        rule.onNodeWithTag("fs-tuning-again-write").performClick()
        waitUntil(20_000) { !there("fs-tuning-write") && TabRewrite.rewritten(xml) }
        assertEquals(0, no.kalli.scribe.tab.TabEdits.moved(xml))
        assertEquals(1, no.kalli.scribe.tab.TabEdits.leftOut(xml).size)
        engraved()
        waitForTag("fs-tab-left-out", 10_000)
    }
}
