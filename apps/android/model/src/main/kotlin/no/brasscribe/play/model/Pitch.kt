package no.brasscribe.play.model

import kotlinx.serialization.Serializable

/** A spelled pitch: letter, alteration in semitones, scientific octave (C4 = middle C). */
@Serializable
data class SpelledPitch(val step: String, val alter: Int = 0, val octave: Int) {
    val midi: Int get() = 12 * (octave + 1) + STEP_PC.getValue(step) + alter

    companion object {
        val STEPS = listOf("C", "D", "E", "F", "G", "A", "B")
        val STEP_PC = mapOf("C" to 0, "D" to 2, "E" to 4, "F" to 5, "G" to 7, "A" to 9, "B" to 11)

        /** Letters the key signature alters, in order: F C G D A E B for sharps, reversed for flats. */
        fun alteredSteps(fifths: Int): Map<String, Int> {
            val sharps = listOf("F", "C", "G", "D", "A", "E", "B")
            return if (fifths >= 0) sharps.take(fifths).associateWith { 1 }
            else sharps.reversed().take(-fifths).associateWith { -1 }
        }

        /**
         * Spells [midi] in the key of [fifths]: diatonic notes by the key, chromatic notes as raised
         * degrees in sharp keys and lowered degrees in flat keys (C major uses C♯ E♭ F♯ G♯ B♭).
         */
        fun spell(midi: Int, fifths: Int): SpelledPitch {
            val pc = Math.floorMod(midi, 12)
            val altered = alteredSteps(fifths)
            // Diatonic candidates first.
            for (step in STEPS) {
                val alter = altered[step] ?: 0
                if (Math.floorMod(STEP_PC.getValue(step) + alter, 12) == pc) return build(midi, step, alter)
            }
            val preferSharp = when {
                fifths > 0 -> true
                fifths < 0 -> false
                else -> pc == 1 || pc == 6 || pc == 8
            }
            for (step in STEPS) {
                val base = STEP_PC.getValue(step) + (altered[step] ?: 0)
                val alter = (altered[step] ?: 0) + if (preferSharp) 1 else -1
                if (Math.floorMod(base + if (preferSharp) 1 else -1, 12) == pc) return build(midi, step, alter)
            }
            return build(midi, "C", pc) // unreachable for valid input
        }

        private fun build(midi: Int, step: String, alter: Int): SpelledPitch {
            val octave = Math.floorDiv(midi - alter - STEP_PC.getValue(step), 12) - 1
            return SpelledPitch(step, alter, octave)
        }
    }
}

/**
 * A brass-band instrument's transposition: written = concert - chromatic. A B♭ cornet has
 * chromatic -2 (it sounds a tone below what is written), diatonic -1.
 */
enum class Instrument(
    val nameEn: String,
    val nameNb: String,
    val keyEn: String,
    val keyNb: String,
    val chromatic: Int,
    val diatonic: Int,
    val midiProgram: Int,
) {
    CONCERT("Concert pitch", "Klingende", "C", "C", 0, 0, 56),
    SOPRANO_CORNET("Soprano Cornet", "Sopran-kornett", "Soprano Cornet in E-flat", "sopran-kornett i Ess", 3, 2, 56),
    CORNET("Cornet", "Kornett", "Cornet in B-flat", "kornett i B", -2, -1, 56),
    FLUGELHORN("Flugelhorn", "Flygelhorn", "Flugelhorn in B-flat", "flygelhorn i B", -2, -1, 56),
    TENOR_HORN("Tenor Horn", "Althorn", "Horn in E-flat", "althorn i Ess", -9, -5, 60),
    BARITONE("Baritone", "Baryton", "Baritone in B-flat", "baryton i B", -14, -8, 58),
    EUPHONIUM("Euphonium", "Eufonium", "Euphonium in B-flat", "eufonium i B", -14, -8, 58),
    TROMBONE("Trombone", "Trombone", "Trombone in B-flat", "trombone i B", -14, -8, 57),
    BASS_TROMBONE("Bass Trombone", "Basstrombone", "Bass Trombone in C", "basstrombone i C", 0, 0, 57),
    EB_BASS("E-flat Bass", "Ess-bass", "Bass in E-flat", "Ess-bass", -21, -12, 58),
    BB_BASS("B-flat Bass", "B-bass", "Bass in B-flat", "B-bass", -26, -15, 58);

    fun writtenMidi(concert: Int): Int = concert - chromatic

    /** Key signature of the written part for a concert key. */
    fun writtenFifths(concertFifths: Int): Int {
        // Transposing up a major second adds two sharps: fifths change = 7 * semitones mod 12, folded to -6..6.
        var f = concertFifths + Math.floorMod(-chromatic * 7, 12)
        while (f > 7) f -= 12
        while (f < -7) f += 12
        return f
    }

    fun spellWritten(concert: Int, concertFifths: Int): SpelledPitch =
        SpelledPitch.spell(writtenMidi(concert), writtenFifths(concertFifths))
}
