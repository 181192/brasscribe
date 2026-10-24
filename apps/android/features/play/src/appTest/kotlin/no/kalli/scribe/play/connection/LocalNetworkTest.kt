package no.kalli.scribe.play.connection

import no.kalli.scribe.play.R

import no.kalli.scribe.connection.*

import no.kalli.scribe.play.Screen

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import no.kalli.scribe.connection.ConnectionState
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * Android 17 keeps the local network closed to the app until the player allows it. The pairing screen asks, looks
 * for the computer only once it may, and says what is wrong when the player said no. (Run on Android 17: Android 16,
 * which the other screen tests run on, has no such question.)
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [37])
class LocalNetworkTest : ScreenTest() {
    private fun waitForText(id: Int) = waitUntil(5_000) { rule.onAllNodes(hasText(text(id))).fetchSemanticsNodes().isNotEmpty() }
    private fun shows(id: Int) = rule.onAllNodes(hasText(text(id))).fetchSemanticsNodes().isNotEmpty()

    private fun pairingScreenNotAllowedYet() {
        shadowOf(rule.activity.application).denyPermissions(LocalNetwork.PERMISSION)
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS); vm.navigate(Screen.COMPANION) }
        rule.waitForIdle()
    }

    @Test
    fun onlyAndroid17Asks() {
        assertFalse(LocalNetwork.asked(36))
        assertTrue(LocalNetwork.asked(37))
        assertTrue(LocalNetwork.asked())
    }

    @Test
    fun thePairingScreenAsksAndSaysSoWhenRefused() {
        pairingScreenNotAllowedYet()
        assertEquals(listOf(LocalNetwork.PERMISSION), shadowOf(rule.activity).lastRequestedPermission?.requestedPermissions?.toList())
        // Nothing is looked for yet, and the screen does not say it is looking.
        assertFalse(shows(R.string.companion_searching))
        assertTrue("the app asked for the local network", ScreenDevice.answerPermission(rule, allow = false))
        waitForText(R.string.pair_network_refused)
        assertFalse(shows(R.string.companion_searching))
        assertTrue(shows(R.string.pair_camera_settings))
        // Typing the code is still there, for the day the player allows it.
        assertTrue(shown().contains(text(R.string.companion_code)))
    }

    @Test
    fun aPairingLinkSaysSoToo() {
        shadowOf(rule.activity.application).denyPermissions(LocalNetwork.PERMISSION)
        rule.runOnUiThread { vm.openPairLink("scribe://pair?v=1&id=srv-1&name=Studio&h=192.168.0.2:8765&code=482913") }
        rule.waitForIdle()
        ScreenDevice.answerPermission(rule, allow = false)
        waitForText(R.string.pair_network_refused)
        assertTrue(shows(R.string.companion_connect))
    }

    @Test
    fun allowedInThePhonesSettingsItLooksForTheComputer() {
        pairingScreenNotAllowedYet()
        ScreenDevice.answerPermission(rule, allow = false)
        waitForText(R.string.pair_network_refused)
        // The player allows it in the phone's settings and comes back to the app.
        shadowOf(rule.activity.application).grantPermissions(LocalNetwork.PERMISSION)
        rule.activityRule.scenario.moveToState(Lifecycle.State.STARTED)
        rule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        waitForText(R.string.companion_searching)
        assertFalse(shows(R.string.pair_network_refused))
    }

    /** A phone paired with a computer on the network, which Android has closed to the app. */
    private fun pairedAndNotAllowed() {
        shadowOf(rule.activity.application).denyPermissions(LocalNetwork.PERMISSION)
        rule.runOnUiThread {
            container.settings.url = "http://192.168.0.2:8765"
            container.settings.serverId = "srv-1"
            container.settings.serverName = "Studio"
            container.settings.paired = true
            vm.connection.retry()
            vm.home()
        }
        rule.waitForIdle()
    }

    @Test
    fun aPairedPhoneIsAskedWhenTheAppOpens() {
        pairedAndNotAllowed()
        // The app is opened again, as from the launcher.
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
        assertEquals(listOf(LocalNetwork.PERMISSION), shadowOf(rule.activity).lastRequestedPermission?.requestedPermissions?.toList())
    }

    @Test
    fun aPhoneWithNothingPairedIsNotAskedWhenTheAppOpens() {
        shadowOf(rule.activity.application).denyPermissions(LocalNetwork.PERMISSION)
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
        assertEquals(null, shadowOf(rule.activity).lastRequestedPermission)
    }

    @Test
    fun theConnectionRowSaysTheNetworkIsClosedAtOnce() {
        pairedAndNotAllowed()
        // Never "Connected" or "Looking for": the row says what is wrong as soon as it is shown, in both languages.
        for (tag in listOf("en-GB", "nb-NO")) {
            language(tag)
            rule.runOnUiThread { vm.home() }
            waitForText(R.string.conn_network_closed)
            val home = shown()
            assertFalse(home, home.contains(text(R.string.conn_connected, vm.serverDisplayName("Studio"))))
            assertFalse(home, home.contains(text(R.string.conn_reconnecting, vm.serverDisplayName("Studio"))))
            assertTrue(home, shows(R.string.conn_allow))
        }
        assertEquals(ConnectionState.NetworkClosed("Studio"), vm.connection.state.value)
        assertTrue(text(R.string.conn_network_closed), text(R.string.conn_network_closed).startsWith("Appen har ikke lov"))
        // The button goes to the pairing screen, which asks again.
        rule.onNode(hasText(text(R.string.conn_allow))).performScrollTo().performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.COMPANION }
        rule.waitForIdle()
        assertEquals(listOf(LocalNetwork.PERMISSION), shadowOf(rule.activity).lastRequestedPermission?.requestedPermissions?.toList())
        // There the row says it too, once (the note under it is for a phone with nothing paired), with the way to the settings.
        waitForText(R.string.conn_network_closed)
        assertTrue(shows(R.string.conn_allow))
        assertFalse(shows(R.string.pair_network_refused))
    }

    @Test
    fun allowedThePairedComputerIsLookedForAgain() {
        pairedAndNotAllowed()
        waitForText(R.string.conn_network_closed)
        shadowOf(rule.activity.application).grantPermissions(LocalNetwork.PERMISSION)
        rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
        rule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        waitUntil(5_000) { vm.connection.state.value !is ConnectionState.NetworkClosed }
    }

    @Test
    fun aTapOnReadySaysTheNetworkIsClosed() {
        pairedAndNotAllowed()
        rule.runOnUiThread { vm.openFinishedJob("0123456789abcdef") }
        waitUntil(5_000) { vm.status.value?.text == text(R.string.pair_network_refused) }
    }
}
