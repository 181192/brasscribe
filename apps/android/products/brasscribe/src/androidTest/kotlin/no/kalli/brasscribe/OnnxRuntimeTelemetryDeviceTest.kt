package no.kalli.brasscribe

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.kalli.scribe.score.pitch.SwiftF0
import no.kalli.scribe.test.DeviceOnly
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * A model runs on the phone with ONNX Runtime's telemetry off. The runtime's Java telemetry client, which its
 * start-up hook makes as the app starts (reading the phone's id, maker and model), is never made, and its uploader
 * never starts: making the environment and a session writes nothing to the app's storage (with the uploader on, its
 * queue of events would appear in the app's cache).
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class OnnxRuntimeTelemetryDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    /** The app's files, but for its preferences, which the app's start may still be writing. */
    private fun files(): Set<String> =
        File(context.applicationInfo.dataDir).walkTopDown().filter { it.isFile && it.parentFile?.name != "shared_prefs" }
            .map { it.path }.toSet()

    @Test
    fun aModelRunsWithTheRuntimesTelemetryOff() {
        val model = context.assets.open("models/swift-f0-window.onnx").use { it.readBytes() }
        Thread.sleep(2_000)
        val before = files()

        SwiftF0(model).close()
        Thread.sleep(3_000)

        val client = Class.forName("ai.onnxruntime.TelemetryInitializer").getDeclaredField("client")
            .apply { isAccessible = true }.get(null)
        assertNull("the runtime's telemetry client", client)
        assertEquals("files the runtime wrote", emptySet<String>(), files() - before)
        assertEquals("the app's start set the variable, as the runtime sees it", "1", System.getenv("ORT_DISABLE_TELEMETRY"))
    }
}
