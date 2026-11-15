package no.kalli.scribe.score.pitch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * ONNX Runtime runs with its telemetry off: its environment is made in one place, which will not make it unless
 * ORT_DISABLE_TELEMETRY is 1 (the app sets it as it starts; the tests in build.gradle.kts, where an upload that
 * answers while the test JVM exits would also abort the JVM).
 */
class OrtTelemetryTest {
    @Test
    fun theTestJvmRunsOnnxRuntimeWithoutItsUploader() {
        assertEquals("1", System.getenv(OnnxRuntime.TELEMETRY_OFF))
    }

    @Test
    fun theEnvironmentIsOnlyMadeWithTelemetryOff() {
        assertTrue(OnnxRuntime.telemetryOff { if (it == "ORT_DISABLE_TELEMETRY") "1" else null })
        assertFalse(OnnxRuntime.telemetryOff { null })
        assertFalse(OnnxRuntime.telemetryOff { "0" })
    }

    /** Every model of the app gets the environment from [OnnxRuntime], never from ONNX Runtime directly. */
    @Test
    fun noModelMakesItsOwnEnvironment() {
        val android = generateSequence(File("").absoluteFile) { it.parentFile }.first { File(it, "settings.gradle.kts").isFile }
        val direct = android.walkTopDown()
            .onEnter { it.name != "build" && it.name != ".gradle" && it.name != "test" && it.name != "screenTest" }
            .filter { it.extension == "kt" && "/src/" in it.path && it.name != "OnnxRuntime.kt" }
            .filter { "OrtEnvironment.getEnvironment(" in it.readText() }
            .map { it.relativeTo(android).path }
            .toList()
        assertEquals("files that make ONNX Runtime's environment themselves", emptyList<String>(), direct)
    }
}
