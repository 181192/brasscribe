package no.kalli.fretscribe

import android.app.Application
import android.os.Looper
import androidx.lifecycle.SavedStateHandle
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Tab
import no.kalli.scribe.model.BrasscribeJson
import no.kalli.scribe.tab.PracticeModel
import no.kalli.scribe.tab.PracticeSound
import no.kalli.scribe.tab.RecordingPlayer
import no.kalli.scribe.tab.RecordingState
import no.kalli.scribe.tab.TabClock
import no.kalli.scribe.tab.TabIndex
import no.kalli.scribe.tab.TabSoundSource
import no.kalli.scribe.tab.TabSoundState
import no.kalli.scribe.tab.TabVoices
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf
import java.io.File
import kotlin.math.abs

/**
 * The tab's own sound beside the recording ([PracticeModel]), with a recording that plays by the clock on the wall
 * (the phone's own player runs on the test's clock on the JVM) and the real sound thread: the tab's sound settles
 * beside the recording without being moved, also when the recording runs a little fast; it is moved once when the
 * recording is; and the sound says when it is being made and when it cannot be.
 */
@RunWith(AndroidJUnit4::class)
class PracticeFollowTest {
    private val app = ApplicationProvider.getApplicationContext<Application>()
    private val fixtures = File(System.getProperty("scribe.sounds")!!).parentFile!!.resolve("apps/fixtures/bass-line")
    private val index = TabIndex.parse(fixtures.resolve("tab.musicxml").readText())
    private val clock = TabClock.of(index, BrasscribeJson.decodeFromString(Tab.serializer(), fixtures.resolve("tab.json").readText()), null)!!

    /** A recording that plays by the clock on the wall, [pace] times as fast as it should. */
    private class ByTheClock(private val listener: RecordingPlayer.Listener, private val pace: Double) : RecordingPlayer {
        private var from = 0.0
        private var since = -1L
        override val playing: Boolean get() = since >= 0
        override val asked: Boolean get() = since >= 0
        override val position: Double get() = if (since < 0) from else from + (System.nanoTime() - since) / 1e9 * speed * pace
        override val duration = 60.0
        // (The time gone by so far was at the speed it had.)
        override var speed = 1f
            set(value) { if (since >= 0) { from = position; since = System.nanoTime() }; field = value }
        override var repeat: ClosedFloatingPointRange<Double>? = null
        override fun play() { if (since < 0) { since = System.nanoTime(); listener.onPlaying(true) } }
        override fun pause() { if (since >= 0) { from = position; since = -1; listener.onPlaying(false) } }
        override fun seekTo(seconds: Double) { from = seconds; if (since >= 0) since = System.nanoTime() }
        override fun release() = Unit
    }

    private class Counting : TabVoices {
        @Volatile var silenced = 0
        @Volatile var struck = 0
        override fun on(pitch: Int) { struck++ }
        override fun off(pitch: Int) = Unit
        override fun silence() { silenced++ }
        override fun render(out: FloatArray, at: Int, frames: Int) = java.util.Arrays.fill(out, 2 * at, 2 * (at + frames), 0f)
    }

    private var pace = 1.0
    private val recording = File(app.cacheDir, "take.wav")

    @Before
    fun setUp() {
        recording.writeBytes(ByteArray(64) { 1 })
        app.getSharedPreferences(PracticeModel.CHOICES, 0).edit().clear().commit()
        PracticeModel.recordingPlayers = { _, listener -> ByTheClock(listener, pace) }
    }

    @After
    fun tearDown() {
        PracticeModel.recordingPlayers = null
    }

