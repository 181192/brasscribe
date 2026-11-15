package no.kalli.scribe.play

import android.content.Context
import android.content.pm.PackageManager
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** ONNX Runtime's telemetry is off from the app's start, and its start-up hook is not in the app. */
@RunWith(AndroidJUnit4::class)
class OnnxRuntimeTelemetryTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test
    fun theUploadersOldQueueIsDeletedAndNothingElse() {
        // As the uploader of an earlier version left it in the cache, beside a file of the app's own.
        val queue = listOf("onnxruntime.db", "onnxruntime.db-wal", "onnxruntime.db-shm").map { File(context.cacheDir, it) }
        queue.forEach { it.writeText("events") }
        val own = File(context.cacheDir, "take.wav").apply { writeText("audio") }

        OnnxRuntimeTelemetry.clearQueue(context)

        assertTrue(queue.none { it.exists() })
        assertTrue(own.exists())
    }

    /** The app's start switches it off. (The variable itself is the phone's: the test JVM's environment does not see it.) */
    @Test
    fun theAppStartSwitchesItOff() {
        assertTrue(OnnxRuntimeTelemetry.switchedOff)
    }

    /** `ai.onnxruntime.TelemetryInitializer`, from the ONNX Runtime library's manifest, is removed in the app's. */
    @Test
    fun onnxRuntimesStartUpHookIsNotInTheApp() {
        val providers = context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_PROVIDERS).providers.orEmpty()
        assertTrue("the test sees the app's providers", providers.isNotEmpty())
        assertFalse(providers.map { it.name }.toString(), providers.any { it.name.startsWith("ai.onnxruntime.") })
    }
}
