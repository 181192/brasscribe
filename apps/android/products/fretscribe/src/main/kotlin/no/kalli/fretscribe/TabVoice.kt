package no.kalli.fretscribe

import alphaTab.core.ecmaScript.Float32Array
import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.io.ByteBuffer
import android.content.Context
import no.kalli.scribe.engine.FrettedInstrument
import no.kalli.scribe.tab.TabSoundPlayer
import no.kalli.scribe.tab.TabSoundSource
import no.kalli.scribe.tab.TabVoices

/**
 * The instrument a tab sounds on: one General MIDI program of the small SoundFont alphaTab brings with it
 * (the app carries the file already), played by alphaTab's synthesizer without its player ([SoundFontSynth]).
 * Only the program's own samples are read.
 */
internal class SoundFontVoices(soundFont: ByteArray, program: Int, sampleRate: Int) : TabVoices {
    private val synth = SoundFontSynth(ByteBuffer.fromBuffer(Uint8Array(soundFont.asUByteArray())), program.toDouble(), sampleRate.toDouble())
    private var into: FloatArray? = null
    private var wrapped: Float32Array? = null

    override fun on(pitch: Int) = synth.noteOn(pitch.toDouble(), VELOCITY)
    override fun off(pitch: Int) = synth.noteOff(pitch.toDouble())
    override fun silence() = synth.soundsOff()

    override fun render(out: FloatArray, at: Int, frames: Int) {
        if (into !== out) { into = out; wrapped = Float32Array(out) }
        java.util.Arrays.fill(out, 2 * at, 2 * (at + frames), 0f)
        synth.render(wrapped!!, (2 * at).toDouble(), frames.toDouble())
    }

    companion object {
        /** alphaTab's own SoundFont, in the app's assets. */
        const val ASSET = "sonivox.sf2"
        private const val VELOCITY = 0.8

        /** General MIDI: a bass played with the fingers, a nylon-string guitar (the nearest to a ukulele), a steel-string guitar. */
        const val BASS = 33
        const val NYLON = 24
        const val STEEL = 25

        /** The program [kind] sounds on; without a kind, a bass when the page goes below a guitar's lowest string. */
        fun programOf(kind: FrettedInstrument?, lowest: Int?): Int = when {
            kind?.isBass == true -> BASS
            kind == FrettedInstrument.UKULELE || kind == FrettedInstrument.UKULELE_BARITONE -> NYLON
            kind != null && kind != FrettedInstrument.UNKNOWN -> STEEL
            lowest != null && lowest < 40 -> BASS
            else -> STEEL
        }
    }
}

/** What the tab's own sound is made from for [sheet]: its notes, on the sound of the instrument it was written for. */
internal fun tabSoundOf(context: Context, sheet: TabSheet): TabSoundSource {
    val app = context.applicationContext
    val kind = sheet.tab?.preset?.let(FrettedInstrument::ofPreset)?.first
    val program = SoundFontVoices.programOf(kind, sheet.index.pieces.minOfOrNull { it.pitch })
    return TabSoundSource(sheet.index) {
        SoundFontVoices(app.assets.open(SoundFontVoices.ASSET).use { it.readBytes() }, program, TabSoundPlayer.RATE)
    }
}
