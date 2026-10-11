package no.brasscribe.play

import android.app.Application
import android.content.Context

class PlayApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun attachBaseContext(base: Context) {
        // Before any content provider runs: what the app's own libraries need set before they start.
        Product.beforeStart()
        super.attachBaseContext(base)
    }

    override fun onCreate() {
        super.onCreate()
        GoogleLeftovers.clear(this)
        container = AppContainer(this)
    }
}
