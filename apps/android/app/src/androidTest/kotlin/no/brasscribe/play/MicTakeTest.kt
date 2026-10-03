package no.brasscribe.play

import android.Manifest
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.audio.MicRecorder
import no.brasscribe.play.audio.WavFile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import no.brasscribe.play.test.DeviceOnly

/** The microphone recorder writes the take to its WAV as it records; stopping hands over the file and the samples. */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class MicTakeTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Before
    fun grantMicrophone() {
        InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.RECORD_AUDIO)
    }

    @Test
    fun aTakeIsWrittenAsItIsRecorded() = runBlocking<Unit> {
        val file = File(context.cacheDir, "mic-take-test.wav").apply { delete() }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val rec = MicRecorder(file)
        assumeTrue("no microphone input on this device", rec.start(scope))
        Thread.sleep(1_500)
        val during = file.length()
        val seconds = rec.state.value.seconds
        val take = rec.stop()
        scope.cancel()
        assertTrue("the WAV grows while recording ($during bytes after ${"%.2f".format(seconds)} s)", during > 44 + 16_384)
        assertTrue("a second or more recorded (${take.seconds} s)", take.seconds >= 1.0)
        assertTrue(rec.state.value.fitsPhone)
        assertFalse(rec.state.value.recording)
        assertNotNull("a short take keeps its samples", take.audio)
        assertEquals(take.samples.toInt(), take.audio!!.samples.size)
        val wav = WavFile.read(take.file)
        assertEquals(take.sampleRate, wav.sampleRate)
        assertEquals(take.samples.toInt(), wav.samples.size)
        file.delete()
    }

    @Test
    fun aDiscardedTakeLeavesNoFile() = runBlocking<Unit> {
        val file = File(context.cacheDir, "mic-take-discard.wav").apply { delete() }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val rec = MicRecorder(file)
        assumeTrue("no microphone input on this device", rec.start(scope))
        Thread.sleep(300)
        rec.discard()
        scope.cancel()
        assertFalse(file.exists())
    }
}
