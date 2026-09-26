package no.brasscribe.play

import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.KeySig
import no.brasscribe.play.model.Meter
import no.brasscribe.play.model.Note
import no.brasscribe.play.model.TimedNote
import no.brasscribe.play.model.Voice
import no.brasscribe.play.model.VoiceRole
import org.junit.Assert.assertEquals
import org.junit.Test

class NoteEvidenceBuilderTest {
    @Test
    fun comparesModelsAtUncertainNotesAndPrefersTheNearestPitch() {
        val c = Composition("t", listOf(Voice("melody", VoiceRole.MELODY, listOf(
            Note(67, 24, 24, confidence = 0.5, onsetS = 1.0), Note(69, 48, 24, confidence = 0.9, onsetS = 2.0)))),
            listOf(Meter(0, 4)), listOf(KeySig(0, 0)))
        val e = NoteEvidenceBuilder.build(c, listOf(
            NoteEvidenceBuilder.ModelNotes("swift-f0", "SwiftF0", listOf(TimedNote(1.02, 1.4, 67, 0.9, emptyList()))),
            NoteEvidenceBuilder.ModelNotes("basic-pitch", "Basic Pitch", listOf(TimedNote(1.01, 1.4, 48, 0.9, emptyList()), TimedNote(1.03, 1.4, 69, 0.9, emptyList()))),
        ))
        val note = e.notes.single()
        assertEquals(0.5, note.confidence, 0.0)
        assertEquals(listOf(67 to true, 69 to false), note.models.map { it.pitch to it.agrees })
        assertEquals(2, note.alternativeShift)
        assertEquals(note, e.noteAt("melody", 24, 55))
    }
}
