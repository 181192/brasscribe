package no.brasscribe.play

import android.os.Looper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import no.brasscribe.play.score.ScoreController
import no.brasscribe.play.screen.ScreenDevice
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The score is parsed off the main thread and applied on it; a load cancelled while it parses (the
 * screen left) leaves the controller unloaded, with no error and no render.
 */
@RunWith(AndroidJUnit4::class)
class ScoreLoadTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val scope = CoroutineScope(Dispatchers.Main)
    private lateinit var controller: ScoreController

    private fun xml(): ByteArray = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))

    private fun newController() {
        instrumentation.runOnMainSync { controller = ScoreController(instrumentation.targetContext, reducedMotion = true) }
    }

    @After
    fun tearDown() {
        instrumentation.runOnMainSync { controller.release() }
        scope.cancel()
    }

    @Test
    fun theScoreIsParsedOffTheMainThread() {
        newController()
        var pickedOn: Thread? = null
        val job = scope.launch { controller.load(xml()) { pickedOn = Thread.currentThread(); setOf(0) } }
        ScreenDevice.waitWithoutScreen(20_000) { job.isCompleted }
        val st = controller.state.value
        assertNull(st.error)
        assertTrue("loaded", st.loaded)
        assertTrue("parts", st.parts.isNotEmpty())
        val main = Looper.getMainLooper().thread
        assertNotNull(controller.parsedOn)
        assertTrue("parsed on ${controller.parsedOn?.name}, not the main thread", controller.parsedOn !== main)
        assertTrue("parts picked on ${pickedOn?.name}, not the main thread", pickedOn != null && pickedOn !== main)
    }

    @Test
    fun aCancelledLoadLeavesTheControllerUnloaded() {
        newController()
        lateinit var job: Job
        // Cancelled while the parse runs: the screen went away before the score was ready.
        job = scope.launch(start = kotlinx.coroutines.CoroutineStart.LAZY) { controller.load(xml()) { job.cancel(); setOf(0) } }
        job.start()
        ScreenDevice.waitWithoutScreen(20_000) { job.isCompleted }
        assertTrue(job.isCancelled)
        runCatching { ScreenDevice.waitWithoutScreen(500) { false } }
        val st = controller.state.value
        assertFalse("not loaded", st.loaded)
        assertNull("no error", st.error)
        assertEquals("nothing rendered", 0, controller.renders.value)
        assertTrue("no parts", st.parts.isEmpty())
    }
}
