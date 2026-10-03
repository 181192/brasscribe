package no.brasscribe.play

import no.brasscribe.play.engine.Profile
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.KeySig
import no.brasscribe.play.model.Meter
import no.brasscribe.play.model.Note
import no.brasscribe.play.model.Voice
import no.brasscribe.play.model.VoiceRole
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** A transcription with no note in it opens on the problem screen, not in Check the notes, which had none to show. */
class NoNotesFoundTest {
    private fun result(vararg notes: List<Note>) = TranscriptionResult(
        Composition("T", notes.mapIndexed { i, n -> Voice("v$i", if (i == 0) VoiceRole.MELODY else VoiceRole.BASS, n) }, listOf(Meter(0, 4)), listOf(KeySig(0, 0))),
        "<score-partwise/>", Profile.SOLO, onDevice = true,
    )

    @Test
    fun aResultWithoutANoteIsNotCheckedNoteByNote() {
        // A low bass on the phone: the voices are there, with nothing in them.
        assertTrue(foundNoNotes(result(emptyList(), emptyList()), Screen.REVIEW))
        assertTrue(foundNoNotes(result(), Screen.REVIEW))
        assertFalse(foundNoNotes(result(emptyList(), listOf(Note(40, 0, 24))), Screen.REVIEW))
        // A tab goes to Check the song, which shows what was heard either way; an opened score has no composition.
        assertFalse(foundNoNotes(result(emptyList()), Screen.OUTPUT))
        assertFalse(foundNoNotes(TranscriptionResult(null, "<score-partwise/>", Profile.SOLO, onDevice = false), Screen.REVIEW))
        assertEquals(R.string.error_no_notes, ErrorWords.of(NoNotesFoundException()))
    }
}
