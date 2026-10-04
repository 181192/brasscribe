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
        // The job is handed to the service that follows it while the player is away.
        val started = generateSequence { shadowOf(app).nextStartedService }.firstOrNull { it.component?.className == ComputerJobService::class.java.name }
        assertNotNull("the service is started", started)
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }

        // Allowed: the screen says the app tells the player, and nothing is asked again.
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
        val asked = shadowOf(rule.activity).lastRequestedPermission
        send(slow = true)
        val told = shown()
        assertTrue(told, told.contains(if (tab) "Fretscribe tells you when the tab is ready." else "Brasscribe tells you when the score is ready."))
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

        // In front, the screen shows it: the service posts nothing (it asks AppInFront).
        assertTrue(AppInFront.now)
        // Away: "ready", on its own channel, with a tap that opens this job.
        assertTrue(JobNotices.ended(app, done, "Bass line"))
        val posted = nm.allNotifications.single()
        assertEquals(JobNotices.CHANNEL_DONE, posted.channelId)
        assertEquals(text(R.string.notif_ready), posted.extras.getCharSequence(android.app.Notification.EXTRA_TITLE).toString())
        assertEquals("Bass line", posted.extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString())
        assertNotNull(manager.getNotificationChannel(JobNotices.CHANNEL_DONE))
        val tap = shadowOf(posted.contentIntent).savedIntent
        assertEquals(JobNotices.ACTION_OPEN_JOB, tap.action)
        assertEquals(jobId, tap.getStringExtra(JobNotices.EXTRA_JOB))

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
    }

    @Test
    fun aJobIsFollowedThroughTheTimesTheComputerDoesNotAnswer() = runBlocking {
        fun job(status: JobStatus) = no.brasscribe.play.engine.Job("j", "tab", status, 0.0, emptyList())
        val answers = ArrayDeque(listOf<() -> no.brasscribe.play.engine.Job?>(
            { job(JobStatus.RUNNING) }, { throw java.io.IOException("no route") }, { null }, { job(JobStatus.SUCCEEDED) },
        ))
        assertEquals(JobStatus.SUCCEEDED, JobFollow.untilEnded({ answers.removeFirst()() }, pause = 0)?.status)
        // A computer that stays away is given up on after so many tries in a row.
        var asked = 0
        assertEquals(null, JobFollow.untilEnded({ asked++; throw java.io.IOException("gone") }, pause = 0, tries = 3))
        assertEquals(3, asked)
    }
}
