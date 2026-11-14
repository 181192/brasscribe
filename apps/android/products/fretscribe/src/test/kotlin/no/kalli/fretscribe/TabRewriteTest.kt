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
}
