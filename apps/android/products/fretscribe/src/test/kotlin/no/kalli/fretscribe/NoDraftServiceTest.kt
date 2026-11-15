package no.kalli.fretscribe

import android.content.pm.PackageManager
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Fretscribe writes nothing down on the phone, so its manifest has no draft service and no mediaProcessing
 * foreground service: one fewer declaration for Google Play, and nothing that could start one.
 */
@RunWith(AndroidJUnit4::class)
class NoDraftServiceTest {
    @Test
    fun theManifestHasNoDraftServiceAndNoMediaProcessing() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val info = context.packageManager.getPackageInfo(
            context.packageName, PackageManager.GET_SERVICES or PackageManager.GET_PERMISSIONS)
        val services = info.services.orEmpty().map { it.name }
        assertFalse("no draft service in $services", services.any { it.endsWith(".DraftService") })
        // The other services are still there: the check is not passing on an empty list.
        assertEquals(true, services.any { it.endsWith(".ComputerJobService") })
        val permissions = info.requestedPermissions.orEmpty().toList()
        assertFalse(permissions.contains("android.permission.FOREGROUND_SERVICE_MEDIA_PROCESSING"))
        assertFalse(Fretscribe.makesScoresOnThePhone)
    }
}
