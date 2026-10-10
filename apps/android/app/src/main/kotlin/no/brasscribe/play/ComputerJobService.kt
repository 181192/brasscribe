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
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
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
 * once the job is made it is told so and asks the computer for it ([JobFollow]); it follows each job it is given until
 * that job ends, and stops when none is left. When a job ends while no screen of the app is in
 * front, it posts "ready" (or "couldn't be made"); a tap opens the score or the tab. When the computer stays away too
 * long it stops and says the score will be in Your scores once the computer is back. A job that ends while the app is
 * in front, or that the player stopped, posts nothing.
 */
class ComputerJobService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    /** The jobs it asks the computer about, each on its own. */
    private val follows = mutableMapOf<String, kotlinx.coroutines.Job>()
    private var watching: kotlinx.coroutines.Job? = null
    private var shownTitle: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        JobNotices.channels(this)
        val title = held.value.title
        // Always first: a service started with startForegroundService that never reaches the foreground ends the app.
        // A refusal (the type's time for the day is used up) leaves the job to the view model while the app is in front.
        val entered = runCatching {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, working(title), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        }.onFailure { android.util.Log.w("BrasscribePlay", "job service not in the foreground", it) }
        starting = false
        if (entered.isFailure) { held.value = Held(); stopSelf(); return START_NOT_STICKY }
        alive = true
        shownTitle = title
        // What it holds for is told in the process ([held]), never by another start, so a job made after the player left
        // reaches it too. Nothing held any more (stopped while it was starting): it stops now that it may.
        if (watching == null) watching = scope.launch { held.collect(::holdFor) }
        return START_NOT_STICKY
    }

    /** Follows the jobs of [now], stops following the others, and stops itself when there is nothing left to hold for. */
    private fun holdFor(now: Held) {
        if (!now.sending && now.jobs.isEmpty()) return done()
        follows.keys.filter { it !in now.jobs }.forEach { follows.remove(it)?.cancel() }
        val container = (application as PlayApplication).container
        for ((jobId, title) in now.jobs) {
            if (jobId in follows) continue
            val follow = scope.launch(start = CoroutineStart.LAZY) {
                val ended = JobFollow.untilEnded({ container.engine()?.job(jobId) })
                // Still its to say: the view model has not seen the end first, and the player has not stopped the job.
                if (jobId !in held.value.jobs) return@launch
                saidFor = jobId
                JobNotices.afterFollowing(this@ComputerJobService, jobId, ended, title, inFront = AppInFront.now)
                follows.remove(jobId)
                held.update { it.copy(jobs = it.jobs - jobId) }
            }
            follows[jobId] = follow
            follow.start()
        }
        if (now.title != shownTitle) {
            shownTitle = now.title
            // (Not shown without the permission; the service is in the foreground all the same.)
            runCatching { getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, working(now.title)) }
        }
    }

    private fun working(title: String): Notification = NotificationCompat.Builder(this, JobNotices.CHANNEL_WORKING)
        .setSmallIcon(R.drawable.ic_launcher_foreground)
        .setContentTitle(getString(R.string.notif_job_working))
        .setContentText(title.ifBlank { null })
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setContentIntent(JobNotices.openApp(this, null))
        .setCategory(NotificationCompat.CATEGORY_PROGRESS)
        .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
        .setPublicVersion(JobNotices.publicVersion(this, JobNotices.CHANNEL_WORKING, getString(R.string.notif_job_working)))
        .build()

    private fun done() {
        alive = false
        // What is told from here on is not this service's: one started after it reads [held] itself.
        watching = null
        follows.clear()
        scope.coroutineContext.cancelChildren()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /** The system's time for the type ran out: the jobs go on on the computer, and are listed there when they are done. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        held.value = Held()
        done()
    }

    override fun onDestroy() {
        // Ended by the system while it held something (not by itself): nothing is held any more.
        if (watching != null) { alive = false; held.value = Held() }
        scope.cancel()
        super.onDestroy()
    }

    /** What the service is in the foreground for: a recording being sent, and the jobs it follows (id to title). */
    internal data class Held(val sending: Boolean = false, val jobs: Map<String, String> = emptyMap(), val title: String = "")

    /**
     * The view model tells the service what to hold for through [held], in the process; only the first start is a start
     * in the foreground. (A second one, for a job made after the player left the app, is refused from Android 12, and
     * the service would stay in the foreground with nothing to follow.) The service is in the foreground exactly while
     * a recording is being sent or a job is followed. All of it is called on the main thread.
     */
    companion object {
        private const val NOTIFICATION_ID = 3

        internal val held = MutableStateFlow(Held())
        /** Asked to start, and not yet in the foreground: it stops itself there if nothing is held by then. */
        @Volatile private var starting = false
        /** In the foreground, reading [held]. */
        @Volatile private var alive = false
        /** The job whose end the service last spoke for (or kept quiet about, in front): the view model does not repeat it. */
        @Volatile private var saidFor: String? = null

        /** How the service is started in the foreground (a test puts its own here, to count the starts and run the service). */
        internal var startInForeground: (Context) -> Unit = ::startService

        private fun startService(context: Context) {
            context.startForegroundService(Intent(context, ComputerJobService::class.java))
        }

        /**
         * The recording of [title] is about to be sent: in the foreground from here, while the app is in front. A start
         * the system refuses changes nothing else. [follow] or [release] comes after it.
         */
        fun start(context: Context, title: String) {
            val runs = alive || starting
            held.update { it.copy(sending = true, title = title) }
            if (!runs) startIt(context, mayStart = true)
        }

        /**
         * The job [jobId] is made: the service follows it and says how it ended. A service that runs is told so here,
         * with no start in the foreground; when none runs (the phone refused it), one is tried only with the app in
         * front; with none, the view model alone follows the job, as long as the phone lets the app run.
         */
        fun follow(context: Context, jobId: String, title: String) {
            // (Read first: a service told of a job that has ended already says so and stops before this returns.)
            val runs = alive || starting
            held.update { it.copy(sending = false, jobs = it.jobs + (jobId to title), title = title) }
            if (!runs) startIt(context, mayStart = AppInFront.now)
        }

        /** No service is, or is about to be, in the foreground: one is started if [mayStart], and else nothing is held. */
        private fun startIt(context: Context, mayStart: Boolean) {
            if (mayStart) {
                starting = true
                runCatching { startInForeground(context.applicationContext) }
                    .onFailure { starting = false; android.util.Log.w("BrasscribePlay", "job service not started", it) }
            }
            // No service: nothing is held.
            if (!alive && !starting) held.value = Held()
        }

        /**
         * The view model has nothing more to send, and [jobId] (when the job was made) is not followed any more: the
         * player stopped it, the recording could not be sent, or its end was seen. The service stops when that leaves
         * it nothing to hold for; one that is still starting stops once it is in the foreground, as `DraftService` does.
         */
        fun release(jobId: String?) {
            held.update { it.copy(sending = false, jobs = if (jobId == null) it.jobs else it.jobs - jobId) }
        }

        /**
         * The view model saw [job] end, and the service is done with it. With the app in front the screen shows it.
         * Away, it is said here at once, unless the service has said it already.
         */
        fun ended(context: Context, job: Job, title: String) {
            release(job.id)
            if (saidFor != job.id) JobNotices.afterFollowing(context, job.id, job, title, inFront = AppInFront.now)
        }

        /**
         * Holds the service in the foreground while [send] sends the recording and makes the job. When no job comes of
         * it (it failed, or was cancelled, as when the app is closed while it sends), the service is let go.
         */
        suspend fun <T> whileSending(context: Context, title: String, send: suspend () -> T): T {
            try {
                start(context, title)
                return send()
            } catch (e: Throwable) {
                release(null)
                throw e
            }
        }

        /** Nothing held and no service, as in a new process (tests: the companion outlives a test's service). */
        internal fun forget() {
            held.value = Held()
            starting = false
            alive = false
            saidFor = null
            startInForeground = ::startService
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
