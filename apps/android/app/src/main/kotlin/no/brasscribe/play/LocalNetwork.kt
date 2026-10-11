package no.brasscribe.play

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build

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
}
