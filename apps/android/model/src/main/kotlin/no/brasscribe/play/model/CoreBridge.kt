package no.brasscribe.play.model

/** A note found in audio, in seconds, before it is placed on a beat grid. */
data class TimedNote(
    val onsetS: Double,
    val offsetS: Double,
    val pitch: Int,
    val confidence: Double,
    val sources: List<String>,
)

/** One part of a MusicXML export: which voice, on which instrument, under which name. */
data class PartSpec(val voiceId: String, val name: String, val instrument: Instrument)

/** Arrangement choices of the Output screen, as the core and the engine name them. */
data class ArrangeOptions(
    /** The core's lineup: "band" (the full band), "minimal" or "quartet". */
    val lineup: String = "band",
    /** "faithful", "standard" or "easier". */
    val difficulty: String = "faithful",
    /** Concert key such as "Bb" or "-2:major"; exclusive with [transpose]. */
    val key: String? = null,
    /**
     * Semitones from the recording, -11..11; exclusive with [key]. It is the total: a composition that
     * is already transposed by that much (its `arrangement.transpose_semitones`) is not moved again.
     */
    val transpose: Int? = null,
    /** The player's seat ([Seat.id]): a solo take is written for it (one part, in the octave played); null: none. */
    val seat: String? = null,
    /** "treble" or "bass": the clef the seat's part is written in; null: the band part's own. */
    val reads: String? = null,
    /** "lineup" or "seat": who plays the tune (band lineups); null: the lineup's lead. */
    val lead: String? = null,
)

/** One seat of the contest band ("What do you play?"), from the core's table. */
data class Seat(
    val id: String,
    /** The part's English name, as the band score prints it ("2nd Cornet"). */
    val name: String,
    /** The part's Norwegian name («2. kornett»). */
    val nbName: String,
    /** Instrument id ("cornet", "tenor-horn", ...). */
    val instrument: String,
    /** The part's own clef: "treble", "bass" or "percussion". */
    val clef: String,
    /** Clefs the player may read it in, the part's own first; empty for percussion. */
    val reads: List<String>,
    /** Sounding minus written, semitones, of the part's instrument. */
    val chromatic: Int,
    /** The seat can carry the tune ("Who plays the tune?" offers it): the core's `tune`. */
    val tune: Boolean,
)

/** The player's part in a lineup for their seat: [part] null when the lineup has none. */
data class SeatPart(val part: String?, val exact: Boolean, val sameKey: Boolean)

/** Where a part comes from, as the core derives it from the arrangement. */
enum class PartSource(val id: String) {
    YOUR_RECORDING("your-recording"), RECORDING("recording"), ARRANGED("arranged"),

    /** Nothing to play in this arrangement (Percussion without drums, the Soprano Cornet with no climax). */
    EMPTY("empty");

    companion object {
        fun of(id: String): PartSource? = entries.firstOrNull { it.id == id }
    }
}

/** SwiftF0 frames of a solo take: where sustained notes really end (the core's written durations). */
data class Contour(val timesS: List<Double>, val pitchHz: List<Double>, val loudnessDb: List<Double>)

/**
 * What the phone heard in a solo take, per transcriber (seconds), plus the beat table
 * (`time position` lines, position 1 = downbeat) and the take itself as WAV.
 */
data class SoloTake(
    val title: String,
    val swiftF0: List<TimedNote>,
    val basicPitch: List<TimedNote>,
    val beatsText: String,
    val contour: Contour? = null,
    val wav: ByteArray? = null,
)

/** A band arrangement: the Composition, the full score and one MusicXML per part. */
data class Arranged(val composition: Composition, val compositionJson: String, val musicXml: String, val parts: List<Pair<String, String>>)

/** One bar of a part in the talking score: its heading and one line per event. */
data class BarLines(val heading: String, val lines: List<String>)

/** A talking score of an arranged score: every part of the MusicXML, spoken as the player reads it. */
interface TalkingScoreDoc : AutoCloseable {
    val partNames: List<String>
    val totalBars: Int
    fun partLines(part: Int, lang: Lang, pitchMode: PitchMode): List<BarLines>
    fun toHtml(lang: Lang, parts: List<Int>?): String
    override fun close() {}
}

