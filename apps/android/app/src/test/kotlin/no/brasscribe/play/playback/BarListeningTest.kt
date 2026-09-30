package no.brasscribe.play.playback

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import no.brasscribe.play.audio.PcmAudio
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class BarListeningTest {
    private class FakeOutput : ClipOutput {
        val log = mutableListOf<String>()
        override fun play(clips: List<PcmAudio>): Long { log += "play ${clips.size}"; return 1_500 }
        override fun stop() { log += "stop" }
    }

    private val clip = PcmAudio(FloatArray(10), 16_000)
    private val both = BarListening.Clips(listOf(clip, clip), withRecording = true)

    @Test
    fun listenThenStopWithTheSameButton() = runTest {
        val out = FakeOutput()
        val events = mutableListOf<BarListening.Event>()
        val l = BarListening(backgroundScope, out) { events += it }
        l.toggle(12) { both }; runCurrent()
        assertEquals(12, l.playing.value)
        assertEquals(BarListening.Event.Started(12, true), events.last())
        l.toggle(12) { both }
        assertNull(l.playing.value)
        assertEquals(BarListening.Event.Stopped(12), events.last())
        assertEquals("stop", out.log.last())
    }

    @Test
    fun aClipThatCannotPlaySaysSoInsteadOfCrashing() = runTest {
        val broken = object : ClipOutput {
            var stops = 0
            override fun play(clips: List<PcmAudio>): Long = throw IllegalStateException("AudioTrack not initialized")
            override fun stop() { stops++ }
        }
        val events = mutableListOf<BarListening.Event>()
        val l = BarListening(backgroundScope, broken) { events += it }
        l.toggle(5) { both }; runCurrent()
        assertNull(l.playing.value)
        assertEquals(BarListening.Event.Unavailable, events.last())
        // A load that fails (the score's audio could not be fetched) is the same.
        l.toggle(6) { error("download failed") }; runCurrent()
        assertNull(l.playing.value)
        assertEquals(listOf(BarListening.Event.Unavailable, BarListening.Event.Unavailable), events)
    }

    @Test
    fun returnsToListenWhenTheBarEnds() = runTest {
        val out = FakeOutput()
        val events = mutableListOf<BarListening.Event>()
        val l = BarListening(backgroundScope, out) { events += it }
        l.toggle(3) { both }; runCurrent()
        advanceTimeBy(1_499)
        assertEquals(3, l.playing.value)
        advanceTimeBy(2)
        assertNull(l.playing.value)
        assertEquals(BarListening.Event.Ended(3), events.last())
    }

    @Test
    fun anotherBarReplacesTheOneThatPlays() = runTest {
        val out = FakeOutput()
        val l = BarListening(backgroundScope, out)
        l.toggle(3) { both }; runCurrent()
        l.toggle(4) { both }; runCurrent()
        assertEquals(4, l.playing.value)
        // The first bar's timer must not end the second one early.
        advanceTimeBy(1_000)
        assertEquals(4, l.playing.value)
    }

    @Test
    fun stoppingDuringTheDownloadMeansNothingPlaysLater() = runTest {
        val out = FakeOutput()
        val gate = CompletableDeferred<Unit>()
        val l = BarListening(backgroundScope, out)
        l.toggle(7) { gate.await(); both }; runCurrent()
        assertEquals("Stop shows at once", 7, l.playing.value)
        l.stop(announce = false)
        gate.complete(Unit); runCurrent()
        assertNull(l.playing.value)
        assertEquals(emptyList<String>(), out.log.filter { it.startsWith("play") })
    }

    @Test
    fun leavingIsQuietAndNothingToPlaySaysSo() = runTest {
        val out = FakeOutput()
        val events = mutableListOf<BarListening.Event>()
        val l = BarListening(backgroundScope, out) { events += it }
        l.toggle(1) { both }; runCurrent()
        l.stop(announce = false)
        assertEquals(listOf<BarListening.Event>(BarListening.Event.Started(1, true)), events)
        l.stop()
        assertEquals("nothing playing: nothing said", 1, events.size)
        l.toggle(2) { BarListening.Clips(emptyList(), false) }; runCurrent()
        assertEquals(BarListening.Event.Unavailable, events.last())
        assertNull(l.playing.value)
    }
}
