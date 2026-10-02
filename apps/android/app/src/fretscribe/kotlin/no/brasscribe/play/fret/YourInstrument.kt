package no.brasscribe.play.fret

import no.brasscribe.play.connection.KeyValueStore
import no.brasscribe.play.engine.FrettedInstrument

/**
 * The instruments of "Your instrument", in the order they are listed, each with the kinds of it that can be
 * chosen: a guitar or a bass by its number of strings, a ukulele by its size.
 */
enum class Instrument(val id: String, val kinds: List<FrettedInstrument>) {
    GUITAR("guitar", listOf(FrettedInstrument.GUITAR_6, FrettedInstrument.GUITAR_7, FrettedInstrument.GUITAR_8)),
    BASS("bass", listOf(FrettedInstrument.BASS_4, FrettedInstrument.BASS_5, FrettedInstrument.BASS_6)),
    /** Soprano, concert and tenor are one kind: they are tuned alike. The baritone is tuned as a guitar's top four strings. */
    UKULELE("ukulele", listOf(FrettedInstrument.UKULELE, FrettedInstrument.UKULELE_BARITONE)),
    MANDOLIN("mandolin", listOf(FrettedInstrument.MANDOLIN));

    /** A capo is used on it: asked about on Check the song. */
    val takesCapo: Boolean get() = this == GUITAR || this == UKULELE

    companion object {
        /** The instrument [kind] is a kind of; null for one this version does not offer. */
        fun of(kind: FrettedInstrument): Instrument? = entries.firstOrNull { kind in it.kinds }
    }
}

/**
 * Which hand frets (docs/fretscribe/research/02-accessibility.md §6). Tab is the same for all three;
 * chord boxes and the fretboard turn round for the two right-hand setups.
 */
enum class FrettingHand(val id: String) {
    /** The left hand frets: most players. */
    LEFT("left"),

    /** The right hand frets, on an instrument strung for it. */
    RIGHT("right"),

    /** The right hand frets on an ordinary instrument turned upside down: the low string is nearest the floor. */
    RIGHT_UPSIDE_DOWN("right-upside-down"),
}

/** What the player reads. The id is the engine's `layout`. */
enum class Reads(val id: String) {
    TAB("tab"),
    TAB_AND_NOTATION("tab-and-notation"),
    NOTATION("notation"),
}

/** The options of a `tab` job that come from the player's instrument. */
data class TabJobOptions(val instrument: String, val tuning: String, val layout: String)

/**
 * The player's answer to "Your instrument" (design/fretscribe/flows.md §2): what new tabs are written for.
 * A song already written keeps the instrument it was made for.
 *
 * [kind] is the engine's instrument ("guitar-6", "bass-5", "ukulele-baritone") and [tuning] one of the
 * tunings the engine has for it ("standard", "drop-d", "high-g"); together they name a preset of the
 * core's `target-fretted` crate ([preset], "guitar-drop-d").
 */
