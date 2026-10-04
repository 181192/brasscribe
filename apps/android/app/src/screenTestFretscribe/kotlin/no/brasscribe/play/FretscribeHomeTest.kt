package no.brasscribe.play

import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Home offers no "Open a tab" until an imported tab opens in the tab view: today a MusicXML file would open in
 * Brasscribe's score screen. The other ways in stay.
 */
@RunWith(AndroidJUnit4::class)
class FretscribeHomeTest : ScreenTest() {
    private fun home(): String {
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
        return shown()
    }

    @Test
    fun sheetMusicThatArrivesAnotherWayIsRefused() {
        val xml = checkNotNull(no.brasscribe.play.screen.ScreenDevice.fixture("bass-line/tab.musicxml"))
        val file = java.io.File(rule.activity.cacheDir, "A tab.musicxml").apply { writeBytes(xml) }
        rule.runOnUiThread { vm.home(); vm.importUri(android.net.Uri.fromFile(file)) }
        waitUntil(5_000) { vm.status.value?.text == "Fretscribe can't open sheet music yet; it makes tabs from recordings." }
        assertTrue(vm.screen.value.toString(), vm.screen.value == listOf(Screen.HOME))
        assertFalse(vm.busy.value)
    }

    @Test
    fun homeHasNoOpenATab() {
        val en = home()
        assertTrue(en, en.contains("Record with the microphone"))
        assertFalse(en, en.contains("Open a tab"))
        assertFalse(en, en.contains("MusicXML"))
        language("nb")
        val nb = home()
        assertTrue(nb, nb.contains("Spill inn med mikrofonen"))
        assertFalse(nb, nb.contains("Åpne en tab"))
        assertFalse(nb, nb.contains("MusicXML"))
    }
}
