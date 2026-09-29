package no.brasscribe.play.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * The canonical score shared by every Brasscribe app: concert pitch, integer ticks.
 *
 * Mirrors `brasscribe_music.score_model.Composition`. Unknown fields are ignored on decode so newer
 * engines can add fields without breaking older apps.
 */
@Serializable
data class Composition(
    val title: String,
    val voices: List<Voice>,
    val meters: List<Meter>,
    val keys: List<KeySig>,
    /** Seconds of beat 0, 1, 2 … of the recording (the tempo map). */
    @SerialName("beat_times") val beatTimes: List<Double> = emptyList(),
    /** Index into [beatTimes] of tick 0. Negative when the recording starts after the first downbeat. */
    @SerialName("first_downbeat") val firstDownbeat: Int = 0,
    @SerialName("ticks_per_beat") val ticksPerBeat: Int = DEFAULT_TICKS_PER_BEAT,
    @SerialName("free_regions") val freeRegions: List<FreeRegion> = emptyList(),
    /**
     * Neighbouring uncertain notes of one voice to review together (music/README.md, "Confidence and
     * review marks"): [start, end) ticks. Null when the engine did not group them; then every marked
     * note is its own item.
     */
    val review: List<ReviewItem>? = null,
    /**
     * The options the arrangement was made with (`lineup`, `difficulty`, `transpose_semitones`, …), as
     * the core and the engine record them; null means the defaults. Kept whole so a re-encode keeps it.
     */
    val arrangement: JsonObject? = null,
    /** The beat grid is a guess from the onsets (the tracker found under two beats); the score says "tempo?". */
    @SerialName("tempo_estimated") val tempoEstimated: Boolean = false,
) {
    val endTick: Int get() = voices.maxOfOrNull { v -> v.notes.maxOfOrNull { it.end } ?: 0 } ?: 0
    val startTick: Int get() = minOf(0, voices.minOfOrNull { v -> v.notes.minOfOrNull { it.start } ?: 0 } ?: 0)

    fun voice(id: String): Voice? = voices.firstOrNull { it.id == id }

    fun freeRegionAt(tick: Int): FreeRegion? = freeRegions.firstOrNull { tick >= it.start && tick < it.end }

    /** Median tempo of the gridded passages, 120 when there is no tempo map. */
    val bpm: Double
        get() {
            if (beatTimes.size < 2) return 120.0
            val strict = beatTimes.zipWithNext().withIndex()
                .filter { (i, _) -> freeRegionAt((i - firstDownbeat) * ticksPerBeat) == null }
                .map { (_, p) -> p.second - p.first }
            val diffs = strict.ifEmpty { beatTimes.zipWithNext { a, b -> b - a } }.sorted()
            return 60.0 / diffs[diffs.size / 2]
        }

    companion object {
        const val DEFAULT_TICKS_PER_BEAT = 24
    }
}

@Serializable
enum class VoiceRole {
    @SerialName("melody") MELODY,
    @SerialName("countermelody") COUNTERMELODY,
    @SerialName("harmony") HARMONY,
    @SerialName("bass") BASS,
    @SerialName("rhythm") RHYTHM,
}

@Serializable
data class Voice(
    val id: String,
    val role: VoiceRole,
    val notes: List<Note>,
    /** What the source instrument seemed to be; never binding. */
    @SerialName("instrument_hint") val instrumentHint: String? = null,
    /** Textural layer it came from: solo, strings, brass, keys, bass, drums. */
    val layer: String? = null,
)

@Serializable
data class Note(
    /** Concert MIDI pitch. */
    val pitch: Int,
    /** Ticks from the first downbeat (negative in a pickup). */
    val start: Int,
    /** Notated duration in ticks. */
    val dur: Int,
    val confidence: Double = 1.0,
    val sources: List<String> = emptyList(),
    @SerialName("onset_s") val onsetS: Double? = null,
    @SerialName("offset_s") val offsetS: Double? = null,
    /** Performed length in ticks; null when unknown. */
    @SerialName("performed_dur") val performedDur: Int? = null,
    val articulations: List<Articulation> = emptyList(),
    /** A trill mark: semitones up to the auxiliary; kept so a re-arrangement in the core keeps it. */
    val trill: Int? = null,
) {
    val end: Int get() = start + dur
    val uncertainty: Uncertainty get() = Uncertainty.of(confidence)
}

@Serializable
enum class Articulation {
    @SerialName("staccato") STACCATO,
    @SerialName("fermata") FERMATA,
    @SerialName("accent") ACCENT,
    @SerialName("tenuto") TENUTO,
    @SerialName("marcato") MARCATO,
}

/** One review item: `notes` marked notes of [voice] in [start, end) ticks; `very` when any is very unsure. */
@Serializable
data class ReviewItem(val voice: String, val start: Int, val end: Int, val notes: Int = 1, val very: Boolean = false)

@Serializable
data class Meter(val tick: Int, val beats: Int, @SerialName("beat_unit") val beatUnit: Int = 4)

@Serializable
data class KeySig(val tick: Int, val fifths: Int, val mode: String = "major")

/** A passage in free time (ad lib.): no beat grid was imposed on it. Span [start, end) in ticks. */
@Serializable
data class FreeRegion(
    val start: Int,
    val end: Int,
    @SerialName("start_s") val startS: Double,
    @SerialName("end_s") val endS: Double,
    @SerialName("tempo_bpm") val tempoBpm: Double,
    val notation: FreeNotation = FreeNotation.PROPORTIONAL,
    val label: String = "ad lib.",
)

@Serializable
enum class FreeNotation {
    @SerialName("proportional") PROPORTIONAL,
    @SerialName("tempo") TEMPO,
}
