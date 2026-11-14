package no.kalli.scribe.tab

import no.kalli.scribe.engine.Tab
import no.kalli.scribe.model.BrasscribeJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs

/**
 * The tab's own sound ([TabSoundScore], [TabSynth]) on the recorded fixture (apps/fixtures/bass-line): every note
 * sounds at the second the recording plays it, at any speed, with a bar counted in, the beats ticking, and over a
 * stretch again and again.
 */
class TabSoundTest {
    private val rate = 8_000
    private val root: File? = System.getProperty("scribe.sounds")?.let { File(it).parentFile }

    private fun fixture(): Triple<TabIndex, Tab, TabClock> {
        val dir = root?.resolve("apps/fixtures/bass-line")
        assumeTrue("apps/fixtures/bass-line is not in this checkout", dir?.isDirectory == true)
        val index = TabIndex.parse(File(dir, "tab.musicxml").readText())
        val tab = BrasscribeJson.decodeFromString(Tab.serializer(), File(dir, "tab.json").readText())
        return Triple(index, tab, TabClock.of(index, tab, null)!!)
    }

    /** Voices that sound nothing and write down when each note was struck and let go, in frames rendered. */
    private class Heard : TabVoices {
        var frame = 0
        val on = ArrayList<Pair<Int, Int>>()
        val off = ArrayList<Pair<Int, Int>>()
        var silenced = 0
        override fun on(pitch: Int) { on += frame to pitch }
        override fun off(pitch: Int) { off += frame to pitch }
        override fun silence() { silenced++ }
        override fun render(out: FloatArray, at: Int, frames: Int) {
            java.util.Arrays.fill(out, 2 * at, 2 * (at + frames), 0f)
            frame += frames
        }
    }

    /** Renders [seconds] of sound and gives it back, one channel. */
    private fun TabSynth.play(seconds: Double): FloatArray {
        val frames = (seconds * rate).toInt()
        val out = FloatArray(frames * 2)
        render(out, frames)
        return FloatArray(frames) { out[2 * it] }
    }

    /** The frames a click starts at: where the sound comes up from silence. */
    private fun clicks(sound: FloatArray): List<Int> {
        val starts = ArrayList<Int>()
        var quietSince = -rate
        for (i in sound.indices) {
            if (abs(sound[i]) > 0.05f) { if (i - quietSince > rate / 50) starts += i; quietSince = i }
        }
        return starts
    }

    @Test
    fun everyNoteOfThePageSoundsWhereTheRecordingPlaysIt() {
        val (index, tab, clock) = fixture()
        val score = TabSoundScore.of(index, clock)
        assertEquals(tab.notes.size, score.notes.size)
        // The page writes a note on the grid: within a sixteenth of where it was heard.
        val sixteenth = (tab.beatTimes[1] - tab.beatTimes[0]) / 4
        val heard = tab.notes.sortedBy { it.onsetS!! }
        score.notes.zip(heard).forEach { (written, was) ->
            assertEquals(was.pitch, written.pitch)
            assertEquals(was.onsetS!!, written.start, sixteenth + 1e-6)
            assertTrue(written.end > written.start)
        }
        // A beat for each of the two beats of every bar, the first of each marked.
        assertEquals(2 * clock.bars, score.beats.size)
        assertEquals(clock.secondsAt(3), score.beats[6].at, 1e-9)
        assertTrue(score.beats[6].first)
        assertFalse(score.beats[7].first)
    }

    @Test
    fun aBarOfSixEightIsCountedInTwo() {
        val dir = root?.resolve("apps/fixtures/tab-probes/six-eight")
        assumeTrue("apps/fixtures/tab-probes/six-eight is not in this checkout", dir?.isDirectory == true)
        val index = TabIndex.parse(File(dir, "tab.musicxml").readText())
        val clock = TabClock.of(index, BrasscribeJson.decodeFromString(Tab.serializer(), File(dir, "tab.json").readText()), null)!!
        val measure = clock.measure(0)
        assertEquals(6, measure.beats)
        // Two dotted quarters: the first and the fourth eighth, the first of the bar marked.
        assertEquals(2 to 3 * TabIndex.TICKS / 2, TabSoundScore.counted(measure))
        val beats = TabSoundScore.of(index, clock).beats
        assertEquals(2 * clock.bars, beats.size)
        assertEquals(clock.secondsAt(0, 3 * TabIndex.TICKS / 2), beats[1].at, 1e-9)
        assertEquals(listOf(true, false, true, false), beats.take(4).map { it.first })
        // Four-four and two-four are counted as written.
        assertEquals(4 to TabIndex.TICKS, TabSoundScore.counted(TabMeasure("1", 4 * TabIndex.TICKS, 4, TabIndex.TICKS)))
        assertEquals(3 to TabIndex.TICKS / 2, TabSoundScore.counted(TabMeasure("1", 3 * TabIndex.TICKS / 2, 3, TabIndex.TICKS / 2)))
    }

