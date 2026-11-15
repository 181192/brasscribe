package no.kalli.scribe.play

import android.content.Context
import android.system.Os
import java.io.File

/**
 * ONNX Runtime, which runs the models the app listens with, sends events about its use to Microsoft unless it is
 * told not to. Its Android build starts its uploader when the runtime's environment is first made, unless
 * [VARIABLE] is set then; the call its Java API has for this (`OrtEnvironment.setTelemetry(false)`) comes after
 * the environment, and the uploader has already started and queued its first events by then. So the variable is
 * set here, as the app starts and before any model runs; the score's models refuse to start ONNX Runtime without
 * it (`OnnxRuntime.environment`). The runtime's own start-up hook, which makes its telemetry client as the app starts
 * (reading the phone's id, maker and model for it), is taken out of the app's manifest.
 *
 * An earlier version of the app may have left the uploader's queue of events in the app's cache: deleted here, as
 * [GoogleLeftovers] deletes Google's.
 */
object OnnxRuntimeTelemetry {
    const val VARIABLE = "ORT_DISABLE_TELEMETRY"

    /** The uploader's queue (SQLite, with its journal files), in the folder its Java side gives it: the app's cache. */
    private val QUEUE = listOf("onnxruntime.db", "onnxruntime.db-wal", "onnxruntime.db-shm", "onnxruntime.db-journal")

    /** Whether [switchOff] has run in this process (the tests' view of the app's start). */
    @Volatile var switchedOff = false
        private set

    fun switchOff(context: Context) {
        Os.setenv(VARIABLE, "1", true)
        switchedOff = true
        clearQueue(context)
    }

    /** Deletes the uploader's queue that an earlier version may have left; nothing else. */
    fun clearQueue(context: Context) {
        for (name in QUEUE) File(context.cacheDir, name).delete()
    }
}
