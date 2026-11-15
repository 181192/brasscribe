package no.kalli.brasscribe

import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Brasscribe makes band drafts on the phone, so its merged manifest keeps the draft service as a mediaProcessing
 * foreground service, with its permission (Fretscribe's drops both: NoDraftServiceTest).
 */
@RunWith(AndroidJUnit4::class)
class DraftServiceDeclaredTest {
    @Test
    fun theManifestKeepsTheDraftServiceAndMediaProcessing() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val info = context.packageManager.getPackageInfo(
            context.packageName, PackageManager.GET_SERVICES or PackageManager.GET_PERMISSIONS)
        val draft = info.services.orEmpty().singleOrNull { it.name.endsWith(".DraftService") }
        assertTrue("a draft service in ${info.services.orEmpty().map { it.name }}", draft != null)
        assertEquals(ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING, draft!!.foregroundServiceType)
        assertTrue(info.requestedPermissions.orEmpty().contains("android.permission.FOREGROUND_SERVICE_MEDIA_PROCESSING"))
    }
}
