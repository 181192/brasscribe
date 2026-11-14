package no.kalli.fretscribe

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.click
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.tab.NoteEdit
import no.kalli.scribe.tab.TabEdits
import no.kalli.scribe.tab.TabIndex
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Fix a note, on a fixture computer (apps/fixtures/bass-line-marks: note 5, in bar 3, is doubtful): opened from a mark
 * and by a tap on a fret number, a note is moved to another string, kept, made a ghost note, left out and put back, and
 * taken back to what Fretscribe wrote. Each fix is on the page at once and is saved with the song.
 */
@RunWith(AndroidJUnit4::class)
class FixNoteTest : TabScreenTest() {
    override val shots = "fretscribe/fix-a-note"

    private val xml get() = vm.result.value!!.musicXml
    private fun piece(note: Int) = TabIndex.parse(TabEdits.shown(xml)).let { i -> i.of(note).first { it.staff == i.markStaff } }
    private fun there(tag: String) = rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()

    /** The page has been engraved again with what [seen] asks of alphaTab's score. */
    private fun engravedWith(what: String, seen: (alphaTab.model.Score) -> Boolean) =
        waitUntil(30_000) { TabScreenProbe.view?.engraved?.let(seen) == true }

    /** The notes alphaTab engraves on the tab: fret, and whether it is a dead note. */
    private fun frets(score: alphaTab.model.Score): List<Pair<Int, Boolean>> {
        val out = ArrayList<Pair<Int, Boolean>>()
        for (bar in score.tracks[0].staves[0].bars) for (voice in bar.voices) for (beat in voice.beats) for (note in beat.notes) out += note.fret.toInt() to note.isDead
        return out
    }

    @Test
    fun aDoubtfulNoteIsMovedKeptAndTakenBackFromItsMark() {
        computer("bass-line-marks")
        showTheTab()
        val before = xml
        rule.onNodeWithTag("fs-tab-marked").assertTextContains("2 notes marked ?", substring = true)
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo().performClick()
        waitForTag("fs-tab-note-fix", 5_000)
        rule.onNodeWithTag("fs-tab-note-fix").performClick()
        waitForTag("fs-fix-done", 5_000)
        // The note, and every place its pitch can be played: B on the A string at fret 2, or on the E string at fret 7.
        rule.onNodeWithTag("fs-fix-note-5").assertTextContains("Bar 3, beat 2. 3rd string, fret 2, B.")
        rule.onNodeWithTag("fs-fix-place-5-3").assertIsSelected().assertTextContains("3rd string, fret 2")
        rule.onNodeWithTag("fs-fix-place-5-4").assertTextContains("4th string, fret 7")
        assertFalse(there("fs-fix-place-5-2"))
        assertFalse(there("fs-fix-revert-5"))
        checkAccessibility()
        shot("fix-a-note")

        // Moved to the E string: on the page at once, no longer doubtful, and saved with the song.
        rule.onNodeWithTag("fs-fix-place-5-4").performClick()
        waitUntil(10_000) { xml != before }
        assertEquals(4 to 7, piece(5).let { it.string to it.fret })
        assertEquals(NoteEdit(was = 3 to 2, checked = true), TabEdits.of(xml, 5))
        assertTrue(vm.result.value!!.changedOnPhone)
        engravedWith("fret 7") { frets(it)[5].first == 7 }
        rule.onNodeWithTag("fs-fix-place-5-4").assertIsSelected()
        rule.onNodeWithTag("fs-fix-note-5").assertTextContains("Bar 3, beat 2. 4th string, fret 7, B.")
        rule.onNodeWithTag("fs-fix-was-5").assertTextContains("Fretscribe wrote it on the 3rd string, fret 2.")
        waitUntil(10_000) { runCatching { rule.onNodeWithTag("fs-tab-marked").assertTextContains("1 note marked ?", substring = true) }.isSuccess }

        // Back to Fretscribe's version: where it was, doubtful again.
        rule.onNodeWithTag("fs-fix-revert-5").performScrollTo().performClick()
        waitUntil(10_000) { xml == before }
        engravedWith("fret 2") { frets(it)[5].first == 2 }
        rule.onNodeWithTag("fs-fix-place-5-3").assertIsSelected()

        // Kept as it is: the "?" goes, the place stays.
        rule.onNodeWithTag("fs-fix-keep-5").performScrollTo().performClick()
        waitUntil(10_000) { TabEdits.of(xml, 5).checked }
        assertEquals(3 to 2, piece(5).let { it.string to it.fret })
        assertEquals(null, piece(5).confidence)
        waitUntil(10_000) { !there("fs-fix-keep-5") }
        rule.onNodeWithTag("fs-fix-done").performScrollTo().performClick()
        waitUntil(5_000) { !there("fs-fix-done") }

        // The fix is the song's: opened again from Your songs, the note is still kept.
        val fixed = xml
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { vm.scores.value.isNotEmpty() }
        settle()
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        assertEquals(fixed, xml)
        assertTrue(TabEdits.of(xml, 5).checked)
        waitUntil(10_000) { runCatching { rule.onNodeWithTag("fs-tab-marked").assertTextContains("1 note marked ?", substring = true) }.isSuccess }
    }

