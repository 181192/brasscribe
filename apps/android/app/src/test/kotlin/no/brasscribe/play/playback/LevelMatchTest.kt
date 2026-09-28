package no.brasscribe.play.playback

import no.brasscribe.play.audio.LoudnessMeter
import no.brasscribe.play.audio.OutputStage
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.audio.PlaybackLevels
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin

/** "Listen to this bar" plays the recording at the band's loudness for the score, one gain for the whole recording. */
class LevelMatchTest {
    private fun tone(amplitude: Double, seconds: Double = 6.0, rate: Int = 22050) =
        PcmAudio(FloatArray((seconds * rate).toInt()) { (amplitude * sin(2 * PI * 1000 * it / rate)).toFloat() }, rate)

    @Test fun aLoudRecordingIsTurnedDownToTheTarget() {
        val loud = tone(0.5) // about −6 LUFS as dual mono
        val m = LevelMatch()
        val bar = m.slice(loud, 1.0, 3.0)
        assertEquals(PlaybackLevels.RECORDING_FALLBACK_LUFS, LoudnessMeter.dualMono(bar), 0.3)
    }

    /** With a score, the target is its band estimate, estimated once per score. */
    @Test fun theScoresTargetIsUsedAndEstimatedOnce() {
        val loud = tone(0.5)
        var estimates = 0
        val m = LevelMatch { xml -> estimates++; if (xml == null) PlaybackLevels.RECORDING_FALLBACK_LUFS else -12.0 }
        val score = "<score-partwise/>"
        assertEquals(-12.0, LoudnessMeter.dualMono(m.slice(loud, 1.0, 3.0, score)), 0.3)
        m.slice(loud, 3.0, 5.0, score)
        assertEquals(1, estimates)
        // another score, then none: each gets its own target
        val other = "<score-partwise></score-partwise>"
        m.slice(loud, 1.0, 3.0, other)
        assertEquals(PlaybackLevels.RECORDING_FALLBACK_LUFS, LoudnessMeter.dualMono(m.slice(loud, 1.0, 3.0, null)), 0.3)
        assertEquals(3, estimates)
    }

    @Test fun aQuietRecordingIsBoostedUpToTheCapAndLimited() {
        val quiet = tone(0.01) // about −40 LUFS: the boost stops at the cap
        val m = LevelMatch()
        assertEquals(PlaybackLevels.RECORDING_MAX_BOOST_DB, m.gainDb(quiet), 0.0)
        val hot = PcmAudio(FloatArray(22050) { if (it % 2 == 0) 0.5f else -0.5f }, 22050)
        assertTrue(m.slice(hot, 0.0, 1.0).peak() <= OutputStage.CEILING)
    }

    /** One gain for every bar: a soft bar stays softer than a loud one. */
    @Test fun everyBarGetsTheWholeRecordingsGain() {
        val rate = 22050
        val x = FloatArray(rate * 8) { i -> ((if (i < rate * 4) 0.4 else 0.04) * sin(2 * PI * 440 * i / rate)).toFloat() }
        val rec = PcmAudio(x, rate)
        val m = LevelMatch()
        val g = m.gainDb(rec)
        val loud = m.slice(rec, 0.5, 3.5)
        val soft = m.slice(rec, 4.5, 7.5)
        assertEquals(20.0, LoudnessMeter.dualMono(loud) - LoudnessMeter.dualMono(soft), 0.3)
        assertEquals(g, m.gainDb(rec), 0.0)
        assertEquals("the recording itself is never changed", x[100], rec.samples[100], 0f)
    }
}
