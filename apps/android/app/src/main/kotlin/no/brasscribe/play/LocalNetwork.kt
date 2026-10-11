package no.brasscribe.play

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import no.brasscribe.play.engine.LocalHosts

/**
 * The computer is reached over the local network. Android 17 keeps that network closed to an app until the
 * player allows it (one of the phone's Nearby devices permissions); Android 16 has no such question, and the
 * network is open there.
 */
object LocalNetwork {
    const val PERMISSION = Manifest.permission.ACCESS_LOCAL_NETWORK

    /** Whether this phone asks the player at all. */
    fun asked(sdk: Int = Build.VERSION.SDK_INT): Boolean = sdk >= Build.VERSION_CODES.CINNAMON_BUN

    /** Whether the app may reach the local network now. */
    fun allowed(context: Context): Boolean =
        !asked() || context.checkSelfPermission(PERMISSION) == PackageManager.PERMISSION_GRANTED

    /** Whether the app may reach [url] now: the phone itself is never closed to it. */
    fun reaches(context: Context, url: String?): Boolean = allowed(context) || LocalHosts.hostOf(url)?.let(::isThisPhone) == true

    internal fun isThisPhone(host: String): Boolean =
        host == "localhost" || host == "::1" || host == "[::1]" || Regex("""127(\.\d{1,3}){3}""").matches(host)

    /**
     * The phone's question about the local network is on screen. Android shows one question at a time and drops
     * a second one asked meanwhile, so another question (notifications) waits until this is false.
     */
    var asking by mutableStateOf(false)
}

/** A request to the computer that was not sent: the phone has the local network closed to the app. */
class LocalNetworkClosedException : java.io.IOException(MESSAGE) {
    companion object {
        /** Kept in the message, which is what is left of the exception once another one wraps it. */
        const val MESSAGE = "the local network is closed to the app"
    }
}
