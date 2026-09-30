package no.brasscribe.play.pitch

import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.Arranged
import no.brasscribe.play.model.BandTake
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.TimedNote

/** Stage of the band draft, for progress in plain words. */
enum class BandStage { PITCH, BEATS, ARRANGE }

/** Timings (ms) and counts of one band draft. */
data class BandStats(
    val audioSeconds: Double,
    val basicPitchNotes: Int,
    val beats: Int,
    val downbeats: Int,
    val ms: Map<BandStage, Long>,
    val totalMs: Long,
)

/** Nothing to write down: no notes were heard, or no steady beat (fewer than two beats or bars) was found. */
class NothingToArrangeException(message: String) : Exception(message)

/**
 * A band draft on the phone: the engine's brass-band profile without MuScriptor. Basic Pitch listens to the
 * whole mix, Beat This! small gives the beats, and the Rust core's song arranger writes the minimal band or the
 * quartet with Basic Pitch in the melody, bass and harmony slots.
 *
 * Without a beat grid the engine's song arranger stops ("too short to notate"), so this does too, rather than
 * inventing a steady tempo as the solo path may: a band take is not a solo line whose onsets carry the pulse.
 */
class BandDraftPipeline(
    private val basicPitch: BasicPitch,
    private val beatThis: BeatThis,
    private val core: CoreBridge,
) {
    /** Listens to a band take; [arrange] can be called again with other options without re-listening. */
    fun listen(audio: FloatArray, sampleRate: Int, title: String, onStage: (BandStage) -> Unit = {}): Pair<BandTake, BandStats> {
        val ms = LinkedHashMap<BandStage, Long>()
        val t0 = System.nanoTime()
        fun <T> timed(s: BandStage, f: () -> T): T {
            onStage(s)
            val a = System.nanoTime()
            return f().also { ms[s] = (System.nanoTime() - a) / 1_000_000 }
        }
        val notes = timed(BandStage.PITCH) {
            basicPitch.transcribe(audio, sampleRate).map { TimedNote(it.start, it.end, it.pitch, it.amplitude, listOf("basic-pitch")) }
        }
        if (notes.isEmpty()) throw NothingToArrangeException("no notes were heard")
        val beats = timed(BandStage.BEATS) { beatThis.track(audio, sampleRate) }
        if (beats.beats.size < 2 || beats.downbeats.size < 2) throw NothingToArrangeException("no steady beat was found")
        val take = BandTake(title, notes, beats.toBeatsText())
        val stats = BandStats(audio.size.toDouble() / sampleRate, notes.size, beats.beats.size, beats.downbeats.size, ms,
            (System.nanoTime() - t0) / 1_000_000)
        return take to stats
    }

    fun arrange(take: BandTake, options: ArrangeOptions): Arranged? = core.arrangeSong(take, options)

    companion object {
        /**
         * Native memory one second of audio needs while the draft runs, on top of the decoded samples the app
         * already holds: Basic Pitch's resampled input and its note, onset and contour frames, and Beat This!'s
         * spectrogram and logits. Generous, because ONNX Runtime's arena grows in steps.
         */
        const val BYTES_PER_SECOND = 1L shl 20

        /** The models, their sessions and the arranger, whatever the length. */
        const val FIXED_BYTES = 300L shl 20

        /** True when a take of [seconds] fits in [availableBytes] of free memory (ActivityManager's availMem). */
        fun fits(seconds: Double, availableBytes: Long): Boolean =
            FIXED_BYTES + (seconds * BYTES_PER_SECOND).toLong() <= availableBytes
    }
}
