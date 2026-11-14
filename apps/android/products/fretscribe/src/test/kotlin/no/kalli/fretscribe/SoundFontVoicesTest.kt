package no.kalli.fretscribe

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.FrettedInstrument
import no.kalli.scribe.tab.SoundBeat
import no.kalli.scribe.tab.SoundNote
import no.kalli.scribe.tab.TabSoundLevel
import no.kalli.scribe.tab.TabSoundScore
import no.kalli.scribe.tab.TabSynth
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The instrument's sound ([SoundFontVoices]) from alphaTab's own SoundFont in the app: each program the app
 * plays is in the file, a note sounds at its pitch, stops when it is let go, and is silent at once when the
 * song jumps.
 */
@RunWith(AndroidJUnit4::class)
class SoundFontVoicesTest {
    private val rate = 44_100
    private val soundFont: ByteArray by lazy {
        ApplicationProvider.getApplicationContext<android.content.Context>().assets.open(SoundFontVoices.ASSET).use { it.readBytes() }
    }

    private fun SoundFontVoices.play(seconds: Double): FloatArray {
        val frames = (seconds * rate).toInt()
        val out = FloatArray(frames * 2) { 9f }
        var at = 0
        while (at < frames) { val n = minOf(64, frames - at); render(out, at, n); at += n }
        return FloatArray(frames) { (out[2 * it] + out[2 * it + 1]) / 2 }
    }

    private fun level(sound: FloatArray): Double = sqrt(sound.sumOf { it.toDouble() * it } / sound.size)

    /** How much of [sound] is at [hz]. */
    private fun at(sound: FloatArray, hz: Double): Double {
        var re = 0.0
        var im = 0.0
        sound.forEachIndexed { i, v -> re += v * cos(2 * PI * hz * i / rate); im += v * sin(2 * PI * hz * i / rate) }
        return sqrt(re * re + im * im) / sound.size
    }

    @Test
    fun everyProgramSoundsANoteAtItsPitchAndStopsIt() {
        for ((program, pitch) in listOf(SoundFontVoices.BASS to 40, SoundFontVoices.NYLON to 64, SoundFontVoices.STEEL to 57)) {
            val voices = SoundFontVoices(soundFont, program, rate)
            assertEquals("nothing sounds before a note", 0.0, level(voices.play(0.1)), 0.0)
            voices.on(pitch)
            val sound = voices.play(0.5)
            assertTrue("program $program sounds (${level(sound)})", level(sound) > 0.005)
            assertTrue("program $program does not clip", sound.all { abs(it) <= 1f })
            // The note's own pitch (or a harmonic of it) is stronger than the notes a semitone off.
            fun strength(p: Double) = (1..4).maxOf { at(sound, it * 440.0 * Math.pow(2.0, (p - 69) / 12.0)) }
            assertTrue("program $program plays the pitch", strength(pitch.toDouble()) > 2 * maxOf(strength(pitch - 1.0), strength(pitch + 1.0)))
            voices.off(pitch)
            voices.play(1.5)
            assertTrue("the note dies away once let go", level(voices.play(0.2)) < level(sound) / 10)
            voices.on(pitch)
            voices.play(0.2)
            voices.silence()
            voices.play(0.05)
            assertEquals("a jump is silent within a moment", 0.0, level(voices.play(0.1)), 1e-4)
        }
    }

    @Test
    fun aFullChordWithAClickOverItGoesOutUnderFullScale() {
        // Six notes struck at once on the loudest program, on the first beat of a bar with the metronome on.
        val score = TabSoundScore((0 until 6).map { SoundNote(0.0, 1.0, 40 + 5 * it) }, listOf(SoundBeat(0.0, true)), 1.0)
        for (program in listOf(SoundFontVoices.STEEL, SoundFontVoices.BASS)) {
            val synth = TabSynth(score, SoundFontVoices(soundFont, program, rate), rate)
            synth.metronome = true
            val out = FloatArray(rate)
            synth.render(out, rate / 2)
            val raw = out.maxOf { abs(it) }
            TabSoundLevel.process(out)
            val peak = out.maxOf { abs(it) }
            assertTrue("program $program sounds ($raw)", raw > 0.2)
            assertTrue("program $program peaks at $peak (raw $raw)", peak <= TabSoundLevel.CEILING)
            // The chord itself is below where the limiter starts to bend: it goes out as it is, 6 dB down.
            assertTrue("program $program: the chord has room ($raw)", raw * TabSoundLevel.GAIN <= TabSoundLevel.THRESHOLD)
        }
    }

    @Test
    fun theInstrumentChoosesTheSound() {
        assertEquals(SoundFontVoices.BASS, SoundFontVoices.programOf(FrettedInstrument.BASS_5, 64))
        assertEquals(SoundFontVoices.STEEL, SoundFontVoices.programOf(FrettedInstrument.GUITAR_6, 30))
        assertEquals(SoundFontVoices.NYLON, SoundFontVoices.programOf(FrettedInstrument.UKULELE, null))
        assertEquals(SoundFontVoices.STEEL, SoundFontVoices.programOf(FrettedInstrument.MANDOLIN, null))
        // A song whose data did not come: by its lowest note.
        assertEquals(SoundFontVoices.BASS, SoundFontVoices.programOf(null, 28))
        assertEquals(SoundFontVoices.STEEL, SoundFontVoices.programOf(null, 40))
    }
}
