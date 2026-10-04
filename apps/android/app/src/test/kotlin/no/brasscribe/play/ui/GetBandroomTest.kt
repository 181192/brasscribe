package no.brasscribe.play.ui

import android.content.Intent
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf

/**
 * Where to get Brasscribe Bandroom: the pairing screen and Help show the address of the latest release, as text that
 * can be selected, and a button that opens it in the phone's browser. (The browser is a device's; on the JVM the
 * intent the button starts is checked.)
 */
@RunWith(AndroidJUnit4::class)
class GetBandroomTest : ScreenTest() {
    private fun opensTheLatestRelease(screen: Screen) {
        rule.runOnUiThread { vm.home(); vm.navigate(screen) }
        rule.waitForIdle()
        assertEquals("https://github.com/181192/brasscribe/releases/latest", BANDROOM_DOWNLOAD)
        rule.onNodeWithTag("bandroom-address", useUnmergedTree = true).performScrollTo().assertTextEquals(BANDROOM_DOWNLOAD)
        assertTrue(shown(), shown().contains(text(R.string.bandroom_get_title)))
        rule.onNodeWithText(text(R.string.bandroom_open)).performScrollTo().performClick()
        rule.waitForIdle()
        val started = shadowOf(rule.activity).nextStartedActivity
        assertEquals(Intent.ACTION_VIEW, started?.action)
        assertEquals(BANDROOM_DOWNLOAD, started?.data?.toString())
    }

    @Test
    fun thePairingScreenLinksToTheLatestRelease() = opensTheLatestRelease(Screen.COMPANION)

    @Test
    fun helpLinksToTheLatestRelease() = opensTheLatestRelease(Screen.HELP)
}
