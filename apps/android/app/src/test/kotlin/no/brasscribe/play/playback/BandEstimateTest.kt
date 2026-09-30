package no.brasscribe.play.playback

import alphaTab.midi.ControllerType
import alphaTab.midi.IMidiFileHandler
import alphaTab.midi.MidiFileGenerator
import alphaTab.model.Score
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import no.brasscribe.play.audio.PlaybackLevels
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * The band estimate from the notes alphaTab reads, against sounds/output-stage-vectors.json
 * (band_estimate_scores, whose notes sounds/playback_levels.py reads from the MusicXML itself).
 */
class BandEstimateTest {
    private val sounds: File? = System.getProperty("brasscribe.sounds")?.let(::File)?.takeIf { File(it, "output-stage-vectors.json").isFile }

    @Test fun scoresGiveTheSharedEstimate() {
        assumeTrue("sounds/output-stage-vectors.json not found", sounds != null)
        val root = sounds!!.parentFile
        val rows = Json.parseToJsonElement(File(sounds, "output-stage-vectors.json").readText()).jsonObject.getValue("band_estimate_scores").jsonArray
        assertEquals(2, rows.size)
        for (c in rows.map { it.jsonObject }) {
            val path = c.getValue("path").jsonPrimitive.content
            val xml = File(root, path).readText()
            val notes = BandEstimate.notes(xml.toByteArray())
            assertEquals(path, c.getValue("pitched_notes").jsonPrimitive.int, notes.size)
            assertEquals(path, c.getValue("estimate_lufs").jsonPrimitive.double, PlaybackLevels.bandEstimateLufs(notes)!!, 0.01)
            assertEquals(path, c.getValue("target_lufs").jsonPrimitive.double, BandEstimate.targetLufs(xml), 0.01)
        }
    }

    /** The golden arrangement (data/golden, when present): the estimate the offset was fitted on, and alphaTab's own velocities. */
    @Test fun goldenArrangementIsNearItsMeasuredLoudness() {
        val roots = listOfNotNull(System.getenv("BRASSCRIBE_REPO")?.let(::File), sounds?.parentFile)
        val golden = roots.map { File(it, "data/golden/mikkel-arranged-band/brass-band.musicxml") }.firstOrNull { it.isFile }
        assumeTrue("data/golden not found", golden != null)
        val score = BandEstimate.score(golden!!.readBytes())
        val e = PlaybackLevels.bandEstimateLufs(BandEstimate.notes(score))!!
        println("LEVELS android golden band estimate $e LUFS")
        assertEquals(-14.72, e, 0.05)  // with the offset fitted on two arrangements (-11.02 when it was fitted on the golden's held notes)
        // The velocity rule is alphaTab's: every note its MIDI generator plays has the velocity the estimate gives
        // the note that starts it (a tie chain plays once, at its first note's velocity).
        val estimated = BandEstimate.notes(score).map { it.velocity }.groupingBy { it }.eachCount()
        val played = generatorVelocities(score)
        assertEquals(played.keys, estimated.keys)
        for ((v, n) in played) assertEquals("velocity $v", n, estimated.getValue(v) - tieDestinations(score, v))
    }

    @Test fun noScoreOrAnUnreadableOneFallsBack() {
        assertEquals(PlaybackLevels.RECORDING_FALLBACK_LUFS, BandEstimate.targetLufs(null), 0.0)
        assertEquals(PlaybackLevels.RECORDING_FALLBACK_LUFS, BandEstimate.targetLufs("not a score"), 0.0)
    }

    private fun pitchedTracks(score: Score) = (0 until score.tracks.length.toInt()).filter { t ->
        val staves = score.tracks[t].staves
        (0 until staves.length.toInt()).none { staves[it].isPercussion }
    }.toSet()

    /** Tied-to notes at velocity [v] (their chain's first note's), which the MIDI generator does not play again. */
    private fun tieDestinations(score: Score, v: Double): Int {
        var n = 0
        for (t in pitchedTracks(score)) {
            val staves = score.tracks[t].staves
            for (s in 0 until staves.length.toInt()) for (b in 0 until staves[s].bars.length.toInt()) {
                val voices = staves[s].bars[b].voices
                for (vo in 0 until voices.length.toInt()) for (k in 0 until voices[vo].beats.length.toInt()) {
                    val beat = voices[vo].beats[k]
                    if (beat.isRest) continue
                    for (i in 0 until beat.notes.length.toInt()) {
                        val note = beat.notes[i]
                        if (note.isTieDestination && BandEstimate.velocity(note) == v) n++
                    }
                }
            }
        }
        return n
    }

    private fun generatorVelocities(score: Score): Map<Double, Int> {
        val pitched = pitchedTracks(score)
        val out = HashMap<Double, Int>()
        val handler = object : IMidiFileHandler {
            override fun addNote(track: Double, start: Double, length: Double, key: Double, velocity: Double, channel: Double) {
                if (track.toInt() in pitched) out.merge(velocity, 1, Int::plus)
            }
            override fun addTimeSignature(tick: Double, numerator: Double, denominator: Double) {}
            override fun addRest(track: Double, tick: Double, channel: Double) {}
            override fun addControlChange(track: Double, tick: Double, channel: Double, controller: ControllerType, value: Double) {}
            override fun addProgramChange(track: Double, tick: Double, channel: Double, program: Double) {}
            override fun addTempo(tick: Double, tempo: Double) {}
            override fun addNoteBend(track: Double, tick: Double, channel: Double, key: Double, value: Double) {}
            override fun addBend(track: Double, tick: Double, channel: Double, value: Double) {}
            override fun finishTrack(track: Double, tick: Double) {}
            override fun addTickShift(tickShift: Double) {}
        }
        MidiFileGenerator(score, alphaTab.Settings(), handler).generate()
        return out
    }
}
