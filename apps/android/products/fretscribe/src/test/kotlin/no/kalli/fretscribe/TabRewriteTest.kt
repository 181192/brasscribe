package no.kalli.fretscribe

import no.kalli.scribe.core.bridge.RustCoreBridge
import no.kalli.scribe.engine.FrettedInstrument
import no.kalli.scribe.engine.TabLayout
import no.kalli.scribe.tab.TabIndex
import no.kalli.scribe.tab.TabPiece
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import java.io.File

/**
 * A tab written again on the phone ([TabRewrite]) by the host build of the core, on the fixtures the computer wrote:
 * asked for as it is, the page comes back note for note; in another tuning the same pitches have new places and a
 * note that had no place gets one; a capo keeps the sound or the shapes.
 */
class TabRewriteTest {
    private val fixtures = File(System.getProperty("scribe.sounds")!!).parentFile!!.resolve("apps/fixtures")
    private fun page(name: String) = fixtures.resolve(name).readText()

    @Before
    fun core() = assumeTrue("host build of the Rust core not found", RustCoreBridge.load("fretted") != null)

    /** What the page says of its notes, without the note numbers (a page written again counts them anew). */
    private fun notes(index: TabIndex): List<TabPiece> = index.pieces.filter { it.staff == index.markStaff }.map { it.copy(note = 0) }

    private fun rewritten(xml: String, kind: FrettedInstrument, tuning: String, capo: Int = 0, layout: TabLayout = TabLayout.TAB, keepShapes: Boolean = false): String =
        TabRewrite.rewrite("Song", xml, TabIndex.parse(xml), kind, tuning, capo, layout, keepShapes)

    private fun again(xml: String, kind: FrettedInstrument, tuning: String, capo: Int = 0, layout: TabLayout = TabLayout.TAB, keepShapes: Boolean = false): TabIndex =
        TabIndex.parse(rewritten(xml, kind, tuning, capo, layout, keepShapes))

    @Test
    fun thePageSaysWhatItIsWrittenFor() {
        for ((name, kind) in listOf("bass-line" to FrettedInstrument.BASS_4, "guitar-line" to FrettedInstrument.GUITAR_6, "ukulele-line" to FrettedInstrument.UKULELE)) {
            val xml = page("$name/tab.musicxml")
            assertEquals(name, kind, TabRewrite.written(xml, TabIndex.parse(xml))?.first)
        }
        assertEquals(26, TabRewrite.pitchOf("D1"))
        assertEquals(42, TabRewrite.pitchOf("F#2"))
        assertEquals(39, TabRewrite.pitchOf("Eb2"))
        assertNull(TabRewrite.pitchOf("?"))
    }

    @Test
    fun askedForAsItIsThePageComesBackNoteForNote() {
        for ((name, kind) in listOf("bass-line" to FrettedInstrument.BASS_4, "bass-line-marks" to FrettedInstrument.BASS_4, "guitar-line" to FrettedInstrument.GUITAR_6)) {
            val xml = page("$name/tab.musicxml")
            val before = TabIndex.parse(xml)
            val (_, tuning) = TabRewrite.written(xml, before)!!
            val after = again(xml, kind, tuning, capo = before.capo)
            assertEquals(name, notes(before), notes(after))
            assertEquals(name, before.measures, after.measures)
            assertEquals(name, before.noPlace.map { it.names to it.bar }, after.noPlace.map { it.names to it.bar })
            assertEquals(name, before.tempo, after.tempo)
        }
    }

    @Test
    fun inAnotherTuningTheSamePitchesHaveNewPlacesAndANoteWithNoPlaceGetsOne() {
        // The bass line with marks has a D1, below a bass in standard tuning; drop D has it on the open fourth string.
        val xml = page("bass-line-marks/tab.musicxml")
        val before = TabIndex.parse(xml)
        assertEquals(listOf(listOf("D1")), before.noPlace.map { it.names })
        val after = again(xml, FrettedInstrument.BASS_4, "drop-d")
        assertTrue(after.noPlace.isEmpty())
        assertEquals(notes(before).size + 1, notes(after).size)
        val d = notes(after).single { it.pitch == 26 }
        assertEquals(4 to 0, d.string to d.fret)
        assertEquals(before.noPlace.single().bar, d.bar)
        // Every other note sounds as it did, when it did; the doubtful ones are still doubtful.
        assertEquals(notes(before).map { Triple(it.pitch, it.bar, it.onset) }, notes(after).filter { it.pitch != 26 }.map { Triple(it.pitch, it.bar, it.onset) })
        assertEquals(notes(before).count { it.confidence != null }, notes(after).count { it.confidence != null })
        assertEquals("Drop D", after.tuningName)
        assertEquals(FrettedInstrument.BASS_4 to "drop-d", TabRewrite.written(rewritten(xml, FrettedInstrument.BASS_4, "drop-d"), after))
    }

