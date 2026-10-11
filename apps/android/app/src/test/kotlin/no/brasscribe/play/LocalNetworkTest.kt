package no.brasscribe.play

import androidx.compose.ui.test.hasText
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
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
        rule.runOnUiThread { vm.openPairLink("brasscribe://pair?v=1&id=srv-1&name=Studio&h=192.168.0.2:8765&code=482913") }
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
}
