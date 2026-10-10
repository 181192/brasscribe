package no.brasscribe.play

import android.content.Context
import android.system.Os
import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.BandTake
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.pitch.BandDraftPipeline
import no.brasscribe.play.pitch.BasicPitch
import no.brasscribe.play.pitch.BeatThis
import no.brasscribe.play.pitch.SoloPipeline
import no.brasscribe.play.pitch.SwiftF0

/**
 * Brasscribe on the phone: SwiftF0, Basic Pitch and Beat This! small on ONNX Runtime (the `pitch` module), from
 * the models bundled as assets when they were present at build time (models/convert), arranged by [core].
 */
class OnPhoneModels(private val context: Context, private val core: CoreBridge) : OnPhone {
    override val hasPitchModel: Boolean by lazy { has(MODEL_ASSET) }
    override val hasBandModels: Boolean by lazy { has(BASIC_PITCH_ASSET) && has(BEAT_THIS_ASSET) }

    override fun bandDraftFits(seconds: Double, freeBytes: Long) = BandDraftPipeline.fits(seconds, freeBytes)

    fun openPitchModel(): SwiftF0 = SwiftF0(asset(MODEL_ASSET)!!, threads = 2)

    /** SwiftF0 plus Basic Pitch and Beat This! small when their models are bundled. */
    override fun openSolo(): OnPhone.Solo {
        val sw = openPitchModel()
        val bp = asset(BASIC_PITCH_ASSET)?.let { BasicPitch(it) }
        val bt = asset(BEAT_THIS_ASSET)?.let { BeatThis(it) }
        val pipeline = SoloPipeline(sw, bp, bt, core)
        val models = listOfNotNull(sw, bp, bt)
        return object : OnPhone.Solo {
            override fun listen(audio: FloatArray, sampleRate: Int, title: String, wav: ByteArray?, onStage: (Int) -> Unit): Pair<SoloTake, String> {
                val (take, stats) = pipeline.listen(audio, sampleRate, title, wav) { onStage(it.ordinal) }
                return take to "%.1f s audio, SwiftF0 %d notes, Basic Pitch %d, beats %d (%s), downbeats %d, stages %s ms"
                    .format(stats.audioSeconds, stats.swiftF0Notes, stats.basicPitchNotes, stats.beats, stats.beatSource, stats.downbeats,
                        stats.ms.entries.joinToString { "${it.key.name.lowercase()} ${it.value}" })
            }

            override fun arrange(take: SoloTake, options: ArrangeOptions) = pipeline.arrange(take, options)
            override fun close() = models.forEach { it.close() }
        }
    }

    /** Basic Pitch on the whole mix and Beat This! small. */
    override fun openBandDraft(): OnPhone.BandDraft {
        val bp = BasicPitch(requireNotNull(asset(BASIC_PITCH_ASSET)) { "Basic Pitch is not bundled" })
        val bt = runCatching { BeatThis(requireNotNull(asset(BEAT_THIS_ASSET)) { "Beat This! is not bundled" }) }
            .onFailure { bp.close() }.getOrThrow()
        val pipeline = BandDraftPipeline(bp, bt, core)
        return object : OnPhone.BandDraft {
            override fun listen(audio: FloatArray, sampleRate: Int, title: String, onStage: (Int) -> Unit): Pair<BandTake, String> {
                val (take, stats) = pipeline.listen(audio, sampleRate, title) { onStage(it.ordinal) }
                return take to "%.1f s audio, Basic Pitch %d notes, beats %d, downbeats %d, stages %s ms"
                    .format(stats.audioSeconds, stats.basicPitchNotes, stats.beats, stats.downbeats,
                        stats.ms.entries.joinToString { "${it.key.name.lowercase()} ${it.value}" })
            }

            override fun arrange(take: BandTake, options: ArrangeOptions) = pipeline.arrange(take, options)
            override fun close() { bp.close(); bt.close() }
        }
    }

    private fun has(name: String): Boolean = runCatching { context.assets.open(name).close() }.isSuccess
    private fun asset(name: String): ByteArray? = runCatching { context.assets.open(name).use { it.readBytes() } }.getOrNull()

    companion object {
        const val MODEL_ASSET = "models/swift-f0-window.onnx"
        const val BASIC_PITCH_ASSET = "models/nmp-b1.onnx"
        const val BEAT_THIS_ASSET = "models/beat-this-small0.onnx"
        const val ORT_DISABLE_TELEMETRY = "ORT_DISABLE_TELEMETRY"

        /**
         * ONNX Runtime reports to Microsoft unless this is set when it starts (the first OrtEnvironment). The
         * manifest already removes the provider that sets up its uploader; this keeps the runtime's telemetry
         * off whatever else brings it in. Called before any content provider runs.
         */
        fun telemetryOff() {
            Os.setenv(ORT_DISABLE_TELEMETRY, "1", true)
        }
    }
}
