package no.brasscribe.play.engine

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

/*
 * The bass-tab profile: the job's options and its result (GET /v1/jobs/{id}/tab, the engine's schemas.Tab).
 * EngineContractTest checks the fields, their nullability and the enums against the vendored spec.
 */

/** A value of one of the API's string enums: [id] is what goes over the wire, null for the stand-in of a value this client does not know. */
interface WireEnum {
    val id: String?
}

/**
 * Reads and writes a [WireEnum] by its id. A value a newer engine added decodes as [unknown] instead of
 * failing the whole answer; [unknown] itself is never sent.
 */
open class WireEnumSerializer<E>(name: String, values: List<E>, private val unknown: E) : KSerializer<E> where E : Enum<E>, E : WireEnum {
    private val byId = values.mapNotNull { v -> v.id?.let { it to v } }.toMap()
    override val descriptor = PrimitiveSerialDescriptor("no.brasscribe.play.engine.$name", PrimitiveKind.STRING)
    override fun deserialize(decoder: Decoder): E = byId[decoder.decodeString()] ?: unknown
    override fun serialize(encoder: Encoder, value: E) =
        encoder.encodeString(value.id ?: throw SerializationException("${value.name} is not a value to send"))
}

/** The instrument a tab is written for, by its number of strings, with the tunings the engine has for it (standard first). */
@Serializable(with = FrettedInstrument.Serializer::class)
enum class FrettedInstrument(override val id: String?, val tunings: List<String>) : WireEnum {
    BASS_4("bass-4", listOf("standard", "eb-standard", "d-standard", "drop-d", "bead")),
    BASS_5("bass-5", listOf("standard", "drop-a")),
    BASS_6("bass-6", listOf("standard")),
    UNKNOWN(null, emptyList());

    /** The engine's preset id for this instrument in [tuning], as [Tab.preset] and [TuningFit.preset] name it. */
    fun preset(tuning: String = STANDARD_TUNING): String = "$id-$tuning"

    internal object Serializer : WireEnumSerializer<FrettedInstrument>("FrettedInstrument", entries, UNKNOWN)

    companion object {
        const val STANDARD_TUNING = "standard"
    }
}

/** Where the line sits on the neck. */
@Serializable(with = FingeringStyle.Serializer::class)
enum class FingeringStyle(override val id: String?) : WireEnum {
    /** The cheapest playable fingering. */
    AS_PLAYED("as-played"),
    /** Low frets and open strings. */
    OPEN_POSITION("open-position"),
    /** A phrase stays in one position. */
    LEAD("lead"),
    UNKNOWN(null);

    internal object Serializer : WireEnumSerializer<FingeringStyle>("FingeringStyle", entries, UNKNOWN)
}

/** What was recorded. */
@Serializable(with = Recording.Serializer::class)
enum class Recording(override val id: String?) : WireEnum {
    /** A band or a record: the bass is separated from it. */
    SONG("song"),
    /** The bass alone: no separation. */
    INSTRUMENT("instrument"),
    UNKNOWN(null);

    internal object Serializer : WireEnumSerializer<Recording>("Recording", entries, UNKNOWN)
}

/** The octave the line is written in. */
@Serializable(with = Octave.Serializer::class)
enum class Octave(override val id: String?) : WireEnum {
    /** An octave lower when the line was heard an octave above where a bass plays. */
    AUTO("auto"),
    /** As it was heard. */
    AS_HEARD("0"),
    DOWN("-12"),
    UP("+12"),
    UNKNOWN(null);

    internal object Serializer : WireEnumSerializer<Octave>("Octave", entries, UNKNOWN)
}

/** What the page shows. */
@Serializable(with = TabLayout.Serializer::class)
enum class TabLayout(override val id: String?) : WireEnum {
    /** The tab staff alone, with stems for the rhythm. */
    TAB("tab"),
    /** A notation staff above the tab. */
    TAB_AND_NOTATION("tab-and-notation"),
    /** The notation staff alone. */
    NOTATION("notation"),
    UNKNOWN(null);

    internal object Serializer : WireEnumSerializer<TabLayout>("TabLayout", entries, UNKNOWN)
}

/** Who decided [Tab.octaveShift]: the engine's octave check, or the job's octave option. */
@Serializable(with = OctaveSource.Serializer::class)
enum class OctaveSource(override val id: String?) : WireEnum {
    AUTO("auto"),
    CHOSEN("chosen"),
    UNKNOWN(null);

