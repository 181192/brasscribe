package no.brasscribe.play.model

/** A printable note value: type name as in MusicXML, dots, and an optional 3:2 tuplet. */
data class NoteValue(val type: String, val dots: Int = 0, val triplet: Boolean = false) {
    fun ticks(tpb: Int): Int {
        val base = when (type) {
            "breve" -> 8 * tpb; "whole" -> 4 * tpb; "half" -> 2 * tpb; "quarter" -> tpb
            "eighth" -> tpb / 2; "16th" -> tpb / 4; "32nd" -> tpb / 8
            else -> tpb
        }
        var total = base
        var add = base
        repeat(dots) { add /= 2; total += add }
        return if (triplet) total * 2 / 3 else total
    }
}

object Durations {
    private val PLAIN = listOf(
        NoteValue("whole", 1), NoteValue("whole"), NoteValue("half", 1), NoteValue("half"),
        NoteValue("quarter", 1), NoteValue("quarter"), NoteValue("eighth", 1), NoteValue("eighth"),
        NoteValue("16th", 1), NoteValue("16th"), NoteValue("32nd"),
    )
    private val TRIPLETS = listOf(NoteValue("half", triplet = true), NoteValue("quarter", triplet = true),
        NoteValue("eighth", triplet = true), NoteValue("16th", triplet = true))

    /** The single value of exactly [ticks], if there is one. */
    fun exact(ticks: Int, tpb: Int): NoteValue? =
        PLAIN.firstOrNull { it.ticks(tpb) == ticks } ?: TRIPLETS.firstOrNull { it.ticks(tpb) == ticks }

    /**
     * Splits [ticks] into printable values, largest first, to be tied together. Leftovers below a 32nd
     * are absorbed into the last value, so the sum is at least [ticks] minus that remainder.
     */
    fun split(ticks: Int, tpb: Int): List<NoteValue> {
        exact(ticks, tpb)?.let { return listOf(it) }
        val out = mutableListOf<NoteValue>()
        var left = ticks
        val plainUndotted = PLAIN.filter { it.dots == 0 }
        while (left > 0) {
            val v = plainUndotted.firstOrNull { it.ticks(tpb) <= left } ?: break
            out += v
            left -= v.ticks(tpb)
        }
        if (out.isEmpty()) out += NoteValue("32nd")
        return out
    }
}
