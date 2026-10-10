package no.brasscribe.play

import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.Arranged
import no.brasscribe.play.model.BandTake
import no.brasscribe.play.model.SoloTake

/**
 * What the phone writes down by itself, without the computer: a solo, and a draft of a band. Each app has its
 * own (`Product.onPhone`): Brasscribe's listens with the models and ONNX Runtime it carries; Fretscribe has
 * [None], and carries neither, as its tabs are written on the computer.
 */
interface OnPhone {
    /** A solo can be written down here: SwiftF0 is in the app. */
    val hasPitchModel: Boolean

    /** A band draft can be made here: Basic Pitch and Beat This! small are in the app. */
    val hasBandModels: Boolean

    /** True when a band take of [seconds] fits in [freeBytes] of free memory (ActivityManager's availMem). */
    fun bandDraftFits(seconds: Double, freeBytes: Long): Boolean

    /** The models for a solo, open until closed ([hasPitchModel] must be true). */
    fun openSolo(): Solo

    /** The models for a band draft, open until closed ([hasBandModels] must be true). */
    fun openBandDraft(): BandDraft

    interface Solo : AutoCloseable {
        /**
         * Listens to the take. [onStage] is told each stage as it starts, by its place (0: the sound is made
         * ready, 1: pitch, 2: the notes are confirmed, 3: beats). With the take comes a line for the log.
         */
        fun listen(audio: FloatArray, sampleRate: Int, title: String, wav: ByteArray?, onStage: (Int) -> Unit): Pair<SoloTake, String>

        /** The take as a score, or null without the Rust core. */
        fun arrange(take: SoloTake, options: ArrangeOptions): Arranged?
    }

    interface BandDraft : AutoCloseable {
        /** Listens to the take. [onStage] is told each stage as it starts (0: the notes, 1: beats). With the take comes a line for the log. */
        fun listen(audio: FloatArray, sampleRate: Int, title: String, onStage: (Int) -> Unit): Pair<BandTake, String>

        /** The take as a score, or null without the Rust core. */
        fun arrange(take: BandTake, options: ArrangeOptions): Arranged?
    }

    /** Nothing is written down on the phone. */
    object None : OnPhone {
        override val hasPitchModel = false
        override val hasBandModels = false
        override fun bandDraftFits(seconds: Double, freeBytes: Long) = false
        override fun openSolo(): Solo = error("this app writes nothing down on the phone")
        override fun openBandDraft(): BandDraft = error("this app writes nothing down on the phone")
    }
}
