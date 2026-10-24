package no.kalli.scribe.play

import android.app.Application

/** The application of an app built on the shared flow: each product module's own names its [Product]. */
abstract class PlayApplication : Application() {
    lateinit var container: AppContainer
        private set

    /** The app this is. */
    abstract val product: Product

    override fun onCreate() {
        super.onCreate()
        GoogleLeftovers.clear(this)
        container = AppContainer(this, product)
    }
}
