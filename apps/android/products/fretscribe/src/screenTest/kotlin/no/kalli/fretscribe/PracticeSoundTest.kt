package no.kalli.fretscribe

import android.content.Context
import android.view.KeyEvent
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.FixtureEngineApi
import no.kalli.scribe.engine.FixtureSource
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import no.kalli.scribe.tab.PracticeModel
import no.kalli.scribe.tab.PracticeSound
import no.kalli.scribe.tab.RecordingState
import no.kalli.scribe.tab.YourInstrument
import no.kalli.scribe.test.Slow
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.categories.Category
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

/** A recording of the fixture's tab ([tabJson]): a decaying tone on each note, at the second it was heard, as a WAV file's bytes. */
internal fun bassLineRecording(tabJson: String): ByteArray {
    val rate = 22_050
    val notes = org.json.JSONObject(tabJson).getJSONArray("notes")
    val length = ((0 until notes.length()).maxOf { notes.getJSONObject(it).getDouble("offset_s") } + 1.0)
    val samples = FloatArray((length * rate).toInt())
    for (i in 0 until notes.length()) {
        val n = notes.getJSONObject(i)
        val hz = 440.0 * Math.pow(2.0, (n.getInt("pitch") - 69) / 12.0)
        val from = (n.getDouble("onset_s") * rate).toInt().coerceAtLeast(0)
        val to = (n.getDouble("offset_s") * rate).toInt().coerceAtMost(samples.size)
        for (k in from until to) samples[k] += (Math.sin(2 * Math.PI * hz * (k - from) / rate) * Math.exp(-3.0 * (k - from) / rate) * 0.4).toFloat()
    }
    val data = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN).also { b -> samples.forEach { b.putShort((it.coerceIn(-1f, 1f) * 32_000).toInt().toShort()) } }.array()
    val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        .put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
        .putInt(rate).putInt(rate * 2).putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size).array()
    return header + data
}

/**
 * What is heard in practice, on a fixture computer (apps/fixtures/bass-line-marks): the tab's own notes in place of
 * the recording or over it, a bar counted in, and the metronome; chosen in Sound, and kept for the next song.
 */
@RunWith(AndroidJUnit4::class)
@Category(Slow::class)
class PracticeSoundTest : ScreenTest() {
    private val practice get() = ViewModelProvider(rule.activity)[PracticeModel::class.java]
    private val choices get() = rule.activity.getSharedPreferences(PracticeModel.CHOICES, Context.MODE_PRIVATE)

    override val shots = "fretscribe/practice-sound"

    private fun forget() {
        choices.edit().clear().commit()
        File(rule.activity.noBackupFilesDir, "recordings").deleteRecursively()
        File(rule.activity.noBackupFilesDir, "practice").deleteRecursively()
    }

    @Before
    fun setUp() {
        yourInstrumentStore(rule.activity).save(YourInstrument.DEFAULT)
        forget()
        container.fixtureSource = FixtureSource { name ->
            if (name == FixtureEngineApi.INPUT_FILE) sound() else ScreenDevice.fixture("bass-line-marks/$name")
        }
    }

    @After
    fun tearDown() {
        TabPlaces.forget()
        forget()
    }

    private fun sound(): ByteArray = bassLineRecording(checkNotNull(ScreenDevice.fixture("bass-line-marks/tab.json")).decodeToString())

    /** The tab of the fixture's song, with the player under it. */
    private fun practise() {
        val file = ScreenDevice.recording(rule.activity, "Bass line.wav", sound(), 22_050)
        openFromHome(file)
        waitForTag("fs-what-continue", 20_000)
        rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-instrument"))).performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        rule.onNodeWithTag("fs-show-tab").performClick()
        waitForTag("fs-tab", 30_000)
        waitUntil(30_000) { TabScreenProbe.view?.let { it.engraving.value != null && it.scale == TabScreenProbe.wanted } == true }
        waitForTag("fs-practice-sound", 20_000)
        waitUntil(20_000) { practice.recording == RecordingState.HERE }
        rule.waitForIdle()
    }

    private fun <T> onMain(read: () -> T): T {
        var value: T? = null
        rule.runOnUiThread { value = read() }
        @Suppress("UNCHECKED_CAST")
        return value as T
    }

    private fun now(): Double = onMain { practice.now() }
    private fun recordingAt(): Double = onMain { practice.recordingPlayer!!.position }
    private fun recordingPlays(): Boolean = onMain { practice.recordingPlayer!!.playing }
    private fun tabPlays(): Boolean = onMain { practice.tabSoundPlayer!!.asked }
    private fun tabAt(): Double = onMain { practice.tabSoundPlayer!!.position }

    private fun openSound() {
        rule.onNodeWithTag("fs-practice-sound").performClick()
        waitForTag("fs-sound-done", 5_000)
    }

    private fun closeSound() {
        rule.onNodeWithTag("fs-sound-done").performClick()
        rule.waitForIdle()
    }

