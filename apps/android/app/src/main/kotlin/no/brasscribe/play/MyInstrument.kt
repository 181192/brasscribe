package no.brasscribe.play

import no.brasscribe.play.connection.KeyValueStore
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.PartSource
import no.brasscribe.play.model.Seat
import no.brasscribe.play.model.SeatPart
import no.brasscribe.play.model.VoiceRole

/**
 * The player's answer to "What do you play?" (docs/plan/my-instrument.md §2.1): not asked yet, "I
 * conduct or listen", or a seat of the contest band with the clef they read.
 */
sealed interface SeatChoice {
    /** Never answered ("Not now"): scores behave as before, with the lineup's lead as "your part". */
    data object NotSet : SeatChoice

    /** "I conduct or listen": no part is yours; scores open on every part. */
    data object Conductor : SeatChoice

    /** A seat ([Seat.id]) and the clef read ([Seat.reads]; null: the part's own). */
    data class Player(val seat: String, val reads: String? = null) : SeatChoice

    val seatId: String? get() = (this as? Player)?.seat
    val readsOrNull: String? get() = (this as? Player)?.reads
}

/**
 * Keeps the answer on this phone. It lives in the per-device preferences, which backup and device
 * transfer leave out (res/xml/backup_rules.xml), like Appearance.
 */
class SeatStore(private val store: KeyValueStore) {
    fun load(): SeatChoice = when (val s = store.get(SEAT)) {
        null -> SeatChoice.NotSet
        NONE -> SeatChoice.Conductor
        else -> SeatChoice.Player(s, store.get(READS))
    }

    fun save(choice: SeatChoice) {
        when (choice) {
            SeatChoice.NotSet -> { store.remove(SEAT); store.remove(READS) }
            SeatChoice.Conductor -> { store.put(SEAT, NONE); store.remove(READS) }
            is SeatChoice.Player -> {
                store.put(SEAT, choice.seat)
                if (choice.reads == null) store.remove(READS) else store.put(READS, choice.reads)
            }
        }
    }

    companion object {
        const val SEAT = "seat"
        const val READS = "reads"
        const val NONE = "none"
    }
}

/**
 * "Your part" in one score: its index, and when the lineup has no part of the seat's own, the part it
 * got instead ([MappedSeat]), which the score says in one line.
 */
data class YourPart(val index: Int?, val mapped: MappedSeat? = null)

/** "This small band has no 1st Baritone. Your part here is Euphonium…": [part] null when there is none. */
data class MappedSeat(val lineup: Lineup, val seat: Seat, val part: String?, val sameKey: Boolean)

/** One way to find the player's part for every screen: the score, the stand, Share and Review. */
object YourParts {
    private fun clean(s: String) = s.replace('\u00A0', ' ').trim()

    /**
     * The player's part among [parts]:
     * - the part picked for this score ("Make this my part", [override]) when it is there;
     * - with no answer yet, the lineup's lead, as before;
     * - for "I conduct or listen", none;
     * - else the seat's own part, or the lineup's part for the seat (the core's table), or the one
     *   part of a one-part score (a solo take written for someone else).
     */
    fun resolve(
        parts: List<String>, lineup: Lineup?, choice: SeatChoice, override: String?, seats: List<Seat>,
        seatPart: (String, String) -> SeatPart?,
    ): YourPart {
        val names = parts.map(::clean)
        override?.let { o -> names.indexOfFirst { it.equals(clean(o), true) }.takeIf { it >= 0 }?.let { return YourPart(it) } }
        return when (choice) {
            SeatChoice.NotSet -> YourPart(leadPartIndex(parts, lineup))
            SeatChoice.Conductor -> YourPart(null)
            is SeatChoice.Player -> {
                val seat = seats.firstOrNull { it.id == choice.seat } ?: return YourPart(leadPartIndex(parts, lineup))
                names.indexOfFirst { it.equals(seat.name, true) }.takeIf { it >= 0 }?.let { return YourPart(it) }
                val known = lineup ?: Lineup.ofParts(names)
                val tries = if (known != null) listOf(known) else listOf(Lineup.MINIMAL, Lineup.QUARTET)
                for (l in tries) {
                    val sp = seatPart(l.core, seat.id) ?: continue
                    val i = sp.part?.let { p -> names.indexOfFirst { it.equals(p, true) } } ?: -1
                    if (i >= 0) return YourPart(i, MappedSeat(l, seat, sp.part, sp.sameKey).takeIf { !sp.exact })
                    if (sp.part == null && known != null) return YourPart(null, MappedSeat(l, seat, null, false))
                }
                YourPart(if (names.size == 1) 0 else null)
            }
        }
    }

    /** Sounding minus written of a part, by its name: the seat of that name, or the quartet's own names. */
    fun chromatic(part: String, seats: List<Seat>): Int? {
        val name = clean(part)
        seats.firstOrNull { it.name.equals(name, true) }?.let { return it.chromatic }
        val alias = QUARTET_ALIASES[name] ?: return null
        return seats.firstOrNull { it.id == alias }?.chromatic
    }

    /** The quartet's parts named after their band seat's instrument (1st Cornet plays a cornet). */
    private val QUARTET_ALIASES = mapOf("1st Cornet" to "solo-cornet", "Tenor Horn" to "solo-horn")

    /**
     * The part that carries the tune in [composition]'s arrangement: the seat's part when it was
     * arranged with the tune on the seat (a solo take with a seat always is), else the lineup's lead.
     */
    fun leadPart(composition: Composition?, parts: List<String>, seatPart: (String, String) -> SeatPart?): String? {
        val lineup = Lineup.recorded(composition) ?: Lineup.ofParts(parts.map(::clean))
        val seat = composition?.arrangementString("seat")
        if (seat != null && composition.arrangementString("lead") == "seat") {
            if (parts.size == 1) return clean(parts[0])
            seatPart((lineup ?: Lineup.FULL).core, seat)?.part?.let { return it }
        }
        val i = leadPartIndex(parts, lineup)
        return parts.getOrNull(i)?.let(::clean)?.takeIf { p -> Lineup.LEADS.any { it.equals(p, true) } }
    }

    /**
     * The recording layer that [part] follows, for Review's "Yours": the tune for the lead part, the
     * bass line for the basses, the countermelody for Euphonium, the drums for Percussion. Null for a
     * part that follows no layer of its own.
     */
    fun voiceOf(part: String, lead: String?, source: PartSource?, composition: Composition): String? {
        if (source == PartSource.ARRANGED || source == PartSource.EMPTY) return null
        val sounding = composition.voices.filter { it.notes.isNotEmpty() }
        fun layer(id: String) = sounding.firstOrNull { it.id == id || it.layer == id }?.id
        val name = clean(part)
        return when {
            lead != null && name.equals(lead, true) -> sounding.firstOrNull { it.role == VoiceRole.MELODY }?.id
            name == "E♭ Bass" || name == "B♭ Bass" -> layer("bass")
            name == "Percussion" -> layer("drums")
            name == "Euphonium" -> layer("strings")
            else -> null
        }
    }
}

/** A text option of the recorded arrangement ("seat", "lead"), or null. */
fun Composition.arrangementString(key: String): String? =
    (arrangement?.get(key) as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { it.isString }?.content