    @Test
    fun aCapoKeepsTheSoundOrTheShapes() {
        val xml = page("guitar-line/tab.musicxml")
        val before = TabIndex.parse(xml)
        assertEquals(0, before.capo)
        val (kind, tuning) = TabRewrite.written(xml, before)!!
        // Keep the sound: the same pitches, with the frets counted from the capo. What lies below the capo has no place.
        val capoed = rewritten(xml, kind, tuning, capo = 2)
        val sound = TabIndex.parse(capoed)
        assertEquals(2, sound.capo)
        assertEquals(kind to tuning, TabRewrite.written(capoed, sound))
        val was = notes(before).map { Triple(it.pitch, it.bar, it.onset) }
        assertTrue(notes(sound).map { Triple(it.pitch, it.bar, it.onset) }.all { it in was })
        assertTrue(notes(sound).size < was.size && sound.noPlace.isNotEmpty())
        assertTrue(notes(sound).all { it.pitch >= 42 })
        // The capo taken off again: every note is back where it was, also the ones that had no place under the capo.
        assertEquals(notes(before), notes(again(capoed, kind, tuning, capo = 0)))
        // Keep the shapes: every note on its string and fret, two semitones higher; and back.
        val shaped = rewritten(xml, kind, tuning, capo = 2, keepShapes = true)
        val shapes = TabIndex.parse(shaped)
        assertEquals(notes(before).map { it.string to it.fret }, notes(shapes).map { it.string to it.fret })
        assertEquals(notes(before).map { it.pitch + 2 }, notes(shapes).map { it.pitch })
        assertEquals(notes(before), notes(again(shaped, kind, tuning, capo = 0, keepShapes = true)))
        // The notes a page was written from are kept in it once.
        assertEquals(1, Regex("fretted-source").findAll(rewritten(capoed, kind, tuning, capo = 4)).count())
    }

    @Test
    fun thePageIsWrittenInTheLayoutAskedFor() {
        val xml = page("bass-line/tab.musicxml")
        val both = again(xml, FrettedInstrument.BASS_4, "standard", layout = TabLayout.TAB_AND_NOTATION)
        assertEquals(2, both.staves)
        assertEquals(1, both.tabStaff)
        assertEquals(notes(TabIndex.parse(xml)), notes(both).map { it.copy(staff = 0) })
    }

    /**
     * A tab with the player's fixes, written again: a note left out, a ghost note and a doubtful note kept as it is go
     * with their notes (found on the new page by pitch and start); a moved note goes back to where Fretscribe wrote it,
     * with its "?". Each kind in another tuning, with a capo that keeps the sound, and with one that keeps the shapes.
     */
    @Test
    fun theFixesThatStillMeanTheSameGoWithTheirNotes() {
        val xml = page("guitar-line/tab.musicxml")
        val index = TabIndex.parse(xml)
        val (_, tuning) = TabRewrite.written(xml, index)!!
        val pieces = index.pieces.filter { it.staff == index.markStaff && it.first && it.string != null }
        val doubtful = pieces.first { it.confidence != null }
        // (Notes above the lowest string with a capo on the second fret: they have a place in every case.)
        val (out, ghost, moved) = pieces.filter { it.note != doubtful.note && it.pitch >= 45 }.let { Triple(it[0], it[1], it[2]) }
        val elsewhere = FixNote.places(moved.pitch, SongFacts.openStrings(xml)).first { it.string != moved.string }
        var fixed = no.kalli.scribe.tab.TabEdits.leaveOut(xml, out.note)
        fixed = no.kalli.scribe.tab.TabEdits.ghost(fixed, ghost.note, true)
        fixed = no.kalli.scribe.tab.TabEdits.keep(fixed, doubtful.note)
        fixed = no.kalli.scribe.tab.TabEdits.place(fixed, moved.note, elsewhere.string, elsewhere.fret)
        assertEquals(1, no.kalli.scribe.tab.TabEdits.moved(fixed))
        fun key(p: TabPiece) = Triple(p.bar, p.onset, p.pitch)
        for ((case, written) in listOf(
            "drop D" to TabRewrite.rewriteKeepingFixes("Song", fixed, FrettedInstrument.GUITAR_6, "drop-d", 0, TabLayout.TAB),
            "a capo keeping the sound" to TabRewrite.rewriteKeepingFixes("Song", fixed, FrettedInstrument.GUITAR_6, tuning, 2, TabLayout.TAB),
            "a capo keeping the shapes" to TabRewrite.rewriteKeepingFixes("Song", fixed, FrettedInstrument.GUITAR_6, tuning, 2, TabLayout.TAB, keepShapes = true),
        )) {
            val after = TabIndex.parse(written)
            val shift = if (case.endsWith("shapes")) 2 else 0
            fun on(p: TabPiece) = after.pieces.first { it.staff == after.markStaff && it.first && Triple(it.bar, it.onset, it.pitch) == key(p).copy(third = p.pitch + shift) }
            fun edit(p: TabPiece) = no.kalli.scribe.tab.TabEdits.of(written, on(p).note)
            assertTrue("$case: left out", edit(out).leftOut)
            assertTrue("$case: a ghost note", edit(ghost).ghost)
            assertTrue("$case: kept as it is", edit(doubtful).checked)
            assertEquals("$case: the moved note is no longer moved", null, edit(moved).was)
            assertEquals("$case: nothing else is fixed", 3, no.kalli.scribe.tab.TabEdits.fixed(written))
            // The left-out note is still in the file, to be put back.
            assertEquals(case, listOf(on(out).note), no.kalli.scribe.tab.TabEdits.leftOut(written))
        }
        // A page without fixes is written as before.
        assertEquals(rewritten(xml, FrettedInstrument.GUITAR_6, "drop-d"), TabRewrite.rewriteKeepingFixes("Song", xml, FrettedInstrument.GUITAR_6, "drop-d", 0, TabLayout.TAB))
    }
}