/** A note of one part as played back (seconds of score time), after humanization. */
data class PlayedNote(val startS: Double, val endS: Double, val pitch: Int, val velocity: Int, val staccato: Boolean)

/** A note of one part as written: Composition ticks, score-time seconds, pitch and velocity. */
data class ScoreNote(val tick: Long, val durTicks: Long, val startS: Double, val endS: Double, val pitch: Int, val velocity: Int)

/**
 * The shared symbolic logic every Play app needs. [RustCoreBridge] (core-bridge module) implements it
 * with the Rust core over UniFFI; [KotlinCoreBridge] is the in-app fallback when the native library is
 * missing. Methods returning null mean "not available in this implementation".
 */
interface CoreBridge {
    val name: String

    fun decodeComposition(json: String): Composition
    fun encodeComposition(composition: Composition): String

    /** Concert spelling of [pitches] at [onsetsBeats] (ps13 in the core; [keyHint] only helps the fallback). */
    fun spell(onsetsBeats: List<Double>, pitches: List<Int>, keyHint: Int? = null): List<SpelledPitch>

    /** Places notes found in a solo recording on a beat grid at [bpm] (fallback when the core is missing). */
    fun quantizeSolo(notes: List<TimedNote>, bpm: Double, title: String): Composition

    /** A solo take arranged for brass band on the device: SwiftF0 spine confirmed by Basic Pitch. */
    fun arrangeSolo(take: SoloTake, options: ArrangeOptions): Arranged? = null

    /** Estimated major key (circle-of-fifths position) of the notes in [composition]. */
    fun estimateKey(composition: Composition): Int

    fun toMusicXml(composition: Composition, parts: List<PartSpec>): String

    /** The core's band arranger on a Composition ("auto", "minimal", "layers"). */
    fun arrangeMusicXml(composition: Composition, arranger: String): String? = null

    /**
     * The core's arranger on a Composition with a lineup, difficulty and key or transposition: the
     * layered arranger for a take with layers, else the small band or the quartet.
     */
    fun arrangeMusicXmlWith(composition: Composition, options: ArrangeOptions): String? = null

    fun announce(stop: TsStop, context: TsContext, settings: TsSettings, lang: Lang): String

    /** Per-part talking score of an arranged MusicXML score. */
    fun talkingScore(musicXml: String, compositionJson: String?): TalkingScoreDoc? = null

    /** Humanized playback of one part (realistic tier), player index = desk position. */
    fun humanize(notes: List<ScoreNote>, part: String, player: Int, compositionJson: String?): List<PlayedNote>? = null

    /** The contest band's 18 seats in score order; empty without the core. */
    fun seats(): List<Seat> = emptyList()

    /** Which part of [lineup] ("band", "minimal", "quartet") is the player's for [seat]; null without the core. */
    fun seatPart(lineup: String, seat: String): SeatPart? = null

    /** Where each part of the Composition's arrangement comes from, by part name; empty without the core. */
    fun partSources(compositionJson: String): Map<String, PartSource> = emptyMap()

    /** A part's Norwegian name from the core's one table; the name itself when unknown or without the core. */
    fun partNameNb(name: String): String = name
}

object KotlinCoreBridge : CoreBridge {
    override val name = "kotlin"

    override fun decodeComposition(json: String) = CompositionJson.decode(json)
    override fun encodeComposition(composition: Composition) = CompositionJson.encode(composition)
    override fun spell(onsetsBeats: List<Double>, pitches: List<Int>, keyHint: Int?): List<SpelledPitch> {
        val fifths = keyHint ?: KeyEstimator.estimate(pitches.mapIndexed { i, p -> Note(p, (onsetsBeats[i] * 24).toInt(), 24) })
        return pitches.map { SpelledPitch.spell(it, fifths) }
    }
    override fun quantizeSolo(notes: List<TimedNote>, bpm: Double, title: String) = SoloQuantizer.quantize(notes, bpm, title)
    override fun estimateKey(composition: Composition) = KeyEstimator.estimate(composition.voices.flatMap { it.notes })
    override fun toMusicXml(composition: Composition, parts: List<PartSpec>) = MusicXmlWriter.write(composition, parts)
    override fun announce(stop: TsStop, context: TsContext, settings: TsSettings, lang: Lang) =
        Announcer.announce(stop, context, settings, lang)
}