    /** Waits by the clock, with the main thread's messages run, until [done]. */
    private fun until(ms: Long = 15_000, what: String, done: () -> Boolean) {
        val by = System.nanoTime() + ms * 1_000_000
        while (!done()) {
            assertTrue("not within $ms ms: $what", System.nanoTime() < by)
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(5))
            Thread.sleep(5)
        }
    }

    private fun opened(voices: () -> TabVoices, inHand: File? = recording): PracticeModel {
        val m = PracticeModel(app, SavedStateHandle())
        m.open("song", null, clock, inHand, tab = TabSoundSource(index, voices))
        return m
    }

    private fun settles(pace: Double) {
        this.pace = pace
        val voices = Counting()
        val m = opened({ voices })
        until(what = "the recording and the tab's sound") { m.recording == RecordingState.HERE && m.tabSound }
        m.hear(PracticeSound.BOTH)
        m.toggle()
        val tab = m.tabSoundPlayer!!
        val rec = m.recordingPlayer!!
        until(what = "both playing") { m.playing && tab.asked && rec.position > 1.0 }
        until(what = "together") { abs(tab.position - rec.position) < 0.03 }
        // Two seconds beside the recording: never moved (a move cuts every ringing note), and never far from it.
        val moves = tab.jumps
        val silenced = voices.silenced
        var apart = 0.0
        val by = System.nanoTime() + 2_000_000_000L
        until(what = "two seconds") { apart = maxOf(apart, abs(tab.position - rec.position)); System.nanoTime() >= by }
        assertEquals("at pace $pace the tab's sound was moved", moves, tab.jumps)
        assertEquals("at pace $pace ringing notes were cut", silenced, voices.silenced)
        assertTrue("at pace $pace the tab's sound was $apart s from the recording", apart < 0.06)
        assertTrue(voices.struck > 3)
        // Slower, while it plays: the two slow down together, with no move.
        m.slower(); m.slower()
        val slowed = System.nanoTime() + 1_000_000_000L
        apart = 0.0
        until(what = "a second slower") { apart = maxOf(apart, abs(tab.position - rec.position)); System.nanoTime() >= slowed }
        assertEquals("at pace $pace a change of speed moved the tab's sound", moves, tab.jumps)
        assertTrue("at pace $pace, slower, the tab's sound was $apart s from the recording", apart < 0.08)
        // The recording moved by the player: the tab's sound goes with it, in one move.
        m.step(2)
        until(what = "moved") { tab.jumps > moves }
        until(what = "together after the move") { rec.position > clock.secondsAt(2) && abs(tab.position - rec.position) < 0.05 }
        assertTrue("moved ${tab.jumps - moves} times for one move of the song", tab.jumps - moves in 1..2)
        m.toggle()
        assertFalse(tab.asked || rec.asked)
        m.leave()
    }

    @Test
    fun besideTheRecordingTheTabsSoundSettlesAndIsNotMoved() = settles(1.0)

    @Test
    fun aRecordingThatRunsALittleFastIsKeptUpWithWithoutAMove() = settles(1.01)

    @Test
    fun theSoundSaysWhenItIsBeingMadeAndWhenItCannotBe() {
        val m = opened({ Thread.sleep(300); Counting() }, inHand = null)
        assertEquals(TabSoundState.LOADING, m.tabSoundState)
        assertFalse(m.tabSound || m.canPlay)
        until(what = "made") { m.tabSoundState == TabSoundState.READY }
        until(what = "the recording looked for") { m.recording == RecordingState.NOT_HERE }
        assertTrue(m.canPlay)
        assertEquals(PracticeSound.TAB, m.hears)
        m.leave()
        assertEquals(TabSoundState.NONE, m.tabSoundState)

        val failing = opened({ error("no SoundFont") })
        until(what = "failed") { failing.tabSoundState == TabSoundState.FAILED }
        until(what = "the recording") { failing.recording == RecordingState.HERE }
        // The recording still plays; the tab's notes, the count-in and the metronome are not to be had.
        assertFalse(failing.tabSound)
        assertEquals(PracticeSound.RECORDING, failing.hears)
        failing.countIn(true)
        failing.toggle()
        assertTrue(failing.playing && !failing.counting)
        failing.leave()
    }
}
