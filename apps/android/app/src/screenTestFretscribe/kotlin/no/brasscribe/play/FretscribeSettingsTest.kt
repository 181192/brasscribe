package no.brasscribe.play

import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Settings and the pairing screen say nothing a player can't use: no developer's command, and none of the
 * music stand's switches (a tab has no music stand). In English and in Bokmål.
 */
@RunWith(AndroidJUnit4::class)
class FretscribeSettingsTest : ScreenTest() {
    private fun go(vararg to: Screen) = rule.runOnUiThread { vm.home(); to.forEach(vm::navigate) }

    private fun assertPlayersWordsOnly(lang: String) {
        go(Screen.SETTINGS)
        rule.waitForIdle()
        val settings = shown()
        assertFalse("$lang: Settings has no music stand: $settings", settings.contains(text(R.string.stand_enter)))
        for (tag in listOf("setting-stand-follow", "setting-stand-controls")) {
            assertEquals("$lang: $tag", 0, rule.onAllNodesWithTag(tag).fetchSemanticsNodes().size)
        }
        go(Screen.SETTINGS, Screen.COMPANION)
        rule.onNodeWithText(text(R.string.details_show)).performScrollTo().performClick()
        rule.waitForIdle()
        val pairing = shown()
        assertFalse("$lang: the pairing screen names no developer's command: $pairing", pairing.contains("pixi") || pairing.contains("serve-lan"))
        // What is left of the technical details is still there.
        assertEquals(1, rule.onAllNodes(androidx.compose.ui.test.hasText(text(R.string.companion_tech_details))).fetchSemanticsNodes().size)
    }

    @Test
    fun settingsAndPairingShowNoDeveloperCommandAndNoMusicStand() {
        assertPlayersWordsOnly("en")
        language("nb")
        assertPlayersWordsOnly("nb")
    }
}
