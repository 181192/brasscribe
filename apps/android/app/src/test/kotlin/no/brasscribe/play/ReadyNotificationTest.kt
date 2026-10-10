package no.brasscribe.play

import android.Manifest
import android.app.NotificationManager
import android.content.Intent
import android.net.Uri
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.engine.JobStatus
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Before
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.Shadows.shadowOf
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * A job on the computer goes on while the player is away from the app, and a notification says when it is done: the
 * transcribing screen says the player may leave, notifications are asked for once at the first such job, the job is
 * handed to the service that follows it, "ready" is posted only while the app is away, and its tap opens the score or
 * the tab. The service runs here as on a phone ([phoneRunsTheService]): it is started in the foreground once, is told
 * of the job in the process, and is in the foreground only while a recording is sent or a job is followed.
 */
@RunWith(AndroidJUnit4::class)
class ReadyNotificationTest : ScreenTest() {
    private val app get() = rule.activity.application
    private var pace = 0.0

    /** Every start of the service in the foreground, and the services so started. */
    private var starts = 0
    private val services = mutableListOf<ComputerJobService>()
    private val service get() = services.last()

    /**
     * The service as a phone runs it: a start in the foreground creates it and brings it there, and one asked for while
     * the app is away is refused (as from Android 12).
     */
    private fun phoneRunsTheService() {
        ComputerJobService.startInForeground = {
            starts++
            try {
                if (!AppInFront.now) throw IllegalStateException("startForegroundService() not allowed: the app is in the background")
                services += Robolectric.buildService(ComputerJobService::class.java).create().also { it.startCommand(0, starts) }.get()
            } catch (e: Throwable) {
                // (The app takes a refused start quietly; a test that did not expect one says what refused it.)
                refused += e
                throw e
            }
        }
    }

    /** The starts that were refused, or failed, each with what said so. */
    private val refused = mutableListOf<Throwable>()

    /** What the service holds and how it got there, for a failed check to say. */
    private fun told() = "held ${held()}, the app in front ${AppInFront.now}, $starts start(s), ${services.size} service(s) made, " +
        "refused: ${refused.map { it.stackTraceToString().take(4000) }}"

    private fun stopped(s: ComputerJobService = service) = shadowOf(s).isStoppedBySelf && shadowOf(s).isForegroundStopped
    private fun held() = ComputerJobService.held.value
    private fun leaveTheApp() = rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
    private fun comeBack() = rule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
    private fun ready() = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.filter { it.channelId == JobNotices.CHANNEL_DONE }

    @Before
    fun noServiceYet() = ComputerJobService.forget()

    @After
    fun clean() {
        if (!AppInFront.now) comeBack()
        rule.runOnUiThread { vm.cancelTranscription(); vm.keptRecordings.value.forEach(vm::deleteKept); vm.scores.value.forEach(vm::deleteEntry); vm.home() }
        rule.waitForIdle()
        ComputerJobService.forget()
        if (pace > 0) container.fixtureStageSeconds = pace
        container.fixtureSource = null
    }

    private val tab = Product.NAME == "Fretscribe"
    private val profile = if (tab) Profile.TAB else Profile.BRASS_BAND

