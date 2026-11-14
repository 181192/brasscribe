package no.kalli.fretscribe

import android.app.Application
import android.os.Looper
import androidx.lifecycle.SavedStateHandle
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Tab
import no.kalli.scribe.model.BrasscribeJson
import no.kalli.scribe.tab.PracticeModel
import no.kalli.scribe.tab.PracticeSpeed
import no.kalli.scribe.tab.RecordingPlayer
import no.kalli.scribe.tab.RecordingState
import no.kalli.scribe.tab.RepeatBars
import no.kalli.scribe.tab.SavedRepeats
import no.kalli.scribe.tab.SpeedTrainer
import no.kalli.scribe.tab.TabClock
import no.kalli.scribe.tab.TabIndex
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf
import java.io.File

/**
 * The speed trainer and the saved repeats ([PracticeModel]), with a recording that plays nothing and says when the
 * bars being repeated have been played through.
 */
@RunWith(AndroidJUnit4::class)
class PracticeTrainerTest {
    private val app = ApplicationProvider.getApplicationContext<Application>()
    private val fixtures = File(System.getProperty("scribe.sounds")!!).parentFile!!.resolve("apps/fixtures/bass-line")
    private val index = TabIndex.parse(fixtures.resolve("tab.musicxml").readText())
    private val clock = TabClock.of(index, BrasscribeJson.decodeFromString(Tab.serializer(), fixtures.resolve("tab.json").readText()), null)!!

    private class Silent(val listener: RecordingPlayer.Listener) : RecordingPlayer {
        override var playing = false
        override val asked: Boolean get() = playing
        override var position = 0.0
        override val duration = 60.0
        override var speed = 1f
        override var repeat: ClosedFloatingPointRange<Double>? = null
        override fun play() { playing = true; listener.onPlaying(true) }
        override fun pause() { playing = false; listener.onPlaying(false) }
        override fun seekTo(seconds: Double) { position = seconds }
        override fun release() = Unit
    }

    private val made = ArrayList<Silent>()
    private val recording = File(app.cacheDir, "take.wav")

    @Before
    fun setUp() {
        recording.writeBytes(ByteArray(64) { 1 })
        File(app.noBackupFilesDir, "repeats").deleteRecursively()
        PracticeModel.recordingPlayers = { _, listener -> Silent(listener).also { made += it } }
    }

    @After
    fun tearDown() {
        PracticeModel.recordingPlayers = null
    }

    private fun until(what: String, done: () -> Boolean) {
        val by = System.nanoTime() + 15_000_000_000L
        while (!done()) {
            assertTrue("not in time: $what", System.nanoTime() < by)
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(5))
            Thread.sleep(5)
        }
    }

    private fun opened(job: String? = "job-1", songs: Set<String>? = null): PracticeModel {
        val m = PracticeModel(app, SavedStateHandle())
        m.open("song-$job", job, clock, recording, songs)
        until("the recording") { m.recording == RecordingState.HERE }
        return m
    }

    @Test
    fun theBarsStartSlowAndGoFasterAfterEveryFewTimesThrough() {
        val m = opened()
        val player = made.last()
        // The trainer is for bars being repeated.
        m.train(SpeedTrainer.DEFAULT)
        assertNull(m.trainer)
        m.repeat(RepeatBars(1, 2))
        m.train(SpeedTrainer(from = 60, to = 70, step = 5, every = 2))
        assertEquals(60, m.speed)
        assertEquals(0.6f, player.speed, 1e-6f)
        m.toggle()
        // Once through: still 60 %. Twice: 65 %. Twice more: 70 %, and the trainer has done its work.
        player.listener.onTurned()
        assertEquals(60, m.speed)
        player.listener.onTurned()
        assertEquals(65, m.speed)
        assertEquals(0.65f, player.speed, 1e-6f)
        player.listener.onTurned(); player.listener.onTurned()
        assertEquals(70, m.speed)
        assertNull(m.trainer)
        player.listener.onTurned(); player.listener.onTurned()
        assertEquals(70, m.speed)

        // A speed the player sets, other bars, or no repeat ends it.
        m.train(SpeedTrainer(60, 100))
        m.faster()
        assertNull(m.trainer)
        assertEquals(65, m.speed)
        m.train(SpeedTrainer(60, 100))
        m.repeat(RepeatBars(3, 4))
        assertNull(m.trainer)
        m.train(SpeedTrainer(60, 100))
        m.repeat(null)
        assertNull(m.trainer)
        player.listener.onTurned(); player.listener.onTurned()
        assertEquals(60, m.speed)
        // One that would not go faster is none; one past the fastest speed stops there.
        m.repeat(RepeatBars(1, 2))
        m.train(SpeedTrainer(100, 100))
        assertNull(m.trainer)
        m.train(SpeedTrainer(145, 200, step = 10, every = 1))
        player.listener.onTurned()
        assertEquals(PracticeSpeed.MAX, m.speed)
        m.leave()
    }

    @Test
    fun savedRepeatsAreKeptForTheSongAndGoWithIt() {
        val m = opened()
        assertTrue(m.savedRepeats.isEmpty())
        m.saveRepeat(RepeatBars(4, 7))
        m.saveRepeat(RepeatBars(1, 2))
        m.saveRepeat(RepeatBars(4, 7))
        // In the order of their bars, each once; one that is not in the tab is not kept.
        m.saveRepeat(RepeatBars(3, 400))
        assertEquals(listOf(RepeatBars(1, 2), RepeatBars(4, 7)), m.savedRepeats)
        until("written") { SavedRepeats.of(app).read("job-1").size == 2 }
        m.leave()

        // After the app was closed they are read from the phone; another song has none.
        val again = opened()
        until("read") { again.savedRepeats.size == 2 }
        assertEquals(listOf(RepeatBars(1, 2), RepeatBars(4, 7)), again.savedRepeats)
        again.forgetRepeat(RepeatBars(1, 2))
        assertEquals(listOf(RepeatBars(4, 7)), again.savedRepeats)
        until("written") { SavedRepeats.of(app).read("job-1").size == 1 }
        again.leave()
        val other = opened("job-2")
        assertTrue(other.savedRepeats.isEmpty())
        other.saveRepeat(RepeatBars(0, 0))
        until("written") { SavedRepeats.of(app).read("job-2").size == 1 }
        other.leave()

        // A song that is no longer in Your songs takes its repeats with it.
        val kept = opened("job-2", songs = setOf("job-2"))
        until("pruned") { SavedRepeats.of(app).read("job-1").isEmpty() }
        assertEquals(listOf(RepeatBars(0, 0)), SavedRepeats.of(app).read("job-2"))
        kept.forgetRepeat(RepeatBars(0, 0))
        until("the file goes with its last repeat") { File(app.noBackupFilesDir, "repeats").listFiles().orEmpty().isEmpty() }
        kept.leave()
    }
}
