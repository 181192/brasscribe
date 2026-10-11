package no.brasscribe.play

import android.app.Application

class PlayApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        GoogleLeftovers.clear(this)
        container = AppContainer(this)
    }
}
