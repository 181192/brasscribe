package no.brasscribe.play

import android.app.job.JobScheduler
import android.content.Context

/**
 * What Google's code scanner left on a phone that had an earlier version of the app: ML Kit's queue of
 * events waiting to be sent to Google (datatransport's database), ML Kit's id for this install (a UUID in
 * its preferences), and the scheduled job that would have sent the queue. The app no longer has the code
 * that sends them; this deletes them, so they are not kept or carried into a backup. Cheap when they are
 * not there, so it runs at every start.
 */
object GoogleLeftovers {
    const val EVENTS_DATABASE = "com.google.android.datatransport.events"
    const val MLKIT_PREFERENCES = "com.google.mlkit.internal"
    private const val TRANSPORT_PACKAGE = "com.google.android.datatransport."

    fun clear(context: Context) {
        if (context.getDatabasePath(EVENTS_DATABASE).exists()) context.deleteDatabase(EVENTS_DATABASE)
        context.deleteSharedPreferences(MLKIT_PREFERENCES)
        val jobs = context.getSystemService(JobScheduler::class.java) ?: return
        runCatching { jobs.allPendingJobs }.getOrDefault(emptyList())
            .filter { it.service.className.startsWith(TRANSPORT_PACKAGE) }
            .forEach { jobs.cancel(it.id) }
    }
}
