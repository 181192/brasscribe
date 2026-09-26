package no.brasscribe.play.model

/**
 * How sure the transcription is about a note. Every level has its own shape as well as its own colour,
 * so the level survives greyscale printing and colour-vision differences.
 */
enum class Uncertainty {
    /** confidence >= 0.7: plain notehead. */
    CONFIDENT,

    /** 0.4 <= confidence < 0.7: coloured notehead plus an open ring. */
    UNCERTAIN,

    /** confidence < 0.4: parenthesised notehead plus a filled ring. */
    VERY_UNCERTAIN;

    companion object {
        const val CONFIDENT_AT = 0.7
        const val UNCERTAIN_AT = 0.4

        fun of(confidence: Double): Uncertainty = when {
            confidence >= CONFIDENT_AT -> CONFIDENT
            confidence >= UNCERTAIN_AT -> UNCERTAIN
            else -> VERY_UNCERTAIN
        }
    }
}
