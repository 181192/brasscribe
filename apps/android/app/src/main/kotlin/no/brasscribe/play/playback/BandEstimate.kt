package no.brasscribe.play.playback

import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.model.AccentuationType
import alphaTab.model.GraceType
import alphaTab.model.Note
import alphaTab.model.Score
import no.brasscribe.play.audio.BandNote
import no.brasscribe.play.audio.PlaybackLevels

/**
 * The arrangement's band loudness, estimated from its notes as alphaTab reads them
 * (recording.band_estimate in sounds/playback-levels.json). Each pitched note is taken with its
 * notated place and length in quarter notes and the velocity alphaTab plays it at (its dynamics
 * plus accents). The notes come from alphaTab's score model, not its MIDI, because the MIDI stretches
 * some tie chains far past their last note. Percussion parts and grace notes are left out. Parsing a
 * whole score takes a moment: call it off the main thread.
 */
object BandEstimate {
    /** alphaTab's MIDI ticks per quarter note. */
    private const val QUARTER = 960.0

    fun score(musicXml: ByteArray): Score = ScoreLoader.loadScoreFromBytes(Uint8Array(musicXml.asUByteArray()), alphaTab.Settings())

    /** The pitched notes of [musicXml], each note of a chord and each tied note on its own. */
    fun notes(musicXml: ByteArray): List<BandNote> = notes(score(musicXml))

    fun notes(score: Score): List<BandNote> {
        val out = ArrayList<BandNote>()
        for (t in 0 until score.tracks.length.toInt()) {
            val staves = score.tracks[t].staves
            for (s in 0 until staves.length.toInt()) {
                val staff = staves[s]
                if (staff.isPercussion) continue
                for (b in 0 until staff.bars.length.toInt()) {
                    val voices = staff.bars[b].voices
                    for (v in 0 until voices.length.toInt()) {
                        val beats = voices[v].beats
                        for (k in 0 until beats.length.toInt()) {
                            val beat = beats[k]
                            if (beat.isRest || beat.graceType != GraceType.None || beat.playbackDuration <= 0) continue
                            val start = beat.absolutePlaybackStart / QUARTER
                            val end = start + beat.playbackDuration / QUARTER
                            for (n in 0 until beat.notes.length.toInt()) {
                                out += BandNote(start, end, velocity(beat.notes[n]))
                            }
                        }
                    }
                }
            }
        }
        return out
    }

    /** The velocity alphaTab plays [note] at: its mark plus accents; a tied-to note has its chain's first note's. */
    internal fun velocity(note: Note): Double {
        val played = note.tieOrigin?.takeIf { note.isTieDestination } ?: note
        val steps = when (played.accentuated) {
            AccentuationType.Normal -> 1
            AccentuationType.Heavy -> 2
            else -> 0
        }
        val mark = PlaybackLevels.DYNAMIC_VELOCITY[played.dynamics.name.lowercase()] ?: PlaybackLevels.DYNAMIC_VELOCITY.getValue("f")
        return (mark + steps * PlaybackLevels.DYNAMIC_STEP).coerceIn(1, 127).toDouble()
    }

    /** The recording's target for [musicXml]: its band estimate, clamped; the fallback when it has no pitched note or does not parse. */
    fun targetLufs(musicXml: String?): Double {
        val estimate = musicXml?.let { runCatching { PlaybackLevels.bandEstimateLufs(notes(it.toByteArray())) }.getOrNull() }
        return PlaybackLevels.recordingTargetLufs(estimate)
    }
}