data class YourInstrument(
    val kind: FrettedInstrument = FrettedInstrument.GUITAR_6,
    val tuning: String = kind.defaultTuning,
    val hand: FrettingHand = FrettingHand.LEFT,
    val reads: Reads = Reads.TAB,
) {
    /** Guitar, bass, ukulele or mandolin. */
    val instrument: Instrument get() = Instrument.of(kind) ?: Instrument.of(DEFAULT.kind)!!

    /** The number of strings, for a guitar or a bass (they are chosen by it); null for the others. */
    val strings: Int? get() = stringsOf(kind)

    /** The engine's `instrument`: "guitar-6", "bass-4", "ukulele", "mandolin". */
    val family: String get() = valid().kind.id!!

    /** The crate's preset id for this instrument in this tuning. */
    val preset: String get() = valid().let { it.kind.preset(it.tuning) }

    /** The tunings offered for this instrument, its usual one first. */
    val tunings: List<String> get() = kind.tunings

    /** Another instrument: its first kind in its usual tuning. The same instrument changes nothing. */
    fun withInstrument(other: Instrument): YourInstrument = if (other == instrument) this else other.kinds.first().let { copy(kind = it, tuning = it.defaultTuning) }

    /** Another kind of the instrument: the tuning stays when the new kind has it, and is its usual one otherwise. */
    fun withKind(other: FrettedInstrument): YourInstrument = copy(kind = other).valid()

    /**
     * This answer with every part that can't be chosen replaced by its default: an instrument this version
     * does not offer, a tuning the instrument has no preset for.
     */
    fun valid(): YourInstrument {
        if (Instrument.of(kind) == null) return copy(kind = DEFAULT.kind, tuning = DEFAULT.tuning)
        return if (tuning in kind.tunings) this else copy(tuning = kind.defaultTuning)
    }

    /** What a job is asked for. The fretting hand changes only how things are drawn, so it is not among them. */
    fun jobOptions(): TabJobOptions = valid().let { TabJobOptions(it.kind.id!!, it.tuning, it.reads.id) }

    companion object {
        const val STANDARD = FrettedInstrument.STANDARD_TUNING

        /** "Not now": a six-string guitar in standard tuning, the left hand frets, tab. */
        val DEFAULT = YourInstrument()

        /** The number of strings a guitar or a bass is chosen by ("guitar-7" has 7); null for a ukulele and a mandolin. */
        fun stringsOf(kind: FrettedInstrument): Int? =
            if (Instrument.of(kind)?.let { it == Instrument.GUITAR || it == Instrument.BASS } == true) kind.id?.substringAfterLast('-')?.toIntOrNull() else null
    }
}

/**
 * Keeps the answer on this phone, in the per-device preferences (left out of backup and device transfer,
 * like Appearance). Anything stored that this version can't offer reads as its default.
 *
 * The version that offered the bass alone stored "bass" and a number of strings: that still reads as the
 * same bass.
 */
class YourInstrumentStore(private val store: KeyValueStore) {
    fun load(): YourInstrument {
        val stored = store.get(KIND)?.let { id -> Instrument.entries.flatMap { it.kinds }.firstOrNull { it.id == id } }
            ?: bassOf(store.get(INSTRUMENT), store.get(STRINGS))
        val kind = stored ?: YourInstrument.DEFAULT.kind
        return YourInstrument(
            kind = kind,
            // A tuning stored for an instrument this version can't read says nothing about the default one.
            tuning = store.get(TUNING)?.takeIf { stored != null } ?: kind.defaultTuning,
            hand = FrettingHand.entries.firstOrNull { it.id == store.get(HAND) } ?: YourInstrument.DEFAULT.hand,
            reads = Reads.entries.firstOrNull { it.id == store.get(READS) } ?: YourInstrument.DEFAULT.reads,
        ).valid()
    }

    /** What the bass-only version stored: "bass" and its strings. A count the bass doesn't come with is four. */
    private fun bassOf(instrument: String?, strings: String?): FrettedInstrument? {
        if (instrument != Instrument.BASS.id) return null
        return Instrument.BASS.kinds.firstOrNull { YourInstrument.stringsOf(it)?.toString() == strings } ?: FrettedInstrument.BASS_4
    }

    fun save(value: YourInstrument) {
        val v = value.valid()
        store.put(KIND, v.kind.id!!)
        store.put(TUNING, v.tuning)
        store.put(HAND, v.hand.id)
        store.put(READS, v.reads.id)
    }

    companion object {
        /** The engine's instrument id. */
        const val KIND = "fret_kind"
        const val TUNING = "fret_tuning"
        const val HAND = "fret_hand"
        const val READS = "fret_reads"

        /** Read only: what the bass-only version stored beside the tuning. */
        const val INSTRUMENT = "fret_instrument"
        const val STRINGS = "fret_strings"
    }
}
