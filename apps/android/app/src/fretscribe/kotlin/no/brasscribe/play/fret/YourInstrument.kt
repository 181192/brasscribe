package no.brasscribe.play.fret

import no.brasscribe.play.connection.KeyValueStore

/** The instruments of "Your instrument". Only the bass can be chosen yet; the others are shown as "Later". */
enum class Instrument(val id: String, val available: Boolean) {
    BASS("bass", true),
    GUITAR("guitar", false),
    UKULELE("ukulele", false),
    MANDOLIN("mandolin", false),
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

/** The options of a `bass-tab` job that come from the player's instrument. */
data class TabJobOptions(val instrument: String, val tuning: String, val layout: String)

/**
 * The player's answer to "Your instrument" (design/fretscribe/flows.md §2): what new tabs are written for.
 * A song already written keeps the instrument it was made for.
 *
 * [tuning] is the engine's tuning id ("standard", "drop-d"); with the instrument and its strings it names a
 * preset of the core's `target-fretted` crate ([preset], "bass-4-drop-d").
 */
data class YourInstrument(
    val instrument: Instrument = Instrument.BASS,
    val strings: Int = 4,
    val tuning: String = STANDARD,
    val hand: FrettingHand = FrettingHand.LEFT,
    val reads: Reads = Reads.TAB,
) {
    /** The engine's `instrument`: "bass-4", "bass-5" or "bass-6". */
    val family: String get() = "${instrument.id}-$strings"

    /** The crate's preset id for this instrument in this tuning. */
    val preset: String get() = "$family-$tuning"

    /** The tunings offered for this instrument, standard first. */
    val tunings: List<String> get() = tuningsOf(instrument, strings)

    /** Another string count: the tuning stays when the new instrument has it, and is standard otherwise. */
    fun withStrings(count: Int): YourInstrument = copy(strings = count).valid()

    /**
     * This answer with every part that can't be chosen replaced by its default: an instrument that is
     * still "Later", a string count the instrument doesn't have, a tuning it has no preset for.
     */
    fun valid(): YourInstrument {
        // Another instrument's strings and tuning say nothing about the bass: a six-string guitar is no six-string bass.
        if (!instrument.available) return copy(instrument = DEFAULT.instrument, strings = DEFAULT.strings, tuning = STANDARD)
        val strings = strings.takeIf { it in stringsOf(instrument) } ?: stringsOf(instrument).first()
        val tuning = tuning.takeIf { it in tuningsOf(instrument, strings) } ?: STANDARD
        return copy(instrument = instrument, strings = strings, tuning = tuning)
    }

    /** What a job is asked for. The fretting hand changes only how things are drawn, so it is not among them. */
    fun jobOptions(): TabJobOptions = valid().let { TabJobOptions(it.family, it.tuning, it.reads.id) }

    companion object {
        const val STANDARD = "standard"

        /** "Not now": a four-string bass in standard tuning, the left hand frets, tab. */
        val DEFAULT = YourInstrument()

        /**
         * The engine's instruments and their tunings, standard first: the `target-fretted` presets
         * "<instrument>-<tuning>" (core/target-fretted/src/instrument.rs). A test checks this table
         * against the crate.
         */
        val BASS_TUNINGS: Map<Int, List<String>> = mapOf(
            4 to listOf(STANDARD, "eb-standard", "d-standard", "drop-d", "bead"),
            5 to listOf(STANDARD, "drop-a"),
            6 to listOf(STANDARD),
        )

        /** The string counts offered for [instrument]; none for one that can't be chosen yet. */
        fun stringsOf(instrument: Instrument): List<Int> =
            if (instrument == Instrument.BASS) BASS_TUNINGS.keys.toList() else emptyList()

        fun tuningsOf(instrument: Instrument, strings: Int): List<String> =
            if (instrument == Instrument.BASS) BASS_TUNINGS[strings].orEmpty() else emptyList()
    }
}

/**
 * Keeps the answer on this phone, in the per-device preferences (left out of backup and device transfer,
 * like Appearance). Anything stored that this version can't offer reads as its default.
 */
class YourInstrumentStore(private val store: KeyValueStore) {
    fun load(): YourInstrument = YourInstrument(
        instrument = Instrument.entries.firstOrNull { it.id == store.get(INSTRUMENT) } ?: YourInstrument.DEFAULT.instrument,
        strings = store.get(STRINGS)?.toIntOrNull() ?: YourInstrument.DEFAULT.strings,
        tuning = store.get(TUNING) ?: YourInstrument.STANDARD,
        hand = FrettingHand.entries.firstOrNull { it.id == store.get(HAND) } ?: YourInstrument.DEFAULT.hand,
        reads = Reads.entries.firstOrNull { it.id == store.get(READS) } ?: YourInstrument.DEFAULT.reads,
    ).valid()

    fun save(value: YourInstrument) {
        val v = value.valid()
        store.put(INSTRUMENT, v.instrument.id)
        store.put(STRINGS, v.strings.toString())
        store.put(TUNING, v.tuning)
        store.put(HAND, v.hand.id)
        store.put(READS, v.reads.id)
    }

    companion object {
        const val INSTRUMENT = "fret_instrument"
        const val STRINGS = "fret_strings"
        const val TUNING = "fret_tuning"
        const val HAND = "fret_hand"
        const val READS = "fret_reads"
    }
}
