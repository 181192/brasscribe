package no.kalli.fretscribe

import alphaTab.Settings
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.score.AlphaTabMusicXml
import no.kalli.scribe.tab.TabEdits
import no.kalli.scribe.tab.TabIndex
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Where a note can be played ([FixNote]), and that the page alphaTab engraves follows a fix: a note moved to another
 * string is drawn there, and a note left out is a rest.
 */
@RunWith(AndroidJUnit4::class)
class FixNotePlacesTest {
    private val xml = File(System.getProperty("scribe.sounds")!!).parentFile!!.resolve("apps/fixtures/bass-line-marks/tab.musicxml").readText()

    @Test
    fun everyPlaceOfAPitchIsOfferedHighestStringFirst() {
        val bass = listOf(28, 33, 38, 43)
        // B1 (35): the A string at fret 2 and the E string at fret 7; too low for the D and G strings.
        assertEquals(listOf(FretPlace(3, 2), FretPlace(4, 7)), FixNote.places(35, bass))
        // G2 (43): open on the G string, and on every string below it.
        assertEquals(listOf(FretPlace(1, 0), FretPlace(2, 5), FretPlace(3, 10), FretPlace(4, 15)), FixNote.places(43, bass))
        // Not past the last fret, and not on a string another note of the beat is on.
        assertEquals(listOf(FretPlace(1, 0), FretPlace(2, 5), FretPlace(3, 10)), FixNote.places(43, bass, frets = 12))
        assertEquals(listOf(FretPlace(1, 0), FretPlace(3, 10)), FixNote.places(43, bass, frets = 12, taken = setOf(2)))
        // A note below the lowest string has no place.
        assertTrue(FixNote.places(26, bass).isEmpty())
        // A guitar with a capo on the second fret: the page's strings are tuned two higher, and the frets count from the capo.
        assertEquals(FretPlace(6, 3), FixNote.places(45, listOf(42, 47, 52, 57, 61, 66)).last())
        // The page's own strings are read from its staff tuning.
        assertEquals(bass, SongFacts.openStrings(xml))
        val index = TabIndex.parse(xml)
        assertEquals(listOf(5), FixNote.at(index, 2, TabIndex.TICKS).map { it.note })
        assertTrue(FixNote.at(index, 2, 17).isEmpty())
    }

    /** The notes alphaTab reads on the tab: string (1 the lowest, as alphaTab counts), fret, and whether it is a dead note. */
    private fun read(musicXml: String): List<Triple<Int, Int, Boolean>> {
        val out = ArrayList<Triple<Int, Int, Boolean>>()
        val score = AlphaTabMusicXml.parse(TabIndex.forRenderer(musicXml, TabIndex.parse(musicXml).header).toByteArray(), Settings())
        for (staff in score.tracks[0].staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) for (note in beat.notes) {
            out += Triple(note.string.toInt(), note.fret.toInt(), note.isDead)
        }
        return out
    }

    @Test
    fun thePageAlphaTabEngravesFollowsAFix() {
        val before = read(xml)
        // Note 4 is the fifth note of the page: B on the A string (alphaTab's second string), fret 2.
        assertEquals(Triple(2, 2, false), before[4])
        val moved = read(TabEdits.shown(TabEdits.place(xml, 4, 4, 7)))
        assertEquals(Triple(1, 7, false), moved[4])
        assertEquals(before.filterIndexed { i, _ -> i != 4 }, moved.filterIndexed { i, _ -> i != 4 })
        // (A ghost note's x is not read by alphaTab from the file: the tab view makes it a dead note, FixNoteTest.)
        assertTrue(TabIndex.parse(TabEdits.shown(TabEdits.ghost(xml, 4, true))).of(4).single().ghost)
        assertEquals(before.size - 1, read(TabEdits.shown(TabEdits.leaveOut(xml, 4))).size)
    }
}
