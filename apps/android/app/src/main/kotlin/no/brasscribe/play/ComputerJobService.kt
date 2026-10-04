package no.brasscribe.play

import android.Manifest
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
 * follows the job's events and shows its steps. This service is what keeps following it once the player leaves: it is
 * in the foreground with a quiet notification (type `dataSync`: it fetches the job's state from the computer), so the
 * phone neither freezes the app nor ends it for the job, and it asks the computer for the job every few seconds. When
 * the job ends while no screen of the app is in front, it posts "ready" (or "couldn't be made"); a tap opens the score
 * or the tab. A job that ends while the app is in front, or that the player stopped, posts nothing.
 */
class ComputerJobService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var following: String? = null
    private var follow: kotlinx.coroutines.Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val jobId = intent?.getStringExtra(EXTRA_JOB) ?: run { stopSelf(); return START_NOT_STICKY }
        val title = intent.getStringExtra(EXTRA_TITLE).orEmpty()
        JobNotices.channels(this)
        val notification = NotificationCompat.Builder(this, JobNotices.CHANNEL_WORKING)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notif_job_working))
            .setContentText(title.ifBlank { null })
            .setOngoing(true)
            .setContentIntent(JobNotices.openApp(this, null))
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
        // Always first: a service started with startForegroundService that never reaches the foreground ends the app.
        // A refusal (the type's time for the day is used up) leaves the job to the view model while the app is in front.
        val entered = runCatching {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        }.onFailure { android.util.Log.w("BrasscribePlay", "job service not in the foreground", it) }
        if (entered.isFailure) { stopSelf(); return START_NOT_STICKY }
        if (following == jobId) return START_REDELIVER_INTENT
        following = jobId
        val container = (application as PlayApplication).container
        follow?.cancel()
        follow = scope.launch {
            val ended = JobFollow.untilEnded({ container.engine()?.job(jobId) })
            if (following != jobId) return@launch
            if (ended != null && !AppInFront.now) JobNotices.ended(this@ComputerJobService, ended, title)
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

        /** Started when a job is made on the computer, while the app is in front; a start the system refuses changes nothing else. */
        fun start(context: Context, jobId: String, title: String) {
            runCatching {
                context.startForegroundService(Intent(context, ComputerJobService::class.java).putExtra(EXTRA_JOB, jobId).putExtra(EXTRA_TITLE, title))
            }.onFailure { android.util.Log.w("BrasscribePlay", "job service not started", it) }
        }

        /** The player stopped the job: nothing more to follow or to say. */
        fun stop(context: Context) {
            runCatching { context.stopService(Intent(context, ComputerJobService::class.java)) }
        }
    }
}

/** Following a job on the computer by asking for it: through the times the computer cannot be reached. */
object JobFollow {
    /**
     * Asks [ask] for the job every [pause] ms until it has ended, and returns it as it ended. An answer that fails (the
     * phone lost the network, the computer is asleep) or that is null (not paired any more) is asked again, up to
     * [tries] times in a row; then it gives up and returns null.
     */
    suspend fun untilEnded(ask: suspend () -> Job?, pause: Long = PAUSE_MS, tries: Int = Int.MAX_VALUE): Job? {
        var unanswered = 0
        while (true) {
            val job = try {
                ask()
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                null
            }
            if (job != null && job.status.terminal) return job
            unanswered = if (job == null) unanswered + 1 else 0
            if (unanswered >= tries) return null
            delay(pause)
        }
    }

    const val PAUSE_MS = 5_000L
}

/** Whether a screen of the app is in front: MainActivity counts itself in and out. */
object AppInFront {
    @Volatile private var started = 0
    val now: Boolean get() = started > 0
    fun started() { started++ }
    fun stopped() { started = maxOf(0, started - 1) }
}

/** The notifications about a job on the computer: their channels, and the one that says it is done. */
object JobNotices {
    const val CHANNEL_WORKING = "computer-job"
    const val CHANNEL_DONE = "ready"
    const val ACTION_OPEN_JOB = "no.brasscribe.play.OPEN_JOB"
    const val EXTRA_JOB = "job"
    private const val DONE_ID = 4

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
     * Says that [job] ended: ready, with a tap that opens it, or couldn't be made, with a tap that opens the app. Nothing
     * for a job the player stopped. Returns whether something was posted.
     */
    fun ended(context: Context, job: Job, title: String): Boolean {
        if (job.status == JobStatus.CANCELLED || !allowed(context)) return false
        channels(context)
        val ready = job.status == JobStatus.SUCCEEDED
        val notification = NotificationCompat.Builder(context, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(if (ready) R.string.notif_ready else R.string.notif_failed))
            .setContentText(title.ifBlank { job.title }?.ifBlank { null })
            .setContentIntent(openApp(context, job.id.takeIf { ready }))
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .build()
        return runCatching { NotificationManagerCompat.from(context).notify(DONE_ID, notification) }.isSuccess
    }

    /** Opens the app as it is, or, with [jobId], on that job's score or tab. */
    fun openApp(context: Context, jobId: String?): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (jobId != null) intent.setAction(ACTION_OPEN_JOB).putExtra(EXTRA_JOB, jobId)
        else intent.setAction(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER).addFlags(Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        return PendingIntent.getActivity(context, jobId?.hashCode() ?: 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
