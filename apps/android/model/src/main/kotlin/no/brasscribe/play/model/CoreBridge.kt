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

/**
 * The shared symbolic logic every Play app needs. The Rust core (`core/`, UniFFI Kotlin bindings)
 * implements this for all platforms; [KotlinCoreBridge] is the in-app implementation used until the
 * Rust library ships, and the reference the bindings are checked against.
 */
interface CoreBridge {
    val name: String

    fun decodeComposition(json: String): Composition
    fun encodeComposition(composition: Composition): String

    /** Places notes found in a solo recording on a beat grid at [bpm]. */
    fun quantizeSolo(notes: List<TimedNote>, bpm: Double, title: String): Composition

    /** Estimated major key (circle-of-fifths position) of the notes in [composition]. */
    fun estimateKey(composition: Composition): Int

    fun toMusicXml(composition: Composition, parts: List<PartSpec>): String

    fun announce(stop: TsStop, context: TsContext, settings: TsSettings, lang: Lang): String
}

object KotlinCoreBridge : CoreBridge {
    override val name = "kotlin"

    override fun decodeComposition(json: String) = CompositionJson.decode(json)
    override fun encodeComposition(composition: Composition) = CompositionJson.encode(composition)
    override fun quantizeSolo(notes: List<TimedNote>, bpm: Double, title: String) = SoloQuantizer.quantize(notes, bpm, title)
    override fun estimateKey(composition: Composition) = KeyEstimator.estimate(composition.voices.flatMap { it.notes })
    override fun toMusicXml(composition: Composition, parts: List<PartSpec>) = MusicXmlWriter.write(composition, parts)
    override fun announce(stop: TsStop, context: TsContext, settings: TsSettings, lang: Lang) =
        Announcer.announce(stop, context, settings, lang)
}
