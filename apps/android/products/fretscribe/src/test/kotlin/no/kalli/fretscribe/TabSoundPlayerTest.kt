package no.kalli.fretscribe

import android.os.Looper
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.tab.RecordingPlayer
import no.kalli.scribe.tab.SoundBeat
import no.kalli.scribe.tab.SoundNote
import no.kalli.scribe.tab.TabSoundPlayer
import no.kalli.scribe.tab.TabSoundScore
import no.kalli.scribe.tab.TabVoices
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf

/**
 * The tab's sound through the phone's output ([TabSoundPlayer]): it plays by the clock, says where it is, stops
 * where it is paused, counts a bar in, turns back over a stretch, and says when the tab has ended.
 */
@RunWith(AndroidJUnit4::class)
class TabSoundPlayerTest {
    private val score = TabSoundScore(
        notes = (0 until 8).map { SoundNote(it * 0.25, it * 0.25 + 0.2, 40 + it) },
        beats = (0 until 4).map { SoundBeat(it * 0.5, it % 2 == 0) },
        end = 2.0,
    )

    private class Quiet : TabVoices {
        @Volatile var struck = 0
        override fun on(pitch: Int) { struck++ }
        override fun off(pitch: Int) = Unit
        @Volatile var silenced = 0
        override fun silence() { silenced++ }
        override fun render(out: FloatArray, at: Int, frames: Int) = java.util.Arrays.fill(out, 2 * at, 2 * (at + frames), 0f)
    }

    private class Told : RecordingPlayer.Listener {
        val said = ArrayList<String>()
        override fun onPlaying(playing: Boolean) { said += if (playing) "playing" else "paused" }
        override fun onEnded() { said += "ended" }
        override fun onFailed() { said += "failed" }
    }

    /** Waits by the clock, with the main thread's messages run, until [done]. */
    private fun until(ms: Long = 10_000, what: String, done: () -> Boolean) {
        val by = System.nanoTime() + ms * 1_000_000
        while (!done()) {
            assertTrue("not within $ms ms: $what", System.nanoTime() < by)
            shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(5)
        }
    }

    private fun player(voices: TabVoices = Quiet(), told: Told = Told()) =
        TabSoundPlayer(ApplicationProvider.getApplicationContext(), score, { voices }, told)

    @Test
    fun itPlaysByTheClockAndStopsWhereItIsPaused() {
        val voices = Quiet()
        val told = Told()
        val p = player(voices, told)
        assertEquals(0.0, p.position, 0.0)
        val from = System.nanoTime()
        p.play()
        assertTrue(p.playing)
        until(what = "half a second in") { p.position >= 0.5 }
        // (It is never faster than the clock; how much slower a loaded machine makes it is not this test's to say.)
        val took = (System.nanoTime() - from) / 1e9
        assertTrue("half a second of the tab took $took s", took > 0.4)
        p.pause()
        val at = p.position
        assertTrue(at >= 0.5 && at < 2.0)
        Thread.sleep(200)
        assertEquals(at, p.position, 0.0)
        assertTrue(voices.struck >= 2)
        assertEquals(listOf("playing", "paused"), told.said)
        // At half speed it takes twice as long.
        p.speed = 0.5f
        p.seekTo(1.0)
        assertEquals(1.0, p.position, 0.0)
        val again = System.nanoTime()
        p.play()
        until(what = "a quarter second on") { p.position >= 1.25 }
        assertTrue((System.nanoTime() - again) / 1e9 > 0.4)
        p.release()
    }

    @Test
    fun itEndsWhereTheTabEnds() {
        val told = Told()
        val p = player(told = told)
        p.seekTo(1.5)
        p.play()
        until(what = "the end") { "ended" in told.said }
        assertFalse(p.playing)
        assertEquals(2.0, p.position, 0.0)
        // Played again from the end, it starts over.
        p.play()
        until(what = "playing again") { p.position in 0.1..1.0 }
        p.release()
    }

    @Test
    fun aBarIsCountedInBeforeItMoves() {
        val p = player()
        p.seekTo(0.5)
        p.countIn(2, 0.3)
        val from = System.nanoTime()
        p.play()
        assertTrue(p.countingIn)
        assertEquals(0.5, p.position, 0.0)
        until(what = "the count") { !p.countingIn }
        val took = (System.nanoTime() - from) / 1e9
        assertTrue("two beats of 0.3 s took $took s", took > 0.5)
        until(what = "moving") { p.position > 0.7 }
        p.release()
    }

    @Test
    fun movedWhileItPlaysItIsAtTheNewPlaceAtOnce() {
        val voices = Quiet()
        val p = player(voices)
        p.play()
        until(what = "playing") { p.position >= 0.3 }
        assertEquals(0, p.jumps)
        // What was rendered ahead from the old place is dropped: the song is heard from the new place, not a moment behind it.
        val moved = System.nanoTime()
        p.seekTo(1.0)
        assertEquals(1.0, p.position, 0.0)
        until(what = "on from the new place") { p.position >= 1.3 }
        val since = (System.nanoTime() - moved) / 1e9
        val at = p.position
        assertTrue("$at s of the tab after $since s by the clock", at - 1.0 <= since + 0.02 && at - 1.0 > since - 0.06)
        assertEquals(1, p.jumps)
        // A change of pace is no jump: nothing that rings is cut.
        p.trim = 1.03
        p.trim = 0.97
        until(what = "playing on") { p.position >= at + 0.1 }
        assertEquals(1, p.jumps)
        assertEquals(1, voices.silenced)
        // A jump out of a stretch being repeated is where it was put, not a turn further on.
        p.repeat = 0.5..1.0
        until(what = "a turn") { p.turns >= 1 }
        p.repeat = 1.2..1.8
        p.seekTo(0.25)
        until(what = "playing from before the stretch") { p.position in 0.3..0.6 }
        p.release()
    }

    @Test
    fun aStretchTurnsBackToItsStart() {
        val p = player()
        p.repeat = 0.5..1.0
        p.seekTo(0.5)
        p.play()
        until(what = "two turns") { p.turns >= 2 }
        assertTrue("${p.position}", p.position in 0.45..1.0)
        p.pause()
        p.release()
    }

    @Test
    fun itSaysWhenTheSoundIsMadeAndWhenItCannotBe() {
        val told = Told()
        var ready = 0
        val good = TabSoundPlayer(ApplicationProvider.getApplicationContext(), score, { Quiet() }, told) { ready++ }
        until(what = "ready") { ready == 1 }
        assertTrue(told.said.isEmpty())
        good.release()
        val p = TabSoundPlayer(ApplicationProvider.getApplicationContext(), score, { error("no SoundFont") }, told) { ready++ }
        until(what = "failed") { "failed" in told.said }
        assertEquals(1, ready)
        p.release()
    }
}
