package no.brasscribe.play.score

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.math.pow

/** How one part sounds: preset (0-based program, bank), its balance in the band, and whether it is the kit. */
data class TrackSound(val program: Int, val bank: Int, val gainDb: Double = 0.0, val percussion: Boolean = false) {
    val gain: Double get() = 10.0.pow(gainDb / 20)
}

/**
 * The part map of the band SoundFont (sounds/band.py builds brasscribe-band.sf2; sounds/mapping.json
 * parts[].band_soundfont): every brass part has its own preset at (bank, GM program), drums are bank
 * 128 on MIDI channel 10, and the balance is a channel gain (channel_gain_db) because the SoundFont
 * does not store it.
 */
class BandSoundMap(private val parts: Map<String, TrackSound>) {
    fun forPart(name: String): TrackSound? = parts[normalize(name)]
    val size: Int get() = parts.size

    companion object {
        fun parse(mappingJson: String): BandSoundMap {
            val root = Json.parseToJsonElement(mappingJson).jsonObject
            val parts = root.getValue("parts").jsonObject.mapNotNull { (name, v) ->
                val b = v.jsonObject["band_soundfont"]?.jsonObject ?: return@mapNotNull null
                val bank = b.getValue("bank").jsonPrimitive.int
                normalize(name) to TrackSound(b.getValue("program").jsonPrimitive.int, bank,
                    b["channel_gain_db"]?.jsonPrimitive?.double ?: 0.0, bank == 128)
            }.toMap()
            return BandSoundMap(parts)
        }

        fun normalize(name: String) = name.replace(' ', ' ').replace("♭", "b").replace("♯", "#").trim().lowercase()
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
