package no.kalli.scribe.tab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * The player's fixes to a tab ([TabEdits]), on the fixture with marks (apps/fixtures/bass-line-marks, where note 5 is
 * doubtful): a note moved to another string, kept, left out, made a ghost note, and taken back, in the tab alone and
 * in tab with notation; and what the page shows of each.
 */
class TabEditsTest {
    private val root: File? = System.getProperty("scribe.sounds")?.let { File(it).parentFile }

    private fun page(name: String = "tab"): String {
        val file = root?.resolve("apps/fixtures/bass-line-marks/$name.musicxml")
        assumeTrue("apps/fixtures/bass-line-marks is not in this checkout", file?.isFile == true)
        return file!!.readText()
    }

    private fun TabIndex.note(n: Int) = of(n).first { it.staff == markStaff }
    private fun marks(xml: String) = Regex("""<words>\?</words>""").findAll(xml).count()

    @Test
    fun aFileWithoutFixesIsShownAsItIs() {
        val xml = page()
        assertFalse(TabEdits.changed(xml))
        assertEquals(xml, TabEdits.shown(xml))
        assertEquals(NoteEdit(), TabEdits.of(xml, 5))
        assertTrue(TabEdits.leftOut(xml).isEmpty())
    }

    @Test
    fun aNoteIsMovedToAnotherStringAndBack() {
        val xml = page()
        val before = TabIndex.parse(xml)
        assertEquals(3 to 2, before.note(4).let { it.string to it.fret })
        // B on the A string, fret 2, is B on the E string, fret 7.
        val moved = TabEdits.place(xml, 4, 4, 7)
        val after = TabIndex.parse(TabEdits.shown(moved))
        assertEquals(4 to 7, after.note(4).let { it.string to it.fret })
        assertEquals(before.note(4).pitch, after.note(4).pitch)
        assertEquals(NoteEdit(was = 3 to 2), TabEdits.of(moved, 4))
        assertTrue(TabEdits.changed(moved))
        // Nothing else is touched: every other note is where it was, and the file differs in that one note.
        assertEquals(before.pieces.filter { it.note != 4 }, after.pieces.filter { it.note != 4 })
        assertEquals(xml.lines().size + 1, moved.lines().size)
        // Moved again, it still remembers where Fretscribe wrote it; moved back there, it is as it was.
        val again = TabEdits.place(moved, 4, 3, 2)
        assertEquals(xml, again)
        assertEquals(xml, TabEdits.revert(moved, 4))
        assertEquals(NoteEdit(was = 3 to 2), TabEdits.of(TabEdits.place(TabEdits.place(xml, 4, 4, 7), 4, 2, 9).also {
            assertEquals(2 to 9, TabIndex.parse(it).note(4).let { p -> p.string to p.fret })
        }, 4))
    }

    @Test
    fun aDoubtfulNoteThatIsKeptLosesItsMarkAndCanHaveItBack() {
        val xml = page()
        assertEquals(0.31, TabIndex.parse(xml).note(5).confidence!!, 1e-9)
        val before = marks(xml)
        val kept = TabEdits.keep(xml, 5)
        assertEquals(NoteEdit(checked = true), TabEdits.of(kept, 5))
        // The file keeps the mark and the colour (it is how Fretscribe wrote it); what is shown has neither.
        assertEquals(before, marks(kept))
        val shown = TabEdits.shown(kept)
        assertEquals(before - 1, marks(shown))
        assertNull(TabIndex.parse(shown).note(5).confidence)
        assertFalse(Regex("""<note color=[^>]*>(?:(?!</note>).)*<\?fretted-note 5\?>""", RegexOption.DOT_MATCHES_ALL).containsMatchIn(shown))
        assertEquals(TabIndex.parse(xml).pieces.map { it.copy(confidence = null) }, TabIndex.parse(shown).pieces.map { it.copy(confidence = null) })
        // The other doubtful note keeps its mark.
        val other = TabIndex.parse(xml).pieces.first { it.confidence != null && it.note != 5 }.note
        assertEquals(TabIndex.parse(xml).note(other).confidence, TabIndex.parse(shown).note(other).confidence)
        // Moving a doubtful note is looking at it.
        assertTrue(TabEdits.of(TabEdits.place(xml, 5, 4, 7), 5).checked)
        assertEquals(xml, TabEdits.revert(kept, 5))
        assertEquals(xml, TabEdits.revert(TabEdits.place(xml, 5, 4, 7), 5))
    }

