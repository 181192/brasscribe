package no.kalli.scribe.score.pitch

import ai.onnxruntime.OrtEnvironment

/**
 * The one way the models get ONNX Runtime's environment. It is made only with the runtime's telemetry switched off
 * ([TELEMETRY_OFF] set to 1, which the app does as it starts): with the variable set as the environment is made the
 * runtime never starts its uploader to Microsoft, and setting it later changes nothing. Without it this throws
 * instead of running a model with the uploader on.
 */
object OnnxRuntime {
    const val TELEMETRY_OFF = "ORT_DISABLE_TELEMETRY"

    val environment: OrtEnvironment by lazy {
        check(telemetryOff(System::getenv)) { "$TELEMETRY_OFF is not set: ONNX Runtime would send its telemetry" }
        OrtEnvironment.getEnvironment()
    }

    internal fun telemetryOff(getenv: (String) -> String?): Boolean = getenv(TELEMETRY_OFF) == "1"
}
