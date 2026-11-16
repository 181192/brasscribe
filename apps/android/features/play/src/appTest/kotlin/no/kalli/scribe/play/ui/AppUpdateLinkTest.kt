package no.kalli.scribe.play.ui

import android.content.Intent
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.connection.ConnectionState
import no.kalli.scribe.connection.Credential
import no.kalli.scribe.engine.Wire
import no.kalli.scribe.play.R
import no.kalli.scribe.play.screen.ScreenTest
import no.kalli.scribe.play.screen.StubEngine
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf

/**
 * When the app is the one behind the engine, the connection row's button opens the app's own file for this phone in
 * its newest release. (The browser is a device's; on the JVM the intent the button starts is checked.)
 */
@RunWith(AndroidJUnit4::class)
class AppUpdateLinkTest : ScreenTest() {
    private val newer = StubEngine(Wire.INTERFACE_VERSION + 1)

    @After fun stopTheEngine() = newer.close()

    @Test
    fun theUpdateButtonOpensTheAppsOwnFile() {
        rule.runOnUiThread {
            container.settings.url = newer.url
            container.settings.serverId = StubEngine.SERVER_ID
            container.settings.serverName = "Brasscribe on Studio"
            container.credentials.put(Credential(StubEngine.SERVER_ID, StubEngine.TOKEN, "d1", "Brasscribe on Studio", newer.url))
            container.settings.paired = true
            vm.connection.retry()
        }
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.NeedsUpdate }
        rule.runOnUiThread { vm.home() }
        val button = text(R.string.conn_get_app_update)
        waitUntil { rule.onAllNodes(hasText(button)).fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText(button).performScrollTo().performClick()
        rule.waitForIdle()
        val started = shadowOf(rule.activity).nextStartedActivity
        assertEquals(Intent.ACTION_VIEW, started?.action)
        assertEquals(appDownload(container.product), started?.data?.toString())
    }
}