    @Test
    fun theSoundGoesOutWithRoomAndNeverClips() {
        // Half the level; a peak far over full scale bends under the ceiling, and keeps its sign.
        val samples = floatArrayOf(0.5f, -1.0f, 1.6f, 1.8f, -2.4f, 0f)
        TabSoundLevel.process(samples)
        assertEquals(0.25f, samples[0], 1e-6f)
        assertEquals(-0.5f, samples[1], 1e-6f)
        assertEquals(0.8f, samples[2], 1e-6f)
        assertTrue(samples[3] > 0.8f && samples[3] < TabSoundLevel.CEILING)
        assertTrue(samples[4] < -samples[3] && samples[4] > -TabSoundLevel.CEILING)
        assertEquals(0f, samples[5], 0f)
    }

    @Test
    fun theNotesAreStruckOnTimeAndTwiceAsLateAtHalfSpeed() {
        val (index, _, clock) = fixture()
        val score = TabSoundScore.of(index, clock)
        for (speed in listOf(1.0, 0.5)) {
            val voices = Heard()
            val synth = TabSynth(score, voices, rate)
            synth.speed = speed
            synth.play(score.end / speed + 1)
            assertEquals(score.notes.size, voices.on.size)
            voices.on.zip(score.notes).forEach { (struck, note) ->
                assertEquals(note.pitch, struck.second)
                assertEquals("at speed $speed", note.start / speed, struck.first.toDouble() / rate, 2.0 * TabSynth.BLOCK / rate)
            }
            assertEquals(score.notes.size, voices.off.size)
            assertTrue(synth.ended)
        }
    }

    @Test
    fun aBarIsCountedInBeforeTheSongMoves() {
        val (index, _, clock) = fixture()
        val score = TabSoundScore.of(index, clock)
        val voices = Heard()
        val synth = TabSynth(score, voices, rate)
        val from = clock.secondsAt(2)
        synth.seek(from)
        synth.countIn(2, 0.5)
        assertTrue(synth.countingIn)
        val sound = synth.play(0.99)
        // Two clicks half a second apart, and the song has not moved nor sounded a note.
        assertEquals(listOf(0.0, 0.5), clicks(sound).map { Math.round(it * 100.0 / rate) / 100.0 })
        assertEquals(from, synth.position, 1e-9)
        assertTrue(voices.on.isEmpty())
        synth.play(0.5)
        assertFalse(synth.countingIn)
        assertEquals(from + 0.49, synth.position, 0.02)
        assertTrue(voices.on.isNotEmpty())
    }

    @Test
    fun theMetronomeTicksOnEveryBeatAndTheNotesCanBeLeftOut() {
        val (index, _, clock) = fixture()
        val score = TabSoundScore.of(index, clock)
        val voices = Heard()
        val synth = TabSynth(score, voices, rate)
        synth.metronome = true
        synth.notes = false
        val sound = synth.play(score.end)
        val ticks = clicks(sound).map { it.toDouble() / rate }
        assertEquals(score.beats.size, ticks.size)
        ticks.zip(score.beats).forEach { (tick, beat) -> assertEquals(beat.at, tick, 0.02) }
        assertTrue(voices.on.isEmpty())
        // Without the metronome and the notes nothing sounds.
        val quiet = TabSynth(score, Heard(), rate).also { it.notes = false }
        assertTrue(quiet.play(score.end).all { it == 0f })
    }

    @Test
    fun aStretchTurnsBackToItsStartWithItsNotesStruckAgain() {
        val (index, _, clock) = fixture()
        val score = TabSoundScore.of(index, clock)
        val voices = Heard()
        val synth = TabSynth(score, voices, rate)
        val stretch = clock.span(RepeatBars(1, 2))
        val inIt = score.notes.count { it.start >= stretch.start && it.start < stretch.endInclusive }
        assertTrue(inIt > 0)
        synth.repeat = stretch
        synth.seek(stretch.start)
        synth.play((stretch.endInclusive - stretch.start) * 2.5)
        assertEquals(2, synth.turns)
        assertTrue("${synth.position} in $stretch", synth.position in stretch)
        assertFalse(synth.ended)
        assertTrue("${voices.on.size} of $inIt", voices.on.size in 2 * inIt..3 * inIt)
    }
}
