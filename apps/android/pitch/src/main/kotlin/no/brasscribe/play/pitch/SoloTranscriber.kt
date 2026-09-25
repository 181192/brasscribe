package no.brasscribe.play.pitch

import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.TempoEstimator
import no.brasscribe.play.model.TimedNote

/** Result of an on-device solo transcription, with the numbers the UI reports. */
data class SoloResult(
    val composition: Composition,
    val bpm: Double,
    val notes: Int,
    val audioSeconds: Double,
    val detectMillis: Long,
)

/**
 * Offline path for one monophonic instrument (microphone or a solo file): SwiftF0 on the device,
 * note segmentation, then tempo, grid and key through the [CoreBridge]. No network, no engine.
 */
class SoloTranscriber(private val detector: SwiftF0, private val core: CoreBridge) {
    fun transcribe(
        audio: FloatArray,
        sampleRate: Int,
        title: String,
        bpm: Double? = null,
        onProgress: (Double) -> Unit = {},
    ): SoloResult {
        onProgress(0.05)
        val mono16k = Resampler.resample(audio, sampleRate, SwiftF0.SAMPLE_RATE)
        onProgress(0.2)
        val t0 = System.nanoTime()
        val track = detector.detect(mono16k)
        val detectMs = (System.nanoTime() - t0) / 1_000_000
        onProgress(0.8)
        val notes = NoteSegmenter.segment(track).map {
            TimedNote(it.start, it.end, it.midi, it.confidence, listOf("swiftf0"))
        }
        val tempo = bpm ?: TempoEstimator.estimate(notes.map { it.onsetS })
        val composition = core.quantizeSolo(notes, tempo, title)
        onProgress(1.0)
        return SoloResult(composition, tempo, notes.size, mono16k.size / SwiftF0.SAMPLE_RATE.toDouble(), detectMs)
    }
}
