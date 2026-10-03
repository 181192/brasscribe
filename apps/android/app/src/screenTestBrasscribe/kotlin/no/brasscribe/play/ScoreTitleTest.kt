package no.brasscribe.play

import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The score on screen starts with the music: the top bar (and the music stand's band) already name it, so the
 * engraved title block ("Old Hundredth / arr. Brasscribe") is not drawn over the first system. On a phone on its
 * side it took about a third of the music's room.
 */
@RunWith(AndroidJUnit4::class)
class ScoreTitleTest : ScreenTest() {
    @Before
    fun setUp() {
        container.firstRunDone = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @Test
    fun theFirstSystemIsAtTheTopOfTheScore() {
        val xml = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))
        assertTrue("the fixture has a title to leave out", String(xml).contains("<work-title>") || String(xml).contains("<movement-title>"))
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        rule.runOnUiThread { vm.home(); vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        settle()
        val systems = vm.scoreController!!.standSystems()
        assertTrue("engraved", systems.isNotEmpty())
        val first = systems.first()
        val height = first.bottom - first.top
        // Above the first system there is only the staff's own margin, well under half a system's height.
        assertTrue("the first system starts at ${first.top} px, a system is $height px tall", first.top < height / 2)
    }
}