    @Test
    fun aTapOnAFretNumberOpensItsNoteWhichIsMadeAGhostNoteLeftOutAndPutBack() {
        computer("bass-line-marks")
        val tab = showTheTab()
        val before = xml
        // The first note of the page: its beat's place in the first bar, as alphaTab laid it out.
        val bar = tab.engraving.value!!.bar(0)!!
        val stop = bar.stops.first()
        rule.onNodeWithTag("fs-tab-page").performTouchInput { click(Offset(stop.left + stop.width / 2, (bar.top + bar.bottom) / 2)) }
        waitForTag("fs-fix-done", 5_000)
        rule.onNodeWithTag("fs-fix-note-0").assertTextContains("Bar 1, beat 1.", substring = true)
        // A tap beside the bars opens nothing.
        rule.onNodeWithTag("fs-fix-done").performScrollTo().performClick()
        waitUntil(5_000) { !there("fs-fix-done") }
        rule.onNodeWithTag("fs-tab-page").performTouchInput { click(Offset(2f, bar.top)) }
        settle()
        assertFalse(there("fs-fix-done"))

        rule.onNodeWithTag("fs-tab-page").performTouchInput { click(Offset(stop.left + stop.width / 2, (bar.top + bar.bottom) / 2)) }
        waitForTag("fs-fix-done", 5_000)
        // A ghost note: an x on the page.
        rule.onNodeWithTag("fs-fix-ghost-0").performScrollTo().assertIsOff().performClick()
        waitUntil(10_000) { TabEdits.of(xml, 0).ghost }
        engravedWith("a dead note") { frets(it)[0].second }
        rule.onNodeWithTag("fs-fix-ghost-0").assertIsOn().performClick()
        waitUntil(10_000) { xml == before }
        engravedWith("an ordinary note") { !frets(it)[0].second }

        // Left out: the sheet closes, the page has a note less, and the header counts it.
        val notes = frets(TabScreenProbe.view!!.engraved!!).size
        rule.onNodeWithTag("fs-fix-leave-out-0").performScrollTo().performClick()
        waitUntil(10_000) { TabEdits.leftOut(xml) == listOf(0) }
        waitUntil(5_000) { !there("fs-fix-done") }
        engravedWith("a note less") { frets(it).size == notes - 1 }
        waitForTag("fs-tab-left-out", 10_000)
        rule.onNodeWithTag("fs-tab-left-out").assertTextContains("1 note left out", substring = true)
        checkAccessibility()
        // Put back from the list of the notes left out.
        rule.onNodeWithTag("fs-tab-left-out").performClick()
        waitForTag("fs-fix-put-back-0", 5_000)
        checkAccessibility()
        shot("notes-left-out")
        rule.onNodeWithTag("fs-fix-put-back-0").performClick()
        waitUntil(10_000) { xml == before }
        waitUntil(10_000) { !there("fs-tab-left-out") && !there("fs-fix-put-back-0") }
        engravedWith("every note") { frets(it).size == notes }
    }
}