    internal object Serializer : WireEnumSerializer<OctaveSource>("OctaveSource", entries, UNKNOWN)
}

@Serializable(with = KeyMode.Serializer::class)
enum class KeyMode(override val id: String?) : WireEnum {
    MAJOR("major"),
    MINOR("minor"),
    UNKNOWN(null);

    internal object Serializer : WireEnumSerializer<KeyMode>("KeyMode", entries, UNKNOWN)
}

/**
 * The options of a bass-tab job. One left null is not sent, and the engine uses its default: a
 * four-string bass in standard tuning with no capo, as played, separated from a song, the octave
 * checked, the tab staff alone.
 */
data class TabOptions(
    val instrument: FrettedInstrument? = null,
    /** One of the instrument's [FrettedInstrument.tunings]. */
    val tuning: String? = null,
    /** The capo's fret, 0 (none) to [MAX_CAPO]; frets in the tab are counted from it. */
    val capo: Int? = null,
    val style: FingeringStyle? = null,
    val recording: Recording? = null,
    val octave: Octave? = null,
    val layout: TabLayout? = null,
) {
    /** The options as form fields, for a job made from an upload. */
    internal fun formFields(): List<Pair<String, String>> = listOfNotNull(
        instrument?.let { "instrument" to it.wire() }, tuning?.let { "tuning" to it }, capo?.let { "capo" to it.toString() },
        style?.let { "style" to it.wire() }, recording?.let { "recording" to it.wire() }, octave?.let { "octave" to it.wire() },
        layout?.let { "layout" to it.wire() },
    )

    private fun <E> E.wire(): String where E : Enum<E>, E : WireEnum = id ?: throw IllegalArgumentException("$name is not a value to send")

    companion object {
        const val MAX_CAPO = 12
    }
}

/** A place on the neck. */
@Serializable
data class TabPosition(
    /** 1 is the highest line of the tab. */
    val string: Int,
    /** Counted from the capo; 0 is the open string. */
    val fret: Int,
)

/** One note of the tab: when it sounds, what was heard, and where it is played. */
@Serializable
data class TabNote(
    /** Concert MIDI pitch, as written in the tab (after [Tab.octaveShift]). */
    val pitch: Int,
    /** Ticks from the first downbeat. */
    val start: Int,
    /** Written duration in ticks. */
    val dur: Int,
    /** Null: the note has no place on the instrument. */
    val string: Int?,
    /** The other places that sound this pitch, cheapest first. */
    val alternatives: List<TabPosition>,
    /** No string of the instrument sounds this pitch; the usual cause is another tuning or instrument than the player's. */
    @SerialName("out_of_range") val outOfRange: Boolean,
    val fret: Int? = null,
    /** 0 to 1; below [DOUBT] the note is one to check (the tab marks it "?"). */
    val confidence: Double = 1.0,
    @SerialName("onset_s") val onsetS: Double? = null,
    @SerialName("offset_s") val offsetS: Double? = null,
    /** The player chose this string. */
    val pinned: Boolean = false,
    /** Written an octave below where the first transcriber heard it, where the second heard it. It gets no "?". */
    @SerialName("octave_moved") val octaveMoved: Boolean = false,
) {
    /** Where the note is played; null when it has no place on the instrument. */
    val position: TabPosition? get() = if (string != null && fret != null) TabPosition(string, fret) else null

    /** One to check. */
    val doubtful: Boolean get() = confidence < DOUBT

    companion object {
        const val DOUBT = 0.4
    }
}

@Serializable
data class TabString(
    /** MIDI pitch of the open string, without the capo. */
    @SerialName("open_pitch") val openPitch: Int,
    /** Where a short string starts (a banjo's fifth string); 0: at the nut. */
    @SerialName("first_fret") val firstFret: Int = 0,
)

@Serializable
data class TabTuning(
    /** Display name, e.g. Drop D. */
    val name: String,
    /** String 1 first. */
    val strings: List<TabString>,
)

@Serializable
data class TabInstrument(
    val name: String,
    val tuning: TabTuning,
    val frets: Int,
    @SerialName("scale_length_mm") val scaleLengthMm: Double,
    val capo: Int = 0,
)

/**
 * A hard playability violation. [kind] is shared-string, span-too-wide, fret-out-of-range, wrong-pitch,
 * pin-not-honoured, no-string, technique-string, technique-reach, bend-on-open-string or ring-cut; the
 * other fields depend on it (the engine's schema names only [kind]) and name notes by their index in
 * [Tab.notes].
 */
