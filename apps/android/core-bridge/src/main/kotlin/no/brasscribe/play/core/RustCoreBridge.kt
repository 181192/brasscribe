package no.brasscribe.play.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.put
import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.Arranged
import no.brasscribe.play.model.BarLines
import no.brasscribe.play.model.BrasscribeJson
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.CompositionJson
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.KotlinCoreBridge
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.MidiWriter
import no.brasscribe.play.model.PartSpec
import no.brasscribe.play.model.PitchMode
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.SpelledPitch
import no.brasscribe.play.model.TalkingScoreDoc
import no.brasscribe.play.model.TimedNote
import no.brasscribe.play.model.TsContext
import no.brasscribe.play.model.TsPart
import no.brasscribe.play.model.TsSettings
import no.brasscribe.play.model.TsStop
import no.brasscribe.play.model.Verbosity
import uniffi.brasscribe_ffi.LayerMidi
import uniffi.brasscribe_ffi.LayerStems
import uniffi.brasscribe_ffi.Performance
import uniffi.brasscribe_ffi.SoloContour
import uniffi.brasscribe_ffi.TalkingSettings
import uniffi.brasscribe_ffi.arrangeLayersBand
import uniffi.brasscribe_ffi.arrangeMusicxml
import uniffi.brasscribe_ffi.arrangeMusicxmlWith
import uniffi.brasscribe_ffi.coreVersion
import uniffi.brasscribe_ffi.estimateKey
import uniffi.brasscribe_ffi.humanizePart
import uniffi.brasscribe_ffi.layersSongDefaults
import uniffi.brasscribe_ffi.normalizeComposition
import uniffi.brasscribe_ffi.spellPitches
import uniffi.brasscribe_ffi.talkingAnnounceJson
import uniffi.brasscribe_ffi.ArrangeOptions as CoreArrangeOptions
import uniffi.brasscribe_ffi.ScoreNote as CoreScoreNote
import uniffi.brasscribe_ffi.TalkingScore as CoreTalkingScore
import no.brasscribe.play.model.PlayedNote as ModelPlayedNote
import no.brasscribe.play.model.ScoreNote as ModelScoreNote

/**
 * [CoreBridge] on the Rust core (core/, UniFFI over JNA): ps13 spelling, the band arranger with
 * lineup, difficulty and key, the talking score of arranged scores, and playback humanization. The
 * solo quantizer and the monophonic MusicXML writer of app-made parts stay in Kotlin.
 */
class RustCoreBridge private constructor(val version: String) : CoreBridge {
    override val name = "rust $version"

    override fun decodeComposition(json: String): Composition = CompositionJson.decode(normalizeComposition(json))
    override fun encodeComposition(composition: Composition): String = CompositionJson.encode(composition)

    override fun spell(onsetsBeats: List<Double>, pitches: List<Int>, keyHint: Int?): List<SpelledPitch> =
        if (pitches.isEmpty()) emptyList() else spellPitches(onsetsBeats, pitches).map { SpelledPitch(it.step, it.alter, it.octave) }

    override fun quantizeSolo(notes: List<TimedNote>, bpm: Double, title: String) = KotlinCoreBridge.quantizeSolo(notes, bpm, title)

    override fun arrangeSolo(take: SoloTake, options: ArrangeOptions): Arranged {
        val sw = MidiWriter.write(take.swiftF0)
        val bp = MidiWriter.write(take.basicPitch, tpq = MidiWriter.BASIC_PITCH_TPQ)
        // The layered arranger with only a solo layer: SwiftF0 spine, Basic Pitch confirming in the
        // MuScriptor slot too (the phone has no MuScriptor), as the other apps and the reference do.
        val layers = LayerMidi(sw, bp, bp, MidiWriter.EMPTY, MidiWriter.EMPTY, MidiWriter.EMPTY)
        val opts = layersSongDefaults().apply {
            soloContour = take.contour?.let { SoloContour(it.timesS, it.pitchHz, it.loudnessDb) }
            lineup = coreLineup(options.lineup)
            difficulty = options.difficulty
            key = options.key
            transpose = options.transpose
        }
        val out = arrangeLayersBand(layers, LayerStems(solo = take.wav), take.beatsText, take.title, opts)
        return Arranged(CompositionJson.decode(out.compositionJson), out.compositionJson, out.musicxml, out.parts.map { it.fileName to it.musicxml })
    }

    override fun estimateKey(composition: Composition): Int {
        val notes = composition.voices.flatMap { it.notes }
        if (notes.isEmpty()) return 0
        return estimateKey(notes.map { it.dur.toDouble() / composition.ticksPerBeat }, notes.map { it.pitch }).fifths
    }

