package no.brasscribe.play

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.screen.ShownQrCode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Pairing by the computer's QR code: the app's own scanner (the camera, read on the phone) hands what it read to
 * pairing, says so when it is not a pairing code, can be left, and leaves typing the code there when the camera is
 * not allowed.
 */
@RunWith(AndroidJUnit4::class)
class PairByScanTest : ScreenTest() {
    private fun waitForText(id: Int) = waitUntil(5_000) { rule.onAllNodes(hasText(text(id))).fetchSemanticsNodes().isNotEmpty() }

    private fun theWaysToPair() = waitForText(R.string.pair_scan)

    @Test
    fun theScannerSaysWhatTheCameraIsForAndReadsOnThePhone() {
        pairingScanner()
        waitForText(R.string.pair_scan_title)
        assertTrue(shown().contains(text(R.string.pair_scan_on_phone)))
        rule.onNodeWithTag("pair-camera").assertExists()
        // The scanner has its own Cancel in place of Connect.
        assertEquals(0, rule.onAllNodes(hasText(text(R.string.companion_connect))).fetchSemanticsNodes().size)
    }

    @Test
    fun aScannedCodeGoesToPairing() {
        // A link that asks for a pinned certificate is answered on the phone, before any address is tried.
        pairingScanner("brasscribe://pair?v=1&id=srv-1&name=Studio&h=127.0.0.1:9&code=482913&fp=abc")
        waitForText(R.string.pair_needs_update)
        assertEquals(text(R.string.pair_needs_update), vm.companionState.value)
        theWaysToPair()
    }

    @Test
    fun aCodeThatIsNotFromTheComputerSaysSo() {
        pairingScanner("https://example.org/menu")
        waitForText(R.string.pair_link_invalid)
        theWaysToPair()
        assertEquals(null, vm.pendingLink.value)
    }

    @Test
    fun cancelLeavesTheScanner() {
        pairingScanner()
        waitForText(R.string.pair_scan_title)
        rule.onNode(hasText(text(R.string.cancel))).performScrollTo().performClick()
        theWaysToPair()
        assertEquals(0, rule.onAllNodes(hasText(text(R.string.pair_scan_title))).fetchSemanticsNodes().size)
    }

    @Test
    fun aCameraThatIsNotAllowedLeavesTypingTheCode() {
        // The answer to the system's question is given by the test on the JVM; on a device it is the system's dialog.
        assumeTrue(ScreenDevice.JVM)
        ScreenDevice.cameraNotAllowedYet(rule)
        rule.runOnUiThread { container.qrCamera = ShownQrCode("brasscribe://pair?v=1&id=srv-1&h=127.0.0.1:9&code=1&fp=abc"); vm.navigate(Screen.SETTINGS); vm.navigate(Screen.COMPANION) }
        rule.waitForIdle()
        rule.onNode(hasText(text(R.string.pair_scan))).performScrollTo().performClick()
        waitForText(R.string.pair_scan_title)
        // Nothing is read before the camera is allowed.
        assertEquals(null, vm.companionState.value)
        assertTrue("the app asked for the camera", ScreenDevice.answerPermission(rule, allow = false))
        waitForText(R.string.pair_camera_refused)
        theWaysToPair()
        assertTrue(shown().contains(text(R.string.companion_code)))
        rule.onNode(hasText(text(R.string.pair_camera_settings))).assertExists()
    }

    @Test
    fun aCameraAllowedWhenAskedScans() {
        assumeTrue(ScreenDevice.JVM)
        ScreenDevice.cameraNotAllowedYet(rule)
        rule.runOnUiThread { container.qrCamera = ShownQrCode("brasscribe://pair?v=1&id=srv-1&h=127.0.0.1:9&code=1&fp=abc"); vm.navigate(Screen.SETTINGS); vm.navigate(Screen.COMPANION) }
        rule.waitForIdle()
        rule.onNode(hasText(text(R.string.pair_scan))).performScrollTo().performClick()
        waitForText(R.string.pair_scan_title)
        assertTrue("the app asked for the camera", ScreenDevice.answerPermission(rule, allow = true))
        waitForText(R.string.pair_needs_update)
    }
}
