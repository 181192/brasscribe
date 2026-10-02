package no.brasscribe.play.fret

import no.brasscribe.play.engine.Tab
import no.brasscribe.play.model.BrasscribeJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * Which drawn note is which note of the tab's data: the index read from tab.musicxml ([TabIndex]) and the
 * marks made from it ([TabMarks]), on the recorded fixtures (apps/fixtures/bass-line and bass-line-marks)
 * and on small documents written here as the core writes them (core/target-fretted/README.md).
 */
class TabIndexTest {
    private val root: File? = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }

    private fun fixture(name: String): Pair<String, Tab> {
        val dir = root?.resolve("apps/fixtures/$name")
        assumeTrue("apps/fixtures/$name is not in this checkout", dir?.isDirectory == true)
        return File(dir, "tab.musicxml").readText() to BrasscribeJson.decodeFromString(Tab.serializer(), File(dir, "tab.json").readText())
    }

    /** A note piece as the core writes it: [extra] goes before the instructions (chord, staff, ties). */
    private fun note(index: Int, step: String, octave: Int, duration: Int, string: Int? = null, fret: Int? = null, alter: Int? = null, chord: Boolean = false,
                     staff: Int? = null, tie: String = "", confidence: String? = null): String = """
        <note${if (confidence != null) " color=\"#9A5200\"" else ""}>
          ${if (chord) "<chord />" else ""}
          <pitch><step>$step</step>${alter?.let { "<alter>$it</alter>" }.orEmpty()}<octave>$octave</octave></pitch>
          <duration>$duration</duration>
          ${tie.split(' ').filter { it.isNotEmpty() }.joinToString("") { "<tie type=\"$it\" />" }}
          <voice>1</voice><type>quarter</type>
          ${staff?.let { "<staff>$it</staff>" }.orEmpty()}
          ${if (confidence != null) "<notehead color=\"#9A5200\">normal</notehead>" else ""}
          <notations>
            ${tie.split(' ').filter { it.isNotEmpty() }.joinToString("") { "<tied type=\"$it\" />" }}
            ${if (string != null) "<technical><string>$string</string><fret>$fret</fret></technical>" else ""}
          </notations>
          <?fretted-note $index?>
          ${confidence?.let { "<?fretted-confidence $it?>" }.orEmpty()}
        </note>"""

    private fun rest(duration: Int, staff: Int? = null) = "<note><rest /><duration>$duration</duration><voice>1</voice>${staff?.let { "<staff>$it</staff>" }.orEmpty()}</note>"
    private fun words(text: String, staff: Int? = null, boxed: Boolean = false) =
        "<direction placement=\"above\"><direction-type><words${if (boxed) " enclosure=\"rectangle\"" else ""}>$text</words></direction-type>${staff?.let { "<staff>$it</staff>" }.orEmpty()}</direction>"
    private fun backup(duration: Int) = "<backup><duration>$duration</duration></backup>"

    /** A part of [measures] in 4/4 with 24 divisions: a tab staff alone, a notation staff alone, or the pair (notation above). */
    private fun document(layout: String, vararg measures: String, first: String = "1", header: String = "Standard: E A D G"): String {
        val clefs = when (layout) {
            "tab" -> "<clef><sign>TAB</sign><line>5</line></clef>"
            "notation" -> "<clef><sign>F</sign><line>4</line><clef-octave-change>-1</clef-octave-change></clef>"
            else -> "<staves>2</staves><clef number=\"1\"><sign>F</sign><line>4</line></clef><clef number=\"2\"><sign>TAB</sign><line>5</line></clef>"
        }
        val attributes = "<attributes><divisions>24</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>$clefs</attributes>"
        val body = measures.mapIndexed { i, m ->
            val number = if (i == 0) first else (first.toInt() + i).toString()
            "<measure number=\"$number\">${if (i == 0) attributes + words(header, if (layout == "pair") 1 else null) else ""}$m</measure>"
        }.joinToString("\n")
        return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Bass</part-name></score-part></part-list>
<part id="P1">$body</part></score-partwise>"""
    }

    /** A tab's data with [notes] as (confidence, string or null for a note without a place, pitch). */
    private fun data(vararg notes: Triple<Double, Int?, Int>): Tab {
        val (_, recorded) = fixture("bass-line")
        val model = recorded.notes.first()
        return recorded.copy(notes = notes.map { (confidence, string, pitch) ->
            model.copy(pitch = pitch, confidence = confidence, string = string, fret = string?.let { 0 }, outOfRange = string == null)
        })
    }

    @Test
    fun theRecordedLineHasEveryNoteOnceWhereItIsWritten() {
        val (xml, tab) = fixture("bass-line")
        val index = TabIndex.parse(xml)
        assertEquals(15, index.bars)
        assertEquals(1, index.staves)
        assertEquals(0, index.tabStaff)
        assertEquals("Standard: E A D G", index.header)
        assertEquals("Standard", index.tuningName)
        assertEquals(0, index.capo)
        assertEquals(100, index.tempo)
        // Every note of the data is on the page, once, with the string and fret the data gives it.
        assertEquals(tab.notes.indices.toList(), index.pieces.map { it.note })
        tab.notes.forEachIndexed { i, n ->
            val piece = index.of(i).single()
            assertEquals("note $i", listOf(n.pitch, n.string, n.fret), listOf(piece.pitch, piece.string, piece.fret))
            assertTrue(piece.first)
            assertNull(piece.confidence)
            // The line is in 2/4 with 24 ticks to the beat: the bar and the place in it follow from the start.
            assertEquals("note $i", n.start / 48 to (n.start % 48) * TabIndex.TICKS / 24, piece.bar to piece.onset)
        }
        assertEquals(3, index.of(3).single().string)
        assertTrue(index.noPlace.isEmpty())
        // Nothing to check: no marks, from the data or from the page.
        for (marks in listOf(TabMarks.of(index, tab), TabMarks.of(index, null))) {
            assertTrue(marks.columns.isEmpty())
            assertEquals(listOf(0, 0, 0), listOf(marks.doubtful, marks.noPlace, marks.unplaced))
        }
    }

    @Test
    fun theLineWithNotesToCheckHasItsMarksOnTheRightColumns() {
        val (xml, tab) = fixture("bass-line-marks")
        val index = TabIndex.parse(xml)
        // The doubtful note carries its confidence; the note below the lowest string is a rest with boxed words, and has no index.
        assertEquals(0.31, index.of(5).single().confidence!!, 1e-9)
        assertTrue(index.of(12).isEmpty())
        assertEquals(listOf(TabNoPlace(0, 6, "7", 960, listOf("D1"), beat = 2)), index.noPlace)
        // The last note crosses the beat and the bar line: three tied pieces, all with its index, the first with the confidence.
        val tied = index.of(28)
        assertEquals(listOf(14 to 480, 14 to 960, 15 to 0), tied.map { it.bar to it.onset })
        assertEquals(listOf(true, false, false), tied.map { it.first })
        assertEquals(listOf(0.22, null, null), tied.map { it.confidence })

        val marks = TabMarks.of(index, tab)
        assertEquals(listOf(2, 1, 0), listOf(marks.doubtful, marks.noPlace, marks.unplaced))
        assertEquals(listOf(Triple(2, 960, MarkKind.DOUBT), Triple(6, 960, MarkKind.NO_PLACE), Triple(14, 480, MarkKind.DOUBT)), marks.columns.map { Triple(it.bar, it.onset, it.kind) })
        assertEquals(listOf("3", "7", "15"), marks.columns.map { it.barNumber })
        assertEquals(listOf(2, 2, 1), marks.columns.map { it.beat })
        assertEquals(MarkedNote(MarkKind.DOUBT, 5, string = 3, fret = 2, step = "B"), marks.columns[0].notes.single())
        assertEquals(MarkedNote(MarkKind.NO_PLACE, 12, name = "D1", why = NoPlaceWhy.TOO_LOW), marks.columns[1].notes.single())
        assertEquals(MarkedNote(MarkKind.DOUBT, 28, string = 4, fret = 0, step = "E"), marks.columns[2].notes.single())

        // Without the data the page gives the same columns; it names the note without a place and not why.
        val own = TabMarks.of(index, null)
        assertEquals(marks.columns.map { Triple(it.bar, it.onset, it.kind) }, own.columns.map { Triple(it.bar, it.onset, it.kind) })
        assertEquals(listOf(2, 1, 0), listOf(own.doubtful, own.noPlace, own.unplaced))
        assertEquals(MarkedNote(MarkKind.NO_PLACE, null, name = "D1"), own.columns[1].notes.single())

        // The threshold is the data's: a higher one marks more notes, none marks none but the note without a place.
        assertEquals(tab.notes.size - 1, TabMarks.of(index, tab, threshold = 1.0).columns.count { it.kind == MarkKind.DOUBT })
        assertEquals(listOf(MarkKind.NO_PLACE), TabMarks.of(index, tab, threshold = 0.0).columns.map { it.kind })
    }

    @Test
    fun singleNotesAndAChordAreFoundByMeasureStartAndString() {
        val xml = document("tab",
            note(0, "E", 1, 24, 4, 0) + words("?") + note(1, "A", 1, 24, 3, 0, confidence = "0.20") + note(2, "E", 2, 24, 2, 2, confidence = "0.35", chord = true) +
                note(3, "D", 2, 24, 2, 0, alter = -1) + rest(24),
            note(4, "G", 1, 96, 4, 3))
        val index = TabIndex.parse(xml)
        assertEquals(2, index.bars)
        assertEquals(listOf(0, 960, 960, 1920, 0), index.pieces.map { it.onset })
        assertEquals(listOf(0, 0, 0, 0, 1), index.pieces.map { it.bar })
        // D-flat is spelled as the page spells it, and sounds a semitone under D.
        assertEquals(Triple("D", -1, 37), index.of(3).single().let { Triple(it.step, it.alter, it.pitch) })
        // Two doubtful notes that start together are one column with one mark, both notes under it, low to high as written.
        val marks = TabMarks.of(index, data(Triple(0.9, 4, 28), Triple(0.2, 3, 33), Triple(0.35, 2, 40), Triple(0.9, 2, 37), Triple(0.9, 4, 31)))
        val column = marks.columns.single()
        assertEquals(Triple(0, 960, 2), Triple(column.bar, column.onset, column.beat))
        assertEquals(listOf(1 to 3, 2 to 2), column.notes.map { it.note to it.string })
        assertEquals(listOf(2, 0, 0), listOf(marks.doubtful, marks.noPlace, marks.unplaced))
    }

    @Test
    fun aNoteTiedAcrossTheBarLineIsMarkedWhereItStarts() {
        val xml = document("tab",
            rest(72) + words("?") + note(0, "A", 1, 24, 3, 0, tie = "start", confidence = "0.10"),
            note(0, "A", 1, 48, 3, 0, tie = "stop start") + rest(48),
            note(0, "A", 1, 24, 3, 0, tie = "stop") + note(1, "E", 1, 72, 4, 0))
        val index = TabIndex.parse(xml)
        assertEquals(listOf(0 to 2880, 1 to 0, 2 to 0), index.of(0).map { it.bar to it.onset })
        assertEquals(listOf(true, false, false), index.of(0).map { it.first })
        for (tab in listOf(data(Triple(0.1, 3, 33), Triple(0.9, 4, 28)), null)) {
            val column = TabMarks.of(index, tab).columns.single()
            assertEquals(Triple(0, 2880, 4), Triple(column.bar, column.onset, column.beat))
        }
    }

    @Test
    fun aNoteMovedToTheGridAndSplitIntoPiecesKeepsItsIndex() {
        // The data's note 1 starts between two triplet sixteenths; the page writes it on the grid, as two tied pieces
        // across the beat. Its ticks no longer say where it is drawn; its index does.
        val xml = document("tab",
            note(0, "E", 1, 20, 4, 0) + words("?") + note(1, "G", 1, 4, 4, 3, tie = "start", confidence = "0.30") +
                note(1, "G", 1, 20, 4, 3, tie = "stop") + rest(52))
        val index = TabIndex.parse(xml)
        assertEquals(listOf(800, 960), index.of(1).map { it.onset })
        val moved = data(Triple(0.9, 4, 28), Triple(0.3, 4, 31)).let { t -> t.copy(notes = listOf(t.notes[0].copy(start = 0, dur = 19), t.notes[1].copy(start = 19, dur = 25))) }
        val column = TabMarks.of(index, moved).columns.single()
        assertEquals(Triple(0, 800, 1), Triple(column.bar, column.onset, column.beat))
        assertEquals(1, column.notes.single().note)
    }

    @Test
    fun inAPairOfStavesTheMarksAreOnTheTabStaff() {
        // Notation above (staff 1), tab below (staff 2). The low D has no place: the notation staff writes it, with its
        // index; the tab staff has a rest and the boxed words.
        val xml = document("pair",
            note(0, "E", 1, 24, staff = 1) + note(1, "D", 1, 24, staff = 1) + note(2, "A", 1, 48, staff = 1, confidence = "0.25") + backup(96) +
                note(0, "E", 1, 24, 4, 0, staff = 2) + words("! D1", 2, boxed = true) + rest(24, 2) + words("?", 2) + note(2, "A", 1, 48, 3, 0, staff = 2, confidence = "0.25"))
        val index = TabIndex.parse(xml)
        assertEquals(2, index.staves)
        assertEquals(1, index.tabStaff)
        assertEquals(1, index.markStaff)
        assertEquals("Standard: E A D G", index.header)
        assertEquals(listOf(0, 1), index.of(0).map { it.staff })
        assertEquals(listOf(0), index.of(1).map { it.staff })
        assertEquals(listOf(null, 3), index.of(2).map { it.string })
        assertEquals(listOf(TabNoPlace(1, 0, "1", 960, listOf("D1"), beat = 2)), index.noPlace)

        val marks = TabMarks.of(index, data(Triple(0.9, 4, 28), Triple(0.9, null, 26), Triple(0.25, 3, 33)))
        assertEquals(listOf(Triple(1, 960, MarkKind.NO_PLACE), Triple(1, 1920, MarkKind.DOUBT)), marks.columns.map { Triple(it.staff, it.onset, it.kind) })
        // The note without a place is found by its index on the notation staff, and spelled as it is written there.
        assertEquals(MarkedNote(MarkKind.NO_PLACE, 1, step = "D", name = "D1", why = NoPlaceWhy.TOO_LOW), marks.columns[0].notes.single())
        // The doubtful note is the tab staff's piece: it has the string and the fret.
        assertEquals(MarkedNote(MarkKind.DOUBT, 2, string = 3, fret = 0, step = "A"), marks.columns[1].notes.single())
        assertEquals(listOf(1, 1, 0), listOf(marks.doubtful, marks.noPlace, marks.unplaced))
        // The page alone gives the same two columns.
        assertEquals(marks.columns.map { Triple(it.staff, it.onset, it.kind) }, TabMarks.of(index, null).columns.map { Triple(it.staff, it.onset, it.kind) })
    }

    @Test
    fun inTheNotationLayoutTheMarksAreOnTheNotes() {
        val xml = document("notation",
            words("! D1", boxed = true) + note(0, "D", 1, 48) + words("?") + note(1, "A", 1, 48, confidence = "0.25"))
        val index = TabIndex.parse(xml)
        assertNull(index.tabStaff)
        assertEquals(0, index.markStaff)
        val marks = TabMarks.of(index, data(Triple(0.9, null, 26), Triple(0.25, 3, 33)))
        assertEquals(listOf(Triple(0, 0, MarkKind.NO_PLACE), Triple(0, 1920, MarkKind.DOUBT)), marks.columns.map { Triple(it.staff, it.onset, it.kind) })
        assertNull(marks.columns[1].notes.single().string)
        assertEquals(0, marks.unplaced)
    }

    @Test
    fun aPickupIsMeasureNoughtAndBarsAreCountedAsWritten() {
        val xml = document("tab", words("?") + note(0, "E", 1, 24, 4, 0, confidence = "0.10"), note(1, "A", 1, 96, 3, 0), first = "0", header = "Drop D: D A D G, Capo 3")
        val index = TabIndex.parse(xml)
        assertEquals("Drop D", index.tuningName)
        assertEquals(3, index.capo)
        val column = TabMarks.of(index, null).columns.single()
        // alphaTab's first bar is the pickup. Its one quarter note is the fourth beat of the bar it leads into.
        assertEquals(0 to "0", column.bar to column.barNumber)
        assertTrue(column.pickup)
        assertEquals(4, column.beat)
        assertFalse(index.of(1).single().pickup)
        assertEquals(1 to "1", index.of(1).single().let { it.bar to it.barNumber })
    }

    @Test
    fun aBeatIsCountedInTheTimeSignatureInForce() {
        // Two bars of 4/4, then 6/8: the third bar's notes are counted in eighths.
        val six = """<attributes><time><beats>6</beats><beat-type>8</beat-type></time></attributes>"""
        val xml = document("tab",
            rest(72) + words("?") + note(0, "E", 1, 24, 4, 0, confidence = "0.10"),
            rest(96),
            six + rest(36) + words("?") + note(1, "A", 1, 36, 3, 0, confidence = "0.10"))
        val columns = TabMarks.of(TabIndex.parse(xml), null).columns
        assertEquals(listOf(0 to 4, 2 to 4), columns.map { it.bar to it.beat })
        assertEquals(listOf(false, false), columns.map { it.pickup })
    }

    @Test
    fun aDoubtfulNoteWithNoPlaceIsCountedOnceUnderTheMark() {
        val xml = document("tab", words("! D1", boxed = true) + rest(48) + words("?") + note(1, "A", 1, 48, 3, 0, confidence = "0.25"))
        val marks = TabMarks.of(TabIndex.parse(xml), data(Triple(0.1, null, 26), Triple(0.25, 3, 33)))
        assertEquals(listOf(MarkKind.NO_PLACE, MarkKind.DOUBT), marks.columns.map { it.kind })
        assertEquals(listOf(1, 1, 0), listOf(marks.doubtful, marks.noPlace, marks.unplaced))
    }

    @Test
    fun theRendererGetsThePageWithoutItsHeaderWords() {
        val (xml, _) = fixture("bass-line-marks")
        val index = TabIndex.parse(xml)
        val page = TabIndex.forRenderer(xml, index.header)
        assertFalse(page.contains("Standard: E A D G"))
        assertTrue(page.contains("<metronome>"))
        assertEquals(Regex("<direction ").findAll(xml).count() - 4, Regex("<direction ").findAll(page).count())
        assertEquals(index.pieces, TabIndex.parse(page).pieces)
        // Words that are not the header stay.
        val ring = document("tab", words("let ring") + note(0, "E", 1, 96, 4, 0))
        assertTrue(TabIndex.forRenderer(ring, TabIndex.parse(ring).header).contains("let ring"))
    }

    @Test
    fun theSizeFollowsTheTextSizeAndTheZoomUpToWhatFits() {
        val base = 1.7
        // Upright: the text size and the zoom, up to a page 140 units wide.
        assertEquals(1.7, TabSize.scale(base, 100, 1f, 411f, 700f, false, 99.0), 1e-9)
        assertEquals(0.85, TabSize.scale(base, 50, 1f, 411f, 700f, false, 99.0), 1e-9)
        assertEquals(411 / 140.0, TabSize.scale(base, 100, 2f, 411f, 700f, false, 99.0), 1e-9)
        assertEquals(411 / 140.0, TabSize.scale(base, 400, 1f, 411f, 700f, false, 99.0), 1e-9)
        // On its side large text stops at two lines to the room: on a tablet that is larger than the ordinary size.
        assertEquals(700 / 198.0, TabSize.scale(base, 100, 3f, 1200f, 700f, true, 99.0), 1e-9)
        assertEquals(3.4, TabSize.scale(base, 100, 2f, 1200f, 700f, true, 99.0), 1e-6)
        // On a phone it is the ordinary size, and the zoom is on top of it.
        assertEquals(1.7, TabSize.scale(base, 100, 2f, 890f, 300f, true, 99.0), 1e-9)
        assertEquals(1.7, TabSize.scale(base, 100, 1f, 890f, 300f, true, 99.0), 1e-9)
        assertEquals(3.4, TabSize.scale(base, 200, 2f, 890f, 300f, true, 99.0), 1e-9)
        // Before a line has been engraved its height is not known: the text size alone.
        assertEquals(3.4, TabSize.scale(base, 100, 2f, 890f, 300f, true, null), 1e-6)
    }

    @Test
    fun aNoteThePageDoesNotHaveIsCountedNotDrawn() {
        // Two notes of one pitch on one place are written once, with the first one's index: the second has no column.
        val xml = document("tab", words("?") + note(0, "E", 1, 96, 4, 0, confidence = "0.10"))
        val marks = TabMarks.of(TabIndex.parse(xml), data(Triple(0.1, 4, 28), Triple(0.2, 4, 28), Triple(0.9, null, 20)))
        assertEquals(1, marks.columns.size)
        // The lines above the tab count what is drawn: one "?", no "!".
        assertEquals(listOf(1, 0), listOf(marks.doubtful, marks.noPlace))
        // The doubling, and the note without a place that the page has no boxed words for.
        assertEquals(2, marks.unplaced)
        // Boxed words the data has no note for are counted too.
        val boxed = document("tab", words("! D1", boxed = true) + rest(96))
        assertEquals(1, TabMarks.of(TabIndex.parse(boxed), data(Triple(0.9, 4, 28))).unplaced)
    }

    @Test
    fun thePageGoesToTheRendererWithoutItsMarks() {
        val (xml, _) = fixture("bass-line-marks")
        val bare = TabIndex.withoutMarks(xml)
        assertFalse(bare.contains("<words>?</words>"))
        assertFalse(bare.contains("! D1"))
        assertFalse(bare.contains("#9A5200"))
        // Only those: the header, the tempo and every note are still there, and it is still a document.
        assertTrue(bare.contains("<words>Standard: E A D G</words>"))
        assertTrue(bare.contains("<metronome>"))
        assertEquals(Regex("<note\\b").findAll(xml).count(), Regex("<note\\b").findAll(bare).count())
        assertEquals(Regex("<direction ").findAll(xml).count() - 3, Regex("<direction ").findAll(bare).count())
        val again = TabIndex.parse(bare)
        assertEquals(TabIndex.parse(xml).pieces, again.pieces)
        assertTrue(again.noPlace.isEmpty())
    }

    @Test
    fun somethingThatIsNotATabGivesAnEmptyIndex() {
        for (text in listOf("", "not xml", "<score-partwise version=\"4.0\"></score-partwise>")) {
            val index = TabIndex.parse(text)
            assertEquals(0, index.bars)
            assertTrue(TabMarks.of(index, null).columns.isEmpty())
        }
    }

    @Test
    fun theTabsNumbersAreTheDesignTokens() {
        val tokens = root?.resolve("design/fretscribe/tokens/tokens.json")
        assumeTrue("design/fretscribe/tokens is not in this checkout", tokens?.isFile == true)
        val json = kotlinx.serialization.json.Json.parseToJsonElement(tokens!!.readText()) as kotlinx.serialization.json.JsonObject
        fun at(vararg path: String) = path.fold(json as kotlinx.serialization.json.JsonElement) { e, k -> (e as kotlinx.serialization.json.JsonObject).getValue(k) }
        fun number(vararg path: String) = (at(*path, "\$value") as kotlinx.serialization.json.JsonPrimitive).content.toDouble()
        fun hex(mode: String) = ((at("color", mode, "uncertain-tint", "\$value") as kotlinx.serialization.json.JsonObject).getValue("hex") as kotlinx.serialization.json.JsonPrimitive).content
        assertEquals(number("tab", "numeral-scale"), TabTokens.NUMERAL_SCALE, 0.0)
        assertEquals(number("tab", "mark-size-line-spaces"), TabTokens.MARK_LINE_SPACES.toDouble(), 1e-6)
        assertEquals(number("tab", "uncertain-threshold-default"), TabTokens.UNCERTAIN_THRESHOLD, 0.0)
        assertEquals(hex("light"), "#%06X".format(TabTokens.UNCERTAIN_TINT_LIGHT and 0xFFFFFF))
        assertEquals(hex("dark"), "#%06X".format(TabTokens.UNCERTAIN_TINT_DARK and 0xFFFFFF))
        // The engine marks "?" at the same threshold the app reads the data with.
        assertEquals(no.brasscribe.play.engine.TabNote.DOUBT, TabTokens.UNCERTAIN_THRESHOLD, 0.0)
    }
}