    override fun toMusicXml(composition: Composition, parts: List<PartSpec>) = KotlinCoreBridge.toMusicXml(composition, parts)

    override fun arrangeMusicXml(composition: Composition, arranger: String): String =
        arrangeMusicxml(CompositionJson.encode(composition), arranger)

    override fun arrangeMusicXmlWith(composition: Composition, options: ArrangeOptions): String =
        arrangeMusicxmlWith(CompositionJson.encode(composition),
            CoreArrangeOptions(coreLineup(options.lineup), options.difficulty, options.key, options.transpose))

    /** The core's announcer, fed the same event JSON as docs/accessibility/talking-score-vectors.json. */
    override fun announce(stop: TsStop, context: TsContext, settings: TsSettings, lang: Lang): String {
        val json = BrasscribeJson
        val part = stop.part ?: TsPart(context.part.orEmpty())
        val bar = stop.bar?.let { b ->
            buildJsonObject {
                put("number", b.number)
                put("key_fifths", b.keyFifths ?: stop.keyFifths)
                put("key_changed", b.keyFifths != null && b.keyFifths != stop.keyFifths)
                b.tempoBpm?.let { put("tempo_bpm", it) }
                put("a_tempo", b.aTempo)
                b.rehearsal?.let { put("rehearsal", it) }
                b.freeRegion?.let { r ->
                    put("free_region", json.encodeToJsonElement(r.copy(entering = false)))
                    put("entering_region", r.entering)
                }
                stop.totalBars?.let { put("total_bars", it) }
            }
        }
        val request = buildJsonObject {
            put("part", json.encodeToJsonElement(part))
            bar?.let { put("bar", it) }
            put("event", json.encodeToJsonElement(stop.event))
            put("context", json.encodeToJsonElement(context))
            put("settings", JsonObject(mapOf(
                "lang" to JsonPrimitive(lang.code), "verbosity" to JsonPrimitive(settings.verbosity.code),
                "pitch_mode" to JsonPrimitive(settings.pitchMode.code),
            )))
        }
        return talkingAnnounceJson(request.toString())
    }

    override fun talkingScore(musicXml: String, compositionJson: String?): TalkingScoreDoc = Doc(CoreTalkingScore(musicXml, compositionJson))

    private class Doc(private val ts: CoreTalkingScore) : TalkingScoreDoc {
        override val partNames: List<String> = ts.partNames()
        override val totalBars: Int = ts.totalBars().toInt()
        override fun partLines(part: Int, lang: Lang, pitchMode: PitchMode): List<BarLines> =
            ts.partLines(part.toUInt(), settings(lang, pitchMode)).map { BarLines(it.heading, it.lines) }
        override fun toHtml(lang: Lang, parts: List<Int>?): String =
            ts.toHtml(settings(lang, PitchMode.WRITTEN), parts?.map { it.toUInt() })
        override fun close() = ts.close()
    }

    override fun humanize(notes: List<ModelScoreNote>, part: String, player: Int, compositionJson: String?): List<ModelPlayedNote> {
        val perf = compositionJson?.let { Performance(it) }
        try {
            val out = humanizePart(notes.map { CoreScoreNote(it.tick, it.durTicks, it.startS, it.endS, it.pitch, it.velocity.toLong()) },
                part, player.toLong(), "brasscribe", perf, false)
            return out.notes.map { ModelPlayedNote(it.start, it.end, it.pitch, it.velocity.toInt(), it.staccato) }
        } finally {
            perf?.close()
        }
    }

    companion object {
        /** The core, or null when its native library is not in this build. */
        fun load(): RustCoreBridge? = try {
            RustCoreBridge(coreVersion())
        } catch (e: Throwable) {
            null
        }

        /** The core's name of a lineup. An unknown name is an error, never quietly the full band. */
        fun coreLineup(name: String): String = when (name) {
            "band", "full" -> "band"
            "minimal" -> "minimal"
            "quartet" -> "quartet"
            else -> throw IllegalArgumentException("unknown lineup $name")
        }

        private fun settings(lang: Lang, mode: PitchMode) = TalkingSettings(
            lang = lang.code, pitchMode = mode.code, verbosity = "standard", octaveStyle = "scientific", announceConfident = false,
        )

        private val Lang.code get() = if (this == Lang.NB) "nb" else "en"
        private val PitchMode.code get() = if (this == PitchMode.CONCERT) "concert" else "written"
        private val Verbosity.code get() = name.lowercase()
    }
}