    @Test
    fun theTabsOwnNotesPlayInPlaceOfTheRecording() {
        practise()
        rule.onNodeWithTag("fs-practice-sound").assertContentDescriptionEquals("Sound: The recording").assertHeightIsAtLeast(48.dp)
        openSound()
        rule.onNodeWithTag("fs-sound-recording").assertIsSelected()
        rule.onNodeWithTag("fs-sound-count-in").assertIsOff()
        rule.onNodeWithTag("fs-sound-metronome").assertIsOff()
        checkAccessibility()
        shot("sound")
        rule.onNodeWithTag("fs-sound-tab").performClick()
        rule.onNodeWithTag("fs-sound-tab").assertIsSelected()
        closeSound()
        rule.onNodeWithTag("fs-practice-sound").assertContentDescriptionEquals("Sound: The tab's notes")
        assertEquals("tab", choices.getString("sound", null))

        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(10_000) { practice.playing }
        waitUntil(10_000) { now() > 1.5 }
        assertTrue(tabPlays())
        assertFalse("the recording is not heard", recordingPlays())
        // The song is where the tab's sound is, and the player says the bar.
        assertEquals(tabAt(), now(), 0.3)
        // It goes on in the recording when that is chosen, from where the song is.
        val at = now()
        openSound()
        rule.onNodeWithTag("fs-sound-recording").performClick()
        closeSound()
        waitUntil(10_000) { recordingPlays() && !tabPlays() }
        assertTrue("the recording goes on from where the tab was (${recordingAt()} s after $at s)", recordingAt() >= at - 0.2 && recordingAt() < at + 3.0)
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(10_000) { !practice.playing }
        assertFalse(recordingPlays())
    }

    @Test
    fun aBarIsCountedInBeforeTheSongPlays() {
        practise()
        openSound()
        rule.onNodeWithTag("fs-sound-count-in").performClick()
        rule.onNodeWithTag("fs-sound-count-in").assertIsOn()
        closeSound()
        rule.onNodeWithTag("fs-practice-sound").assertContentDescriptionEquals("Sound: The recording, Count-in")
        val from = now()
        val asked = System.nanoTime()
        rule.onNodeWithTag("fs-practice-play").performClick()
        // The player is counting: the button is Pause, and neither the song nor the recording has moved.
        waitUntil(5_000) { practice.counting }
        assertTrue(practice.playing)
        assertFalse(recordingPlays())
        assertEquals(from, now(), 1e-6)
        waitUntil(10_000) { !practice.counting && recordingPlays() }
        val counted = (System.nanoTime() - asked) / 1e9
        // Two beats of 0.6 seconds, as the recording has them at its start: never sooner.
        assertTrue("the bar was counted in $counted s", counted > 1.0)
        waitUntil(10_000) { now() > from + 0.5 }
        // Only the count was the tab's: it is quiet beside the recording now.
        assertFalse(tabPlays())
        // Pause while it counts gives the count up.
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(10_000) { !practice.playing }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(5_000) { practice.counting }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(5_000) { !practice.playing && !practice.counting }
        assertFalse(recordingPlays())
        assertFalse(tabPlays())
    }

    @Test
    fun theMetronomeAndTheTabsNotesKeepWithTheRecording() {
        practise()
        openSound()
        rule.onNodeWithTag("fs-sound-metronome").performClick()
        rule.onNodeWithTag("fs-sound-metronome").assertIsOn()
        closeSound()
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(10_000) { practice.playing && recordingPlays() && tabPlays() }
        waitUntil(10_000) { now() > 1.5 }
        // (How closely the two keep together is PracticeFollowTest's: on the JVM the phone's player runs on the test's clock.)
        // A bar on: the tab's sound goes on beside the recording.
        rule.onNodeWithTag("fs-practice-next").performClick()
        waitUntil(5_000) { recordingPlays() && tabPlays() }
        // The metronome off: the tab's sound stops, the recording plays on.
        rule.runOnUiThread { practice.metronome(false) }
        waitUntil(5_000) { !tabPlays() }
        assertTrue(recordingPlays())
        // Both: the tab's notes over the recording.
        rule.runOnUiThread { practice.hear(PracticeSound.BOTH) }
        waitUntil(10_000) { recordingPlays() && tabPlays() }
        rule.onNodeWithTag("fs-practice-sound").assertContentDescriptionEquals("Sound: Both")
        // Pause stops both.
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(10_000) { !practice.playing && !recordingPlays() && !tabPlays() }
    }

    @Test
    fun cAndMTurnTheCountInAndTheMetronomeOnAndOff() {
        practise()
        assertNotNull(practice.tabSoundPlayer)
        ScreenDevice.key(rule, KeyEvent.KEYCODE_C)
        waitUntil(5_000) { practice.countIn }
        ScreenDevice.key(rule, KeyEvent.KEYCODE_M)
        waitUntil(5_000) { practice.metronome }
        rule.onNodeWithTag("fs-practice-sound").assertContentDescriptionEquals("Sound: The recording, Count-in, Metronome")
        ScreenDevice.key(rule, KeyEvent.KEYCODE_C)
        ScreenDevice.key(rule, KeyEvent.KEYCODE_M)
        waitUntil(5_000) { !practice.countIn && !practice.metronome }
        assertFalse(choices.getBoolean("count_in", true))
    }
}