    @Test
    fun aNoteLeftOutIsARestOnThePageAndStaysInTheFile() {
        val xml = page()
        val before = TabIndex.parse(xml)
        val out = TabEdits.leaveOut(xml, 4)
        assertEquals(listOf(4), TabEdits.leftOut(out))
        assertTrue(TabEdits.of(out, 4).leftOut)
        // In the file the note is still there, with its place.
        assertEquals(before.pieces, TabIndex.parse(out).pieces)
        val shown = TabIndex.parse(TabEdits.shown(out))
        assertTrue(shown.of(4).isEmpty())
        assertEquals(before.pieces.filter { it.note != 4 }, shown.pieces)
        // The bars are as long as they were: a rest stands where the note was.
        assertEquals(before.measures, shown.measures)
        assertTrue(TabEdits.shown(out).contains("<note><rest/><duration>24</duration><voice>1</voice><type>quarter</type></note>"))
        assertEquals(xml, TabEdits.leaveOut(out, 4, out = false))
        // A doubtful note left out takes its "?" with it.
        assertEquals(marks(xml) - 1, marks(TabEdits.shown(TabEdits.leaveOut(xml, 5))))
    }

    @Test
    fun aNoteOfAChordIsLeftOutWithoutTheOthers() {
        fun note(n: Int, string: Int, chord: Boolean, extra: String = "") = """
      <note>${if (chord) "\n        <chord/>" else ""}
        <pitch><step>E</step><octave>2</octave></pitch>
        <duration>24</duration>
        <voice>1</voice>
        <type>quarter</type>
        <notations><technical><string>$string</string><fret>0</fret></technical></notations>
        <?fretted-note $n?>$extra
      </note>"""
        val xml = "<part><measure number=\"1\">" + note(0, 3, false) + note(1, 2, true) + note(2, 1, true) + "\n</measure></part>"
        fun strings(x: String) = Regex("<string>(\\d)</string>").findAll(TabEdits.shown(x)).map { it.groupValues[1].toInt() }.toList()
        fun chords(x: String) = Regex("<chord/>").findAll(TabEdits.shown(x)).count()
        // The first of the chord: the next one is the chord's first now.
        assertEquals(listOf(2, 1), strings(TabEdits.leaveOut(xml, 0)))
        assertEquals(1, chords(TabEdits.leaveOut(xml, 0)))
        // One in the middle, and the last.
        assertEquals(listOf(3, 1), strings(TabEdits.leaveOut(xml, 1)))
        assertEquals(1, chords(TabEdits.leaveOut(xml, 1)))
        assertEquals(listOf(3, 2), strings(TabEdits.leaveOut(xml, 2)))
        // All of them: one rest.
        val none = TabEdits.shown(TabEdits.leaveOut(TabEdits.leaveOut(TabEdits.leaveOut(xml, 0), 1), 2))
        assertEquals(1, Regex("<rest/>").findAll(none).count())
        assertEquals(0, Regex("<pitch>").findAll(none).count())
    }

    @Test
    fun aGhostNoteHasAnXForAHead() {
        val xml = page()
        val ghost = TabEdits.ghost(xml, 4, true)
        assertTrue(TabEdits.of(ghost, 4).ghost)
        val shown = TabEdits.shown(ghost)
        val piece = Regex("""<note\b[^>]*>(?:(?!</note>).)*<\?fretted-note 4\?>.*?</note>""", RegexOption.DOT_MATCHES_ALL).find(shown)!!.value
        assertTrue(piece, piece.contains("<notehead>x</notehead>"))
        assertTrue(piece.indexOf("<notehead>") < piece.indexOf("<notations>"))
        // The page's index says so, and nothing else of the note has changed.
        assertTrue(TabIndex.parse(shown).note(4).ghost)
        assertEquals(TabIndex.parse(xml).pieces, TabIndex.parse(shown).pieces.map { it.copy(ghost = false) })
        assertEquals(xml, TabEdits.ghost(ghost, 4, false))
    }

    @Test
    fun inTabWithNotationBothStavesFollow() {
        val xml = page("tab-and-notation")
        val index = TabIndex.parse(xml)
        assertEquals(2, index.of(5).size)
        val moved = TabIndex.parse(TabEdits.shown(TabEdits.place(xml, 5, 4, 7)))
        // The tab staff has the new place; the notation staff has the same note, and neither is doubtful any more.
        assertEquals(4 to 7, moved.note(5).let { it.string to it.fret })
        assertTrue(moved.of(5).all { it.confidence == null })
        assertEquals(index.of(5).map { it.pitch }, moved.of(5).map { it.pitch })
        val out = TabIndex.parse(TabEdits.shown(TabEdits.leaveOut(xml, 5)))
        assertTrue(out.of(5).isEmpty())
        assertEquals(index.measures, out.measures)
        assertEquals(xml, TabEdits.revert(TabEdits.leaveOut(TabEdits.place(xml, 5, 4, 7), 5), 5))
    }
}
