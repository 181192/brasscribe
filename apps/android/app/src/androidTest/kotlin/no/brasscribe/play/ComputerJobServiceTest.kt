package no.brasscribe.play

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.NotificationManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.test.DeviceOnly
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The service that follows a job on the computer, under the phone's own rules for the background: started in the
 * foreground while the app is in front, it is told of a job made after the player has left, says "ready" when that job
 * ends, and leaves the foreground. (The phone refuses a second start in the foreground from the background, so the
 * job must reach the service that already runs.)
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class ComputerJobServiceTest : ScreenTest() {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private fun notices(channel: String) = context.getSystemService(NotificationManager::class.java).activeNotifications
        .filter { it.notification.channelId == channel }

    // The test ends with the app away: there is no screen of the app to check.
    override val checksTheLastScreen = false

    // Without the permission the system keeps the notifications out of sight, and out of the list read here.
    @Before
    fun allowNotifications() {
        if (android.os.Build.VERSION.SDK_INT >= 33)
            instrumentation.uiAutomation.grantRuntimePermission(context.packageName, android.Manifest.permission.POST_NOTIFICATIONS)
        instrumentation.runOnMainSync { ComputerJobService.forget() }
    }

    @After
    fun letGo() {
        instrumentation.runOnMainSync { ComputerJobService.held.value.jobs.keys.forEach { ComputerJobService.release(it) }; ComputerJobService.release(null) }
        context.getSystemService(NotificationManager::class.java).cancelAll()
    }

    private fun waitFor(ms: Long, what: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (what()) return true; Thread.sleep(100) }
        return what()
    }

    @Test
    fun aJobMadeAfterThePlayerLeftIsFollowedSaidReadyAndNothingStaysInTheForeground() {
        val tab = Product.NAME == "Fretscribe"
        computer(if (tab) "bass-line" else "old-hundredth")
        // In front, as Make the score does before the recording is sent.
        instrumentation.runOnMainSync { ComputerJobService.start(context, "Evening take") }
        // (The system may hold a foreground service's notification back for its first ten seconds.)
        assertTrue("in the foreground while the recording is sent", waitFor(15_000) { notices(JobNotices.CHANNEL_WORKING).isNotEmpty() })

        // The player leaves, and stays away long enough to be in the background for the system too.
        instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
        assertTrue("the app is away", waitFor(10_000) { !AppInFront.now })
        Thread.sleep(8_000)

        // The job is made now, and the running service is told of it.
        val engine = container.engine()!!
        val job = runBlocking { engine.createJob(JobCreate("no-audio", (if (tab) Profile.TAB else Profile.BRASS_BAND).id)) }
        instrumentation.runOnMainSync { ComputerJobService.follow(context, job.id, "Evening take") }
        assertEquals(setOf(job.id), ComputerJobService.held.value.jobs.keys)
        assertTrue("still in the foreground, for the job", notices(JobNotices.CHANNEL_WORKING).isNotEmpty())
        assertTrue("nothing said yet", notices(JobNotices.CHANNEL_DONE).isEmpty())

        // The job runs to its end on the computer; nothing in the app follows it but the service.
        runBlocking { engine.events(job.id).collect { } }
        assertTrue("\"ready\" is said", waitFor(20_000) { notices(JobNotices.CHANNEL_DONE).isNotEmpty() })
        val ready = notices(JobNotices.CHANNEL_DONE).single().notification
        assertEquals(context.getString(R.string.notif_ready), ready.extras.getCharSequence(Notification.EXTRA_TITLE).toString())
        assertNotNull(ready.contentIntent)
        assertTrue("out of the foreground once the job has ended", waitFor(10_000) { notices(JobNotices.CHANNEL_WORKING).isEmpty() })
        assertTrue(ComputerJobService.held.value.jobs.isEmpty())
    }

    /** No job comes of sending (it failed, or the app was closed meanwhile): the service leaves the foreground. */
    @Test
    fun sendingThatMakesNoJobLeavesTheForeground() {
        instrumentation.runOnMainSync { ComputerJobService.start(context, "Evening take") }
        assertTrue(waitFor(15_000) { notices(JobNotices.CHANNEL_WORKING).isNotEmpty() })
        instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
        assertTrue(waitFor(10_000) { !AppInFront.now })
        val failed = runCatching { runBlocking { ComputerJobService.whileSending<Unit>(context, "Evening take") { throw java.io.IOException("no route") } } }
        assertTrue(failed.isFailure)
        assertTrue("out of the foreground", waitFor(10_000) { notices(JobNotices.CHANNEL_WORKING).isEmpty() })
    }
}
