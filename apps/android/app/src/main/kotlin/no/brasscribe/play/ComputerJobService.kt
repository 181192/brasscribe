package no.brasscribe.play

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import no.brasscribe.play.engine.Job
import no.brasscribe.play.engine.JobStatus

/**
 * Follows a job on the computer while the player is away from the app, and says when it is done.
 *
 * The job runs on the computer whatever the phone does: closing the app, or the phone ending it, never stops it, and a
 * finished job is listed in Your scores (Your songs) from the computer. While the app is in front the view model
 * follows the job's events and shows its steps. This service is what keeps it going once the player leaves: it is in
 * the foreground with a quiet notification (type `dataSync`: it sends the recording and fetches the job's state), so
 * the phone neither freezes the app nor ends it. It starts before the recording is sent, so the upload goes on too, and
 * once the job is made it asks the computer for it ([JobFollow]). When the job ends while no screen of the app is in
 * front, it posts "ready" (or "couldn't be made"); a tap opens the score or the tab. When the computer stays away too
 * long it stops and says the score will be in Your scores once the computer is back. A job that ends while the app is
 * in front, or that the player stopped, posts nothing.
 */
class ComputerJobService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var following: String? = null
    private var follow: kotlinx.coroutines.Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val jobId = intent?.getStringExtra(EXTRA_JOB)
        val title = intent?.getStringExtra(EXTRA_TITLE).orEmpty()
        JobNotices.channels(this)
        val notification = NotificationCompat.Builder(this, JobNotices.CHANNEL_WORKING)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notif_job_working))
            .setContentText(title.ifBlank { null })
            .setOngoing(true)
            .setContentIntent(JobNotices.openApp(this, null))
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(JobNotices.publicVersion(this, JobNotices.CHANNEL_WORKING, getString(R.string.notif_job_working)))
            .build()
        // Always first: a service started with startForegroundService that never reaches the foreground ends the app.
        // A refusal (the type's time for the day is used up) leaves the job to the view model while the app is in front.
        val entered = runCatching {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        }.onFailure { android.util.Log.w("BrasscribePlay", "job service not in the foreground", it) }
        starting = false
        if (entered.isFailure) { stopWhenStarted = false; stopSelf(); return START_NOT_STICKY }
        // Stopped (the job ended in front, or the player stopped it) while the service was starting: it stops now that it may.
        if (stopWhenStarted) { stopWhenStarted = false; done(); return START_NOT_STICKY }
        // The recording is being sent: the service holds the app in the foreground until the job is made.
        if (jobId == null) return START_NOT_STICKY
        if (following == jobId) return START_REDELIVER_INTENT
        following = jobId
        val container = (application as PlayApplication).container
        follow?.cancel()
        follow = scope.launch {
            val ended = JobFollow.untilEnded({ container.engine()?.job(jobId) })
            if (following != jobId) return@launch
            JobNotices.afterFollowing(this@ComputerJobService, jobId, ended, title, inFront = AppInFront.now)
            done()
        }
        return START_REDELIVER_INTENT
    }

    private fun done() {
        following = null
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /** The system's time for the type ran out: the job goes on on the computer, and is listed there when it is done. */
    override fun onTimeout(startId: Int, fgsType: Int) = done()

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val EXTRA_JOB = "job"
        private const val EXTRA_TITLE = "title"
        private const val NOTIFICATION_ID = 3

        /** Asked to start, and not yet in the foreground: it may not be stopped until it is (that would end the app). */
        @Volatile private var starting = false
        /** Stopped while it was starting: it stops itself once it is in the foreground. */
        @Volatile private var stopWhenStarted = false

        /**
         * Started, while the app is in front, before the recording is sent ([jobId] null) and again once the job is made.
         * A start the system refuses changes nothing else.
         */
        fun start(context: Context, jobId: String?, title: String) {
            stopWhenStarted = false
            runCatching {
                val intent = Intent(context, ComputerJobService::class.java).putExtra(EXTRA_TITLE, title)
                if (jobId != null) intent.putExtra(EXTRA_JOB, jobId)
                context.startForegroundService(intent)
            }.onSuccess { starting = true }.onFailure { android.util.Log.w("BrasscribePlay", "job service not started", it) }
        }

        /**
         * Nothing more to send, follow or say (the player stopped the job, the recording could not be sent, or the job
         * ended in front). One that is still starting stops itself once it is in the foreground, as `DraftService` does.
         */
        fun stop(context: Context) {
            if (starting) stopWhenStarted = true
            else runCatching { context.stopService(Intent(context, ComputerJobService::class.java)) }
        }
    }
}

/** Following a job on the computer by asking for it, through the times the computer cannot be reached. */
object JobFollow {
    /**
     * Asks [ask] for the job until it has ended, and returns it as it ended. An answer that fails (the phone lost the
     * network, the computer is asleep) or that is null (not paired any more) is asked again; after [patience] ms with
     * no answer it gives up and returns null. It asks every [pauseAt] of the time it has been following: often at
     * first, then less often for a long job.
     */
    suspend fun untilEnded(
        ask: suspend () -> Job?,
        patience: Long = PATIENCE_MS,
        clock: () -> Long = { System.nanoTime() / 1_000_000 },
        sleep: suspend (Long) -> Unit = { delay(it) },
    ): Job? {
        val start = clock()
        var answered = start
        while (true) {
            val job = try {
                ask()
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                null
            }
            val now = clock()
            if (job != null && job.status.terminal) return job
            if (job != null) answered = now
            if (now - answered >= patience) return null
            sleep(pauseAt(now - start))
        }
    }

