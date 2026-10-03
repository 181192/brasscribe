package no.brasscribe.play

import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import no.brasscribe.play.audio.AudioCapture
import no.brasscribe.play.audio.CaptureState
import no.brasscribe.play.audio.CapturedTake
import no.brasscribe.play.capture.CaptureController
import no.brasscribe.play.capture.CaptureKind
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Back on Record while a take is being recorded asks before it throws the take away: Keep recording leaves it
 * recording, Throw away deletes it and goes back. In both apps (the Record screen is shared). The microphone is a
 * device's, so the take here is a stand-in that says it is recording.
 */
@RunWith(AndroidJUnit4::class)
class RecordBackTest : ScreenTest() {
    private class Take(override val file: File) : AudioCapture {
        override val state = MutableStateFlow(CaptureState(recording = true, seconds = 12.0, level = 0.3f))
        @Volatile var discarded = false
        override fun start(scope: CoroutineScope) = true
        override suspend fun stop(): CapturedTake = throw UnsupportedOperationException("not stopped here")
        override suspend fun discard() { discarded = true; file.delete() }
    }

    private val take by lazy { Take(File(rule.activity.cacheDir, "takes/back-test.wav").apply { parentFile?.mkdirs(); writeBytes(ByteArray(64)) }) }

    @After
    fun clean() {
        if (CaptureController.activeFile() != null) CaptureController.discard(rule.activity)
        rule.runOnUiThread { vm.home() }
    }

    private fun asks(): Boolean = rule.onAllNodesWithText(text(R.string.record_discard_title)).fetchSemanticsNodes().isNotEmpty()

    private fun stillRecording() {
        rule.waitForIdle()
        assertEquals(Screen.RECORD, vm.screen.value.last())
        assertFalse("the take is not thrown away", take.discarded)
        assertTrue(take.file.isFile)
    }

    @Test
    fun backAsksBeforeItThrowsTheTakeAway() {
        rule.runOnUiThread {
            vm.home()
            CaptureController.attach(take, CaptureKind.MICROPHONE)
            vm.navigate(Screen.RECORD)
        }
        rule.waitForIdle()

        // The phone's Back asks; Keep recording goes on with the take.
        ScreenDevice.back(rule)
        assertTrue("Back asks first", asks())
        stillRecording()
        checkAccessibility()
        rule.onNodeWithText(text(R.string.record_discard_keep)).performClick()
        rule.waitForIdle()
        assertFalse(asks())
        stillRecording()

        // So does the top bar's button; Throw away deletes the take and goes back.
        rule.onNodeWithText(text(R.string.home)).performClick()
        assertTrue("the top bar's back asks first", asks())
        stillRecording()
        rule.onNodeWithText(text(R.string.record_discard_confirm)).performClick()
        waitUntil(5_000) { take.discarded && vm.screen.value.last() == Screen.HOME }
        assertFalse(take.file.exists())
    }

    @Test
    fun withNothingRecordingBackGoesStraightBack() {
        rule.runOnUiThread { vm.home(); vm.navigate(Screen.RECORD) }
        rule.waitForIdle()
        ScreenDevice.back(rule)
        assertFalse(asks())
        assertEquals(Screen.HOME, vm.screen.value.last())
    }
}
