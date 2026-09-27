package no.brasscribe.play.score

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.math.pow

/**
 * How one part sounds: preset (0-based program, bank), its balance in the band, and whether it is the kit.
 * [part] is the mapping.json part whose preset plays and [target] its first desk's built instrument
 * (the SFZ folder of the realistic tier); [step] says which resolve rule found it.
 *
 * [gainDb] is channel_gain_db, for the band SoundFont preset (a layered cornet preset sounds two
 * targets, and channel_gain_db takes 3 dB off for that). [singleVoiceGainDb] is single_voice_gain_db,
 * for a voice that sounds one target only: the realistic tier's one SFZ per part.
 */
data class TrackSound(
    val program: Int, val bank: Int, val gainDb: Double = 0.0, val percussion: Boolean = false,
    val part: String = "", val target: String? = null, val step: String = "exact",
    val singleVoiceGainDb: Double = gainDb,
) {
    val gain: Double get() = 10.0.pow(gainDb / 20)
    val singleVoiceGain: Double get() = 10.0.pow(singleVoiceGainDb / 20)
}

/**
 * The part map of the band SoundFont (sounds/band.py builds brasscribe-band.sf2; sounds/mapping.json
 * parts[].band_soundfont): every brass part has its own preset at (bank, GM program), drums are bank
 * 128 on MIDI channel 10, and the balance is a channel gain (channel_gain_db) because the SoundFont
 * does not store it.
 *
 * [resolve] follows mapping.json `resolve` step for step (sounds/partsound.py is the reference and
 * sounds/partsound-vectors.json the shared test vectors): exact name, alias, keyword, instrument id,
 * GM program. A brass part therefore always gets a band preset; only a non-brass GM program is left
 * unresolved.
 */
class BandSoundMap private constructor(
    private val parts: Map<String, TrackSound>,
    private val aliases: Map<String, String>,
    private val keywords: List<Pair<String, String>>,
    private val instruments: Map<String, String>,
    private val programs: Map<Int, String>,
) {
    /** Exact-name lookup only (step 1). */
    fun forPart(name: String): TrackSound? = parts[normalize(name)]

    fun resolve(name: String, instrument: String? = null, program: Int? = null): TrackSound? {
        val n = normalize(name)
        parts[n]?.let { return it }
        aliases[n]?.let { return byName(it, "alias") }
        keywords.firstOrNull { (kw, _) -> kw in n }?.let { return byName(it.second, "keyword") }
        if (instrument != null) instruments[instrument]?.let { return byName(it, "instrument") }
        if (program != null) programs[program]?.let { return byName(it, "program") }
        return null
    }

    private fun byName(part: String, step: String) = parts[normalize(part)]?.copy(step = step)

    val size: Int get() = parts.size

    companion object {
        fun parse(mappingJson: String): BandSoundMap {
            val root = Json.parseToJsonElement(mappingJson).jsonObject
            val parts = root.getValue("parts").jsonObject.mapNotNull { (name, v) ->
                val o = v.jsonObject
                val b = o["band_soundfont"]?.jsonObject ?: return@mapNotNull null
                val bank = b.getValue("bank").jsonPrimitive.int
                val target = (o["players"] as? JsonArray)?.firstOrNull()?.jsonObject?.get("target")?.jsonPrimitive?.content
                val gain = b["channel_gain_db"]?.jsonPrimitive?.double ?: 0.0
                normalize(name) to TrackSound(b.getValue("program").jsonPrimitive.int, bank, gain, bank == 128, name,
                    target?.takeIf { bank != 128 }, singleVoiceGainDb = b["single_voice_gain_db"]?.jsonPrimitive?.double ?: gain)
            }.toMap()
            val r = root["resolve"] as? JsonObject
            fun strings(key: String) = (r?.get(key) as? JsonObject)?.mapValues { it.value.jsonPrimitive.content }.orEmpty()
            val keywords = (r?.get("keywords") as? JsonArray)?.map {
                val a = it.jsonArray
                a[0].jsonPrimitive.content to a[1].jsonPrimitive.content
            }.orEmpty()
            return BandSoundMap(parts, strings("aliases"), keywords, strings("instruments"),
                strings("programs").mapKeys { it.key.toInt() })
        }

        /** mapping.json `resolve.normalize`: lowercase, ♭ → b, ♯ → #, whitespace runs (incl. U+00A0) → one space, trim. */
        fun normalize(name: String) = name.lowercase().replace("♭", "b").replace("♯", "#")
            .replace(' ', ' ').replace(Regex("\\s+"), " ").trim()
    }
}

/**
 * MIDI channels for playback. alphaTab gives each track two channels in import order, so an 18-part
 * band wraps past 16: parts share channels (and so each other's program and bank) and one lands on
 * the drum channel. Here every track gets one channel of its own and percussion gets channel 10
 * (index 9); alphaTab's synth has more than 16 channels, and index 16 is its metronome.
 */
object ChannelPlan {
    const val DRUMS = 9
    const val METRONOME = 16

    fun forPlayback(percussion: List<Boolean>): IntArray {
        var next = 0
        return IntArray(percussion.size) { i ->
            if (percussion[i]) DRUMS else {
                while (next == DRUMS || next == METRONOME) next++
                next++
            }
        }
    }
}

/** A note's life on one channel and pitch: [start] to [end], in seconds. */
data class TimedNote(val start: Double, val end: Double, val pitch: Int)

/**
 * Note-offs that cannot cut a later note: on one channel a note-off ends every voice of that pitch,
 * so a note that lasts past the next onset of the same pitch (humanized timing, unisons merged onto
 * one part) would end that next note early. Each such note is trimmed to end [gapS] before the next
 * onset, as sounds/render.py write_midi does for the offline renders.
 */
object SamePitchTrim {
    /** Trimmed notes, in input order; `null` for a note that starts together with the next one of its pitch (that one plays it). */
    fun trim(notes: List<TimedNote>, gapS: Double = 0.005, minS: Double = 0.01): List<TimedNote?> {
        val order = notes.indices.sortedWith(compareBy({ notes[it].start }, { it }))
        val nextStart = HashMap<Int, Double>()
        val out = notes.toMutableList<TimedNote?>()
        for (i in order.reversed()) {
            val n = notes[i]
            val nxt = nextStart[n.pitch]
            if (nxt != null && n.end > nxt - gapS) {
                out[i] = if (nxt - gapS < n.start + minS) null else n.copy(end = nxt - gapS)
            }
            if (out[i] != null) nextStart[n.pitch] = n.start
        }
        return out
    }
}