    /** How long to wait before asking again, [following] ms into the job: 5 s for five minutes, then 20 s. */
    fun pauseAt(following: Long): Long = if (following < 5 * 60_000L) 5_000L else 20_000L

    /** Ten minutes with no answer from the computer, and the service stops following. */
    const val PATIENCE_MS = 10 * 60_000L
}

/** Whether a screen of the app is in front: MainActivity counts itself in and out. */
object AppInFront {
    @Volatile private var started = 0
    val now: Boolean get() = started > 0
    fun started() { started++ }
    fun stopped() { started = maxOf(0, started - 1) }
}

/** The notifications about a job on the computer: their channels, and the ones that say how it went. */
object JobNotices {
    const val CHANNEL_WORKING = "computer-job"
    const val CHANNEL_DONE = "ready"
    const val ACTION_OPEN_JOB = "no.brasscribe.play.OPEN_JOB"
    const val EXTRA_JOB = "job"
    /** The tag of every notice about a job that ended: one per job, all cleared when the app comes to the front. */
    const val TAG_DONE = "job-done"

    /** A job id as the engine makes them: letters, digits, '.', '_' and '-' (anything else, from outside, is not opened). */
    private val JOB_ID = Regex("""[A-Za-z0-9._-]{1,128}""")
    fun isJobId(id: String?): Boolean = id != null && JOB_ID.matches(id) && !id.endsWith(".")

    fun channels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL_WORKING, context.getString(R.string.notif_job_channel), NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(CHANNEL_DONE, context.getString(R.string.notif_ready_channel), NotificationManager.IMPORTANCE_DEFAULT))
    }

    /** Whether the phone lets the app post notifications (asked for from Android 13). */
    fun allowed(context: Context): Boolean =
        (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
            NotificationManagerCompat.from(context).areNotificationsEnabled()

    /**
     * What the service says once it stops following [jobId]: nothing while the app is in front ([inFront]: the screen
     * shows it); else how [ended] ended, or, when the computer stayed away ([ended] null), that the score will be in
     * Your scores once the computer is back. Returns whether something was posted.
     */
    fun afterFollowing(context: Context, jobId: String, ended: Job?, title: String, inFront: Boolean): Boolean = when {
        inFront -> false
        ended == null -> post(context, jobId, context.getString(R.string.notif_away), title, open = null)
        else -> ended(context, ended, title)
    }

    /**
     * Says that [job] ended: ready, with a tap that opens it, or couldn't be made, with a tap that opens the app. Nothing
     * for a job the player stopped. Returns whether something was posted.
     */
    fun ended(context: Context, job: Job, title: String): Boolean {
        if (job.status == JobStatus.CANCELLED) return false
        val ready = job.status == JobStatus.SUCCEEDED
        return post(context, job.id, context.getString(if (ready) R.string.notif_ready else R.string.notif_failed),
            title.ifBlank { job.title.orEmpty() }, open = job.id.takeIf { ready })
    }

    private fun post(context: Context, jobId: String, heading: String, title: String, open: String?): Boolean {
        if (!allowed(context)) return false
        channels(context)
        val notification = NotificationCompat.Builder(context, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(heading)
            .setContentText(title.ifBlank { null })
            .setContentIntent(openApp(context, open))
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            // On a locked screen that hides private content, the notice without the song's name.
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(publicVersion(context, CHANNEL_DONE, heading))
            .build()
        // allowed() was asked above; a permission taken back in between throws, and nothing is posted.
        return runCatching { context.getSystemService(NotificationManager::class.java).notify(TAG_DONE, idOf(jobId), notification) }.isSuccess
    }

    /** One notice per job: a second job's "ready" does not replace the first's. */
    fun idOf(jobId: String): Int = jobId.hashCode()

    /** The notice as a locked screen that hides private content shows it: what happened, without the song. */
    fun publicVersion(context: Context, channel: String, heading: String): Notification =
        NotificationCompat.Builder(context, channel).setSmallIcon(R.drawable.ic_launcher_foreground).setContentTitle(heading).build()

    /** The app came to the front: the notices about ended jobs have said what they had to. */
    fun clearDone(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java) ?: return
        runCatching { nm.activeNotifications.filter { it.tag == TAG_DONE }.forEach { nm.cancel(TAG_DONE, it.id) } }
    }

    /** Opens the app as it is, or, with [jobId], on that job's score or tab. */
    fun openApp(context: Context, jobId: String?): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (jobId != null) intent.setAction(ACTION_OPEN_JOB).putExtra(EXTRA_JOB, jobId)
        else intent.setAction(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER).addFlags(Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        return PendingIntent.getActivity(context, jobId?.hashCode() ?: 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