@Serializable
data class TabViolation(
    val kind: String,
    val note: Int? = null,
    val notes: List<Int>? = null,
    val string: Int? = null,
    val fret: Int? = null,
    /** The note a technique comes from. */
    val previous: Int? = null,
    /** How far a technique reaches, in frets. */
    val frets: Int? = null,
    @SerialName("span_mm") val spanMm: Double? = null,
    /** The let-ring note that still holds the string. */
    val ringing: Int? = null,
) {
    /** Every note the violation names, as indices into [Tab.notes]. */
    val noteIndices: List<Int> get() = (listOfNotNull(note, previous, ringing) + notes.orEmpty()).distinct().sorted()
}

/** How well one tuning of the instrument fits the notes. */
@Serializable
data class TuningFit(
    /** `<instrument>-<tuning>`, e.g. bass-4-drop-d. */
    val preset: String,
    /** Display name, e.g. Drop D. */
    val tuning: String,
    /** Notes no string can sound. */
    @SerialName("out_of_range") val outOfRange: Int,
    /** The lowest note is exactly the lowest open string. */
    @SerialName("low_string_fits") val lowStringFits: Boolean,
    /** Notes an open string can play. */
    @SerialName("open_notes") val openNotes: Int,
    /** Notes that can only be played above the 12th fret. */
    @SerialName("high_frets") val highFrets: Int,
    /** Semitones from the standard tuning, summed over the strings. */
    val distance: Int,
)

@Serializable
data class TabKey(
    /** Tonic and mode, e.g. G or Em. */
    val name: String,
    val fifths: Int,
    val mode: KeyMode,
)

@Serializable
data class TabMeter(val beats: Int, @SerialName("beat_unit") val beatUnit: Int = 4)

@Serializable
data class ReferencePitch(
    /** Offset of the recording from A = 440, -50 to 50; positive is sharp. */
    val cents: Double,
    /** How well the recording agrees on it, 0 to 1. */
    val concentration: Double,
    /** The notes were transcribed from the recording retuned to A = 440. */
    val retuned: Boolean,
)

/**
 * The bass-tab profile's result: every note with its string and fret, and what the song check shows
 * before the tab (tuning, reference pitch, capo, octave, key and tempo).
 */
@Serializable
data class Tab(
    /** The instrument and tuning the tab was made for, e.g. bass-4-standard. */
    val preset: String,
    val style: FingeringStyle,
    val instrument: TabInstrument,
    /** In time order; violations name notes by their index here. */
    val notes: List<TabNote>,
    /** Empty when the tab is playable as written. */
    val violations: List<TabViolation>,
    /** The instrument's tunings ranked by fit to the notes, best first; when the first is not [preset], the song sounds like that tuning. */
    @SerialName("tuning_suggestions") val tuningSuggestions: List<TuningFit>,
    /** What tab.musicxml (and the PDF made from it) shows. */
    val layout: TabLayout,
    /** Notes written at the nearest start or length a note value can spell; in tab.musicxml only, [notes] are unchanged. */
    @SerialName("adjusted_notes") val adjustedNotes: Int,
    /** Semitones the whole line was moved after transcription: 0, -12 or -24 from the octave check, or the chosen 0, -12 or 12. */
    @SerialName("octave_shift") val octaveShift: Int,
    @SerialName("octave_source") val octaveSource: OctaveSource,
    /** Null when the recording's tuning could not be measured. */
    @SerialName("reference_pitch") val referencePitch: ReferencePitch?,
    @SerialName("tempo_bpm") val tempoBpm: Double,
    val key: TabKey,
    val meter: TabMeter,
    /** Seconds of beat 0, 1, 2 ... */
    @SerialName("beat_times") val beatTimes: List<Double>,
    /** Index into [beatTimes] of tick 0; negative when the line starts before the first tracked downbeat (a pickup). */
    @SerialName("first_downbeat") val firstDownbeat: Int,
    /** Single notes written an octave lower than they were heard (with the octave on auto). */
    @SerialName("octave_notes_moved") val octaveNotesMoved: Int = 0,
    @SerialName("ticks_per_beat") val ticksPerBeat: Int = 24,
) {
    /** The tuning the song sounds like when it is not the one the tab was made for; null when [preset] fits best. */
    val suggestedTuning: TuningFit? get() = tuningSuggestions.firstOrNull()?.takeIf { it.preset != preset }
}
