package no.brasscribe.play

import androidx.annotation.StringRes
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import no.brasscribe.play.model.Composition

/**
 * Who the score is arranged for. [engine] is the engine's `lineup` value, [core] the Rust core's; they
 * differ only for the full band ("full" and "band"). [lead] is the part a player reads by default.
 */
enum class Lineup(@StringRes val label: Int, @StringRes val desc: Int, val engine: String, val core: String, val lead: String) {
    FULL(R.string.lineup_full, R.string.lineup_full_desc, "full", "band", "Solo Cornet"),
    MINIMAL(R.string.lineup_minimal, R.string.lineup_minimal_desc, "minimal", "minimal", "Solo Cornet"),
    QUARTET(R.string.lineup_quartet, R.string.lineup_quartet_desc, "quartet", "quartet", "1st Cornet"),
    ;

    companion object {
        /** The lineup a recorded name stands for ("full" and "band" are the same); null for anything else. */
        fun of(name: String?): Lineup? = when (name?.trim()?.lowercase()) {
            "full", "band" -> FULL
            "minimal" -> MINIMAL
            "quartet" -> QUARTET
            else -> null
        }

        /** The lineup [composition] was arranged for, when the core or the engine recorded it. */
        fun recorded(composition: Composition?): Lineup? =
            of((composition?.arrangement?.get("lineup") as? JsonPrimitive)?.contentOrNull)

        /** The lead parts of every lineup, in the order a part list is searched for "my part". */
        val LEADS: List<String> = entries.map { it.lead }.distinct()

        /** The quartet's parts in score order, one player each. */
        val QUARTET_PARTS = listOf("1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium")

        /**
         * The lineup of a score with nothing recorded (an opened MusicXML file): the quartet when its parts
         * are exactly the quartet's, else unknown.
         */
        fun ofParts(names: List<String>): Lineup? =
            QUARTET.takeIf { names.map { it.replace(' ', ' ').trim() } == QUARTET_PARTS }
    }
}

/**
 * Only the layered arranger writes the full band. A take without layers (a Brass band or Pop or rock
 * recording) is arranged for the small band or the quartet, so Full brass band is not offered for it.
 */
val Composition.fullBandMade: Boolean get() = voices.any { it.layer != null }

/** This lineup as it is made for a take: the full band becomes the small band where it can't be written. */
fun Lineup.madeFor(fullBand: Boolean): Lineup = if (this == Lineup.FULL && !fullBand) Lineup.MINIMAL else this

/** A text option of the recorded arrangement ("lineup", "difficulty"), or null. */
fun TranscriptionResult.arrangementText(key: String): String? =
    (composition?.arrangement?.get(key) as? JsonPrimitive)?.contentOrNull

/**
 * This Composition with the lineup, difficulty and seat it was just arranged with recorded, as the core
 * records them. [lineup] is the one made (see [madeFor]): the Output screen never offers the full band
 * for a take without layers. The seat's options are kept so where each part came from stays known after an edit;
 * [soloTake] records the tune on the seat, as a solo take with a seat always has it.
 */
fun Composition.arrangedFor(
    lineup: Lineup, difficulty: String, seat: String? = null, reads: String? = null, lead: String? = null, soloTake: Boolean = false,
): Composition {
    val base = arrangement.orEmpty() - listOf("seat", "reads", "lead")
    val seatOptions = buildMap {
        if (seat != null) {
            put("seat", JsonPrimitive(seat))
            if (reads != null) put("reads", JsonPrimitive(reads))
            if (soloTake || lead == "seat") put("lead", JsonPrimitive("seat"))
        }
    }
    return copy(arrangement = JsonObject(base + mapOf("lineup" to JsonPrimitive(lineup.core), "difficulty" to JsonPrimitive(difficulty)) + seatOptions))
}

/** Index of the part a player most likely wants first: the lineup's lead, else any known lead, else the first part. */
fun leadPartIndex(parts: List<String>, lineup: Lineup? = null): Int {
    val clean = parts.map { it.replace(' ', ' ').trim() }
    val wanted = listOfNotNull(lineup?.lead) + Lineup.LEADS
    return wanted.firstNotNullOfOrNull { lead -> clean.indexOfFirst { it.equals(lead, ignoreCase = true) }.takeIf { it >= 0 } } ?: 0
}
