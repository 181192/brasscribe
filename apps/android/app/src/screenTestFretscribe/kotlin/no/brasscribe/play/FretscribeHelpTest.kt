package no.brasscribe.play

import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Help says what the keys do on the tab, in English and in Bokmål, and not what they do on Brasscribe's music
 * stand. What it says is what the tab's tests check: Space and the arrows in `PracticeTest.theKeysPlayPauseAndMoveByBar`
 * (Page Down does not move the song), and Page Up and Page Down scrolling in `TabViewTest.theKeysMoveThePageBeforeAnythingHasTheFocus`.
 */
@RunWith(AndroidJUnit4::class)
class FretscribeHelpTest : ScreenTest() {
    private fun help(): String {
        rule.runOnUiThread { vm.home(); vm.navigate(Screen.HELP) }
        rule.waitForIdle()
        return shown()
    }

    @Test
    fun helpSaysWhatTheKeysDoOnTheTab() {
        val en = help()
        assertTrue(en, en.contains("Page Up and Page Down scroll the tab."))
        assertTrue(en, en.contains("Space plays and pauses the recording."))
        assertFalse("no promise that the page keys move the music: $en", en.contains("work when they send arrow keys or Page Up and Page Down"))
        language("nb")
        val nb = help()
        assertTrue(nb, nb.contains("Page Up og Page Down blar i tabben."))
        assertFalse(nb, nb.contains("Mellomrom starter og stopper musikken"))
    }
}
