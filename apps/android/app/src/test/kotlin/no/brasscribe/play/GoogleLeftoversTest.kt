package no.brasscribe.play

import android.app.job.JobInfo
import android.app.job.JobScheduler
import android.content.ComponentName
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** A phone updated from a version with Google's code scanner keeps none of what ML Kit left there. */
@RunWith(AndroidJUnit4::class)
class GoogleLeftoversTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val jobs = context.getSystemService(JobScheduler::class.java)

    private fun job(id: Int, service: String) =
        JobInfo.Builder(id, ComponentName(context.packageName, service)).setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).build()

    @Test
    fun theEventQueueMlKitsIdAndTheUploadJobAreDeletedAndNothingElse() {
        // As ML Kit left them: its events waiting for the upload, its install id, and the upload's job.
        SQLiteDatabase.openOrCreateDatabase(context.getDatabasePath(GoogleLeftovers.EVENTS_DATABASE).apply { parentFile?.mkdirs() }, null)
            .use { it.execSQL("CREATE TABLE events (_id INTEGER PRIMARY KEY)") }
        context.getSharedPreferences(GoogleLeftovers.MLKIT_PREFERENCES, Context.MODE_PRIVATE).edit()
            .putString("ml_sdk_instance_id", "3f0e0c4e-0000-4000-8000-000000000000").commit()
        jobs.schedule(job(93201526, "com.google.android.datatransport.runtime.scheduling.jobscheduling.JobInfoSchedulerService"))
        // The app's own.
        context.getSharedPreferences("engine", Context.MODE_PRIVATE).edit().putString("url", "http://10.0.2.2:8765").commit()
        jobs.schedule(job(7, "no.brasscribe.play.SomeJob"))

        GoogleLeftovers.clear(context)

        assertFalse(context.getDatabasePath(GoogleLeftovers.EVENTS_DATABASE).exists())
        assertFalse(context.databaseList().any { it.startsWith(GoogleLeftovers.EVENTS_DATABASE) })
        assertTrue(context.getSharedPreferences(GoogleLeftovers.MLKIT_PREFERENCES, Context.MODE_PRIVATE).all.isEmpty())
        assertEquals(listOf(7), jobs.allPendingJobs.map { it.id })
        assertEquals("http://10.0.2.2:8765", context.getSharedPreferences("engine", Context.MODE_PRIVATE).getString("url", null))

        // Nothing there: nothing happens.
        GoogleLeftovers.clear(context)
        assertEquals(listOf(7), jobs.allPendingJobs.map { it.id })
    }
}