    /** A recording opened and said what it is, with the computer chosen: Make the score is next. */
    private fun opened(slow: Boolean) {
        computer(if (tab) "bass-line" else "old-hundredth")
        if (pace == 0.0) pace = container.fixtureStageSeconds
        if (slow) container.fixtureStageSeconds = 60.0
        rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(recording())) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread { vm.chooseProfile(profile); vm.where.value = Where.COMPANION }
    }

    /**
     * Holds what the app does on Dispatchers.IO, where it reads the recording and sends it, until the latch that is
     * returned is counted down (or for a minute): every thread of the dispatcher is kept busy, so the sending waits
     * behind them.
     */
    private fun holdSending(): CountDownLatch {
        val go = CountDownLatch(1)
        // (More tasks than Dispatchers.IO runs at once: 64 threads, unless a system property sets more.)
        repeat(128) { CoroutineScope(Dispatchers.IO).launch { go.await(60, TimeUnit.SECONDS) } }
        return go
    }

    private fun send(slow: Boolean) {
        opened(slow)
        rule.runOnUiThread { vm.startTranscription() }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running && vm.transcribe.value.step != Step.UPLOAD }
        rule.waitForIdle()
    }

    @Test
    fun theFirstJobOnTheComputerAsksOnceAndSaysThePlayerMayLeave() {
        phoneRunsTheService()
        container.notificationsAsked = false
        shadowOf(app).denyPermissions(Manifest.permission.POST_NOTIFICATIONS)
        send(slow = true)
        // Asked at the first job on the computer, once; until it is allowed, the screen does not promise a notification.
        assertEquals(Manifest.permission.POST_NOTIFICATIONS, shadowOf(rule.activity).lastRequestedPermission?.requestedPermissions?.single())
        assertTrue(container.notificationsAsked)
        val quiet = shown()
        val leave = if (tab) "You can switch to another app: when the tab is ready, it is in Your songs" else "You can switch to another app: when the score is ready, it is in Your scores"
        assertTrue(quiet, quiet.contains(leave))
        assertFalse(quiet, quiet.contains("open until"))
        // The service was started in the foreground once, and has the job that was made.
        assertEquals(1, starts)
        assertEquals(1, held().jobs.size)
        assertFalse(held().sending)
        assertNotNull(shadowOf(service).lastForegroundNotification)
        assertFalse(stopped())
        // Stop: nothing left to follow, and the service is out of the foreground.
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        waitUntil { stopped() }
        assertTrue(held().jobs.isEmpty())

        // Allowed: the screen says the app tells the player, and nothing is asked again.
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        val asked = shadowOf(rule.activity).lastRequestedPermission
        send(slow = true)
        val told = shown()
        assertTrue(told, told.contains(if (tab) "Fretscribe tells you when the tab is ready, or soon after if the phone is asleep." else "Brasscribe tells you when the score is ready, or soon after if the phone is asleep."))
        assertTrue("asked once", shadowOf(rule.activity).lastRequestedPermission === asked)
    }

    @Test
    fun aJobMadeAfterThePlayerLeftIsFollowedWithNoSecondStartInTheForeground() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        phoneRunsTheService()
        opened(slow = false)
        // Make the score, and away at once: the recording is still being sent, and the job is made with the app away.
        // The sending is held until the player has left: the fixture computer answers at once, and whenever the main
        // thread got to run in between, as it does here on purpose, the job was made, or done, with the app in front.
        val send = holdSending()
        try {
            rule.runOnUiThread { vm.startTranscription() }
            settle()
            assertEquals(told(), 1, starts)
            assertTrue(told(), held().sending && held().jobs.isEmpty())
            leaveTheApp()
            assertTrue(told(), held().sending && held().jobs.isEmpty())
        } finally {
            send.countDown()
        }
        val first = service
        waitUntil(60_000) { ready().isNotEmpty() && stopped(first) }
        // One start in the foreground for the whole job (a second one, from the background, is refused); "ready" once,
        // for the job that was made; and the service out of the foreground with nothing held.
        assertEquals(1, starts)
        waitUntil(60_000) { vm.result.value?.jobId != null && !vm.transcribe.value.running }
        val jobId = vm.result.value!!.jobId!!
        val said = ready().single()
        assertEquals(text(R.string.notif_ready), said.extras.getCharSequence(android.app.Notification.EXTRA_TITLE).toString())
        assertEquals(jobId, shadowOf(said.contentIntent).savedIntent.getStringExtra(JobNotices.EXTRA_JOB))
        assertEquals(ComputerJobService.Held(), held().copy(title = ""))

        // The service by itself, as when the view model no longer follows (the app was closed, or the events were lost):
        // started in front while a recording is sent, told of the job once the player is away, it says "ready" and stops.
        comeBack()
        assertTrue(ready().isEmpty())
        ComputerJobService.start(app, "Riff")
        assertEquals(2, starts)
        leaveTheApp()
        ComputerJobService.follow(app, jobId, "Riff")
        assertEquals(2, starts)
        waitUntil(20_000) { ready().isNotEmpty() && stopped() }
        assertEquals("Riff", ready().single().extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString())

        // No service runs and the app is away: no start is asked for, and nothing is held as if one ran.
        ComputerJobService.follow(app, "another-job", "Riff")
        assertEquals(2, starts)
        assertEquals(ComputerJobService.Held(), held())
    }

    @Test
    fun aSecondJobDoesNotTakeTheFirstJobsPlace() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        phoneRunsTheService()
        // A job that is still running on the computer, followed by the service alone.
        send(slow = true)
        val running = held().jobs.keys.single()
        val finished = runBlocking {
            val engine = container.engine()!!
            engine.cancel(engine.createJob(no.brasscribe.play.engine.JobCreate("no-audio", profile.id)).id)
        }
        leaveTheApp()
        // Another is given to it and ends: said, and the first is still followed.
        ComputerJobService.start(app, "Second")
        ComputerJobService.follow(app, "gone-job", "Second")
        assertEquals(setOf(running, "gone-job"), held().jobs.keys)
        ComputerJobService.release("gone-job")
        ComputerJobService.follow(app, finished.id, "Third")
        waitUntil(20_000) { finished.id !in held().jobs }
        assertEquals(setOf(running), held().jobs.keys)
        assertFalse(stopped())
        assertEquals(1, starts)
        // The first job's end is the service's last: it stops.
        ComputerJobService.release(running)
        waitUntil { stopped() }
    }

    @Test
    fun theServiceIsLetGoWhenNoJobComesOfSending() {
        phoneRunsTheService()
        // Sending fails before anything is sent: out of the foreground again.
        val failed = runCatching { runBlocking { ComputerJobService.whileSending<Unit>(app, "Riff") { throw java.io.IOException("no file") } } }
        assertTrue(failed.exceptionOrNull() is java.io.IOException)
        assertEquals(1, starts)
        waitUntil { stopped() }
        assertEquals(ComputerJobService.Held(), held().copy(title = ""))

        // Cancelled while it sends (the app was closed): the same.
        val scope = CoroutineScope(Dispatchers.Main.immediate)
        val sending = scope.launch { ComputerJobService.whileSending<Unit>(app, "Riff") { awaitCancellation() } }
        assertEquals(2, starts)
        rule.waitForIdle()
        assertTrue(held().sending)
        assertFalse(stopped())
        sending.cancel()
        waitUntil { stopped() }
        assertFalse(held().sending)

        // Cancelled once the job is made and handed over: the service keeps following it (the job goes on on the computer).
        val following = scope.launch {
            val id = ComputerJobService.whileSending(app, "Riff") { "a-job" }
            ComputerJobService.follow(app, id, "Riff")
            awaitCancellation()
        }
        assertEquals(3, starts)
        following.cancel()
        rule.waitForIdle()
        assertEquals(setOf("a-job"), held().jobs.keys)
        assertFalse(stopped())
        ComputerJobService.release("a-job")
        waitUntil { stopped() }

        // The same from the screen: a recording that cannot be read is not sent, and nothing stays in the foreground.
        opened(slow = false)
        rule.runOnUiThread { vm.source.value!!.file!!.delete(); vm.startTranscription() }
        assertEquals(4, starts)
        waitUntil(20_000) { !vm.transcribe.value.running && stopped() }
        assertEquals(4, starts)
        assertTrue(held().jobs.isEmpty() && !held().sending)
    }

    @Test
    fun readyIsSaidOnlyWhileTheAppIsAwayAndItsTapOpensTheScore() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        send(slow = false)
        waitUntil(60_000) { !vm.transcribe.value.running && vm.result.value?.jobId != null }
        val jobId = vm.result.value!!.jobId!!
        val done = runBlocking { container.engine()!!.job(jobId) }
        assertEquals(JobStatus.SUCCEEDED, done.status)
        val manager = app.getSystemService(NotificationManager::class.java)
        val nm = shadowOf(manager)

        // In front, the screen shows it: the service posts nothing.
        assertTrue(AppInFront.now)
        assertFalse(JobNotices.afterFollowing(app, jobId, done, "Bass line", inFront = AppInFront.now))
        assertTrue(nm.allNotifications.isEmpty())
        // Away: "ready", on its own channel, with a tap that opens this job.
        assertTrue(JobNotices.afterFollowing(app, jobId, done, "Bass line", inFront = false))
        val posted = nm.allNotifications.single()
        assertEquals(JobNotices.CHANNEL_DONE, posted.channelId)
        assertEquals(text(R.string.notif_ready), posted.extras.getCharSequence(android.app.Notification.EXTRA_TITLE).toString())
        assertEquals("Bass line", posted.extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString())
        assertNotNull(manager.getNotificationChannel(JobNotices.CHANNEL_DONE))
        // A locked screen that hides private content shows what happened, not the song.
        assertEquals(androidx.core.app.NotificationCompat.VISIBILITY_PRIVATE, posted.visibility)
        assertEquals(null, posted.publicVersion.extras.getCharSequence(android.app.Notification.EXTRA_TEXT))
        assertEquals(text(R.string.notif_ready), posted.publicVersion.extras.getCharSequence(android.app.Notification.EXTRA_TITLE).toString())
        // One notice per job: another job's does not replace it.
        assertTrue(JobNotices.ended(app, done.copy(id = "another"), "Riff"))
        assertEquals(2, nm.allNotifications.size)
        val tap = shadowOf(posted.contentIntent).savedIntent
        assertEquals(JobNotices.ACTION_OPEN_JOB, tap.action)
        assertEquals(jobId, tap.getStringExtra(JobNotices.EXTRA_JOB))

        // The app came to the front: the notices about ended jobs are cleared.
        JobNotices.clearDone(app)
        assertTrue(nm.allNotifications.isEmpty())
        // The computer stayed away: the score will be in Your scores once it is back.
        assertTrue(JobNotices.afterFollowing(app, jobId, null, "Bass line", inFront = false))
        assertEquals(text(R.string.notif_away), nm.allNotifications.single().extras.getCharSequence(android.app.Notification.EXTRA_TITLE).toString())
        // A job the player stopped says nothing, and nothing is said without the permission.
        manager.cancelAll()
        assertFalse(JobNotices.ended(app, done.copy(status = JobStatus.CANCELLED), "Bass line"))
        shadowOf(app).denyPermissions(Manifest.permission.POST_NOTIFICATIONS)
        assertFalse(JobNotices.ended(app, done, "Bass line"))
        assertTrue(nm.allNotifications.isEmpty())

        // The tap, from Home: the score or the tab of that job.
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
        rule.runOnUiThread { rule.activity.handleIntent(Intent(tap)) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.SCORE && vm.result.value?.jobId == jobId }
        assertEquals(listOf(Screen.HOME, Screen.SCORE), vm.screen.value)

        // From outside (the activity is exported), only an id of the engine's shape is opened.
        assertFalse(JobNotices.isJobId("../v1/pair"))
        assertFalse(JobNotices.isJobId("a/b"))
        assertTrue(JobNotices.isJobId(jobId))
        // A job neither on the phone nor on a computer that can be reached: said, not a silent Home.
        rule.runOnUiThread { vm.home(); container.fixtureSource = null; vm.openFinishedJob("gone-job") }
        waitUntil(5_000) { vm.status.value?.text == text(R.string.ready_not_here) }
        assertEquals(listOf(Screen.HOME), vm.screen.value)
    }

    @Test
    fun aJobIsFollowedThroughTheTimesTheComputerDoesNotAnswerAndNotForever() = runBlocking {
        fun job(status: JobStatus) = no.brasscribe.play.engine.Job("j", "tab", status, 0.0, emptyList())
        // A clock the waits move: no real time passes.
        var now = 0L
        val pauses = mutableListOf<Long>()
        val sleep: suspend (Long) -> Unit = { pauses += it; now += it }
        val answers = ArrayDeque(listOf<() -> no.brasscribe.play.engine.Job?>(
            { job(JobStatus.RUNNING) }, { throw java.io.IOException("no route") }, { null }, { job(JobStatus.SUCCEEDED) },
        ))
        assertEquals(JobStatus.SUCCEEDED, JobFollow.untilEnded({ answers.removeFirst()() }, clock = { now }, sleep = sleep)?.status)
        assertEquals(listOf(5_000L, 5_000L, 5_000L), pauses)
        // A long job is asked about less often after five minutes.
        assertEquals(5_000L, JobFollow.pauseAt(4 * 60_000L))
        assertEquals(20_000L, JobFollow.pauseAt(6 * 60_000L))
        // A computer that stays away is given up on after ten minutes with no answer; a running job keeps it going.
        now = 0L
        assertEquals(null, JobFollow.untilEnded({ throw java.io.IOException("gone") }, clock = { now }, sleep = sleep))
        assertTrue("gave up at $now ms", now >= JobFollow.PATIENCE_MS && now < JobFollow.PATIENCE_MS + 20_000L)
    }
}
