package no.brasscribe.play

import android.app.Application
import android.content.Context
import android.system.Os

class PlayApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun attachBaseContext(base: Context) {
        // ONNX Runtime reports to Microsoft unless this is set when it starts (the first OrtEnvironment).
        // The manifest already removes the provider that sets up its uploader; this keeps the runtime's
        // telemetry off whatever else brings it in. attachBaseContext runs before any content provider.
        Os.setenv(ORT_DISABLE_TELEMETRY, "1", true)
        super.attachBaseContext(base)
    }

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }

    companion object {
        const val ORT_DISABLE_TELEMETRY = "ORT_DISABLE_TELEMETRY"
    }
}
