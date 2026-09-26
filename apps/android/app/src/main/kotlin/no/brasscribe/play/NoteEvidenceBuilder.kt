package no.brasscribe.play

import no.brasscribe.play.engine.Evidence
import no.brasscribe.play.engine.ModelHeard
import no.brasscribe.play.engine.ModelInfo
import no.brasscribe.play.engine.NoteEvidence
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.TimedNote
import no.brasscribe.play.model.VoiceRole
import kotlin.math.abs

/** The engine's GET /v1/jobs/{id}/evidence, computed on the phone for its own transcriptions. */
object NoteEvidenceBuilder {
    const val UNCERTAIN_BELOW = 0.7
    private const val ONSET_WINDOW_S = 0.12

    data class ModelNotes(val model: String, val name: String, val notes: List<TimedNote>)

    fun build(composition: Composition, models: List<ModelNotes>): Evidence {
        val notes = composition.voices.filter { it.role == VoiceRole.MELODY }.flatMap { voice ->
            voice.notes.filter { it.confidence < UNCERTAIN_BELOW }.map { n ->
                val heard = n.onsetS?.let { onset -> models.map { heardAt(it, onset, n.pitch) } }.orEmpty()
                NoteEvidence(voice.id, n.start, n.pitch, n.confidence, heard, n.onsetS)
            }
        }
        val used = models.filter { m -> notes.any { n -> n.models.any { it.model == m.model } } }
        return Evidence(used.map { ModelInfo(it.model, it.name) }, notes)
    }

    private fun heardAt(m: ModelNotes, onset: Double, pitch: Int): ModelHeard {
        val near = m.notes.filter { abs(it.onsetS - onset) <= ONSET_WINDOW_S }
        // In a polyphonic layer the melody's rival is the nearest pitch, not the lowest one sounding.
        val best = near.minWithOrNull(compareBy<TimedNote> { abs(it.pitch - pitch) }.thenBy { abs(it.onsetS - onset) })
            ?: m.notes.firstOrNull { it.onsetS <= onset && onset < it.offsetS }
        return ModelHeard(m.model, m.name, best?.pitch == pitch, best?.pitch)
    }
}

/** The evidence behind a review event: the transcribed note at that tick with that pitch class. */
fun Evidence.noteAt(voice: String, start: Int, pitch: Int): NoteEvidence? =
    notes.firstOrNull { it.voice == voice && it.start == start && Math.floorMod(it.pitch, 12) == Math.floorMod(pitch, 12) }
