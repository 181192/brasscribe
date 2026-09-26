package no.brasscribe.play.pitch

import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.Arranged
import no.brasscribe.play.model.Contour
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.MidiWriter
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.TempoEstimator
import no.brasscribe.play.model.TimedNote

/** Stage of the offline solo pipeline, for progress in plain words. */
enum class SoloStage { RESAMPLE, PITCH, CONFIRM, BEATS, ARRANGE }

/** Timings (ms) and counts of one on-device solo run. */
data class SoloStats(
    val audioSeconds: Double,
    val swiftF0Notes: Int,
    val basicPitchNotes: Int,
    val beats: Int,
    val downbeats: Int,
    val beatSource: String,
    val ms: Map<SoloStage, Long>,
    val totalMs: Long,
)

data class SoloArrangement(val take: SoloTake, val arranged: Arranged, val stats: SoloStats)

/**
 * The offline solo on the phone, the same rule as the engine's solo profile: SwiftF0 is the spine,
 * a note is confirmed when Basic Pitch also has it, the beat grid comes from Beat This! small, and
 * the Rust core arranges it (free time, written durations from the SwiftF0 contour, key, band parts).
 * Basic Pitch and Beat This are optional: without them notes stay unconfirmed and the grid is a
 * steady tempo estimated from the onsets.
 */
class SoloPipeline(
    private val swiftF0: SwiftF0,
    private val basicPitch: BasicPitch?,
    private val beatThis: BeatThis?,
    private val core: CoreBridge,
) {
    /** Transcribes a take; [arrange] can be called again with other options without re-listening. */
    fun listen(audio: FloatArray, sampleRate: Int, title: String, wav: ByteArray?, onStage: (SoloStage) -> Unit = {}): Pair<SoloTake, SoloStats> {
        val ms = LinkedHashMap<SoloStage, Long>()
        val t0 = System.nanoTime()
        fun <T> timed(s: SoloStage, f: () -> T): T {
            onStage(s)
            val a = System.nanoTime()
            return f().also { ms[s] = (System.nanoTime() - a) / 1_000_000 }
        }
        val mono16k = timed(SoloStage.RESAMPLE) { Resampler.resample(audio, sampleRate, SwiftF0.SAMPLE_RATE) }
        val track = timed(SoloStage.PITCH) { swiftF0.detect(mono16k) }
        val sw = NoteSegmenter.segment(track).map { TimedNote(it.start, it.end, it.midi, it.confidence, listOf("swiftf0")) }
        val bp = timed(SoloStage.CONFIRM) {
            basicPitch?.transcribe(audio, sampleRate)?.map { TimedNote(it.start, it.end, it.pitch, it.amplitude, listOf("basic-pitch")) }.orEmpty()
        }
        val beats = timed(SoloStage.BEATS) { beatThis?.track(audio, sampleRate) }
        val seconds = audio.size.toDouble() / sampleRate
        val beatsText = if (beats != null && beats.beats.size >= 2) beats.toBeatsText()
        else MidiWriter.steadyBeats(sw.firstOrNull()?.onsetS ?: 0.0, TempoEstimator.estimate(sw.map { it.onsetS }), seconds)
        val contour = Contour(List(track.size) { track.timeOf(it) }, track.pitchHz.toList(), track.loudnessDb.toList())
        val take = SoloTake(title, sw, bp, beatsText, contour, wav)
        val stats = SoloStats(seconds, sw.size, bp.size, beats?.beats?.size ?: 0, beats?.downbeats?.size ?: 0,
            if (beats != null) "beat-this" else "tempo estimate", ms, (System.nanoTime() - t0) / 1_000_000)
        return take to stats
    }

    fun arrange(take: SoloTake, options: ArrangeOptions): Arranged? = core.arrangeSolo(take, options)
}
