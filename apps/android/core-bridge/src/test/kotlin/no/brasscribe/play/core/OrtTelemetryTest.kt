package no.brasscribe.play.core

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The tests run ONNX Runtime without its telemetry uploader (build.gradle.kts). With it, an upload that
 * answers while the test JVM exits aborts the JVM, now and then, after every test passed.
 */
class OrtTelemetryTest {
    @Test
    fun theTestJvmRunsOnnxRuntimeWithoutItsUploader() {
        assertEquals("1", System.getenv("ORT_DISABLE_TELEMETRY"))
    }
}
