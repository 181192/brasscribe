package no.kalli.scribe.play

import no.kalli.scribe.engine.Profile
import no.kalli.scribe.model.Composition
import no.kalli.scribe.model.KeySig
import no.kalli.scribe.model.Meter
import no.kalli.scribe.model.Note
import no.kalli.scribe.model.Voice
import no.kalli.scribe.model.VoiceRole
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** A transcription with no note in it opens on its own problem screen, not in Check the notes, which had none to show. */
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
    }

    @Test
    fun theComputerIsOfferedOnlyWhenThePhoneWroteItDownAndTheComputerIsThere() {
        assertTrue(noNotesOffersComputer(madeOnPhone = true, computerThere = true))
        assertFalse(noNotesOffersComputer(madeOnPhone = true, computerThere = false))
        // The computer made it: it has nothing more to give.
        assertFalse(noNotesOffersComputer(madeOnPhone = false, computerThere = true))
        assertFalse(noNotesOffersComputer(madeOnPhone = false, computerThere = false))
    }

    @Test
    fun recordingAgainIsOnlyCalledThatAfterATakeWithTheMicrophone() {
        org.junit.Assert.assertEquals(R.string.problem_record_again, noNotesRecordWords(SourceKind.MICROPHONE))
        for (kind in listOf(SourceKind.FILE, SourceKind.VIDEO, SourceKind.DEVICE, null))
            org.junit.Assert.assertEquals("$kind", R.string.home_record_mic, noNotesRecordWords(kind))
    }
}
