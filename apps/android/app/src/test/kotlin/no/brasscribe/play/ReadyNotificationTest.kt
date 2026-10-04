package no.brasscribe.play

import android.Manifest
import android.app.NotificationManager
import android.content.Intent
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.engine.JobStatus
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf

/**
 * A job on the computer goes on while the player is away from the app, and a notification says when it is done: the
 * transcribing screen says the player may leave, notifications are asked for once at the first such job, the job is
 * handed to the service that follows it, "ready" is posted only while the app is away, and its tap opens the score or
 * the tab. (The service in the foreground is a device's; on the JVM its start, its notice and the tap are checked.)
 */
@RunWith(AndroidJUnit4::class)
class ReadyNotificationTest : ScreenTest() {
    private val app get() = rule.activity.application
    private var pace = 0.0

    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.keptRecordings.value.forEach(vm::deleteKept); vm.scores.value.forEach(vm::deleteEntry); vm.home() }
        if (pace > 0) container.fixtureStageSeconds = pace
        container.fixtureSource = null
    }

    private val tab = Product.NAME == "Fretscribe"
    private val profile = if (tab) Profile.TAB else Profile.BRASS_BAND

    private fun send(slow: Boolean) {
        computer(if (tab) "bass-line" else "old-hundredth")
        if (pace == 0.0) pace = container.fixtureStageSeconds
        if (slow) container.fixtureStageSeconds = 60.0
        rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(recording())) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread { vm.chooseProfile(profile); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running && vm.transcribe.value.step != Step.UPLOAD }
        rule.waitForIdle()
    }

    @Test
    fun theFirstJobOnTheComputerAsksOnceAndSaysThePlayerMayLeave() {
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
        // The service is in the foreground before the recording is sent (the screen already says the player may leave),
        // and is handed the job once it is made.
        val starts = generateSequence { shadowOf(app).nextStartedService }.filter { it.component?.className == ComputerJobService::class.java.name }.toList()
        assertTrue("started before the upload, then with the job (${starts.map { it.getStringExtra("job") }})",
            starts.size >= 2 && starts.first().getStringExtra("job") == null && starts.last().getStringExtra("job") != null)
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }

        // Allowed: the screen says the app tells the player, and nothing is asked again.
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        val asked = shadowOf(rule.activity).lastRequestedPermission
        send(slow = true)
        val told = shown()
        assertTrue(told, told.contains(if (tab) "Fretscribe tells you when the tab is ready, or soon after if the phone is asleep." else "Brasscribe tells you when the score is ready, or soon after if the phone is asleep."))
        assertTrue("asked once", shadowOf(rule.activity).lastRequestedPermission === asked)
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
