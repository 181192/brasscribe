package no.brasscribe.play

import android.content.pm.PackageManager
import android.system.Os
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.PI
import kotlin.math.sin
import no.brasscribe.play.test.DeviceOnly

/**
 * ONNX Runtime runs on the phone without reporting to Microsoft: its telemetry provider is not in the
 * installed app, and the runtime starts with ORT_DISABLE_TELEMETRY set. The pitch model then runs on a
 * synthesized tone, so the runtime is started as a transcription on the phone starts it. The instrumentation
 * argument `ortWaitSeconds` keeps the process alive afterwards, for a network capture around the test.
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class OrtTelemetryDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun onnxRuntimeRunsWithoutItsTelemetry() {
        // The model runs first, so that a build with the telemetry left in still starts the runtime (and
        // its uploader) before the checks below fail.
        val sampleRate = 16_000
        // A brass-like A4: six harmonics, as in the pitch module's synthetic melody.
        val tone = FloatArray(sampleRate * 2) { i ->
            (0.25 * (1..6).sumOf { h -> sin(2 * PI * 440.0 * h * i / sampleRate) / h }).toFloat()
        }
        val track = (context.applicationContext as PlayApplication).container.openPitchModel().use { it.detect(tone) }
        val voiced = (0 until track.size).filter { track.confidence[it] > 0.5 }.map { track.pitchHz[it] }
        assertTrue("SwiftF0 hears the 440 Hz tone: ${voiced.size} voiced frames", voiced.size > track.size / 2)
        assertEquals(440.0, voiced.sorted()[voiced.size / 2], 5.0)

        val wait = InstrumentationRegistry.getArguments().getString("ortWaitSeconds")?.toLongOrNull() ?: 0
        if (wait > 0) Thread.sleep(wait * 1000)

        val providers = context.packageManager
            .getPackageInfo(context.packageName, PackageManager.PackageInfoFlags.of(PackageManager.GET_PROVIDERS.toLong()))
            .providers.orEmpty().map { it.name }
        assertTrue("installed providers: $providers", providers.none { it.startsWith("ai.onnxruntime") })
        assertEquals("1", Os.getenv(PlayApplication.ORT_DISABLE_TELEMETRY))
    }
}
