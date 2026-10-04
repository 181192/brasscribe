package no.brasscribe.play

import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The engraved title block ("Old Hundredth / arr. Brasscribe": the title, composer, arranger and rights) shows on the
 * score upright, where it does not crowd the music. On the music stand and on a phone on its side the top band names
 * the score, and the music starts at the top: there the block took about a third of the music's room.
 */
@RunWith(AndroidJUnit4::class)
class ScoreTitleTest : ScreenTest() {
    @Before
    fun setUp() {
        container.firstRunDone = true
        container.standHintShown = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @After
    fun upright() = ScreenDevice.turn(rule, sideways = false)

    private val hymn get() = String(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml")))

    private fun open(xml: String = hymn) {
        val file = File(rule.activity.cacheDir, "Title test.musicxml").apply { writeText(xml) }
        rule.runOnUiThread { vm.home(); vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        settle()
    }

    /** The first engraved system: how far down it starts, against its own height. */
    private fun firstSystem(): Pair<Float, Float> {
        val first = vm.scoreController!!.standSystems().first()
        return first.top to (first.bottom - first.top)
    }

    private fun titled() = firstSystem().let { (top, height) -> top >= height / 2 }

    @Test
    fun uprightTheScoreShowsItsTitle() {
        assertTrue(hymn.contains("<work-title>") && hymn.contains("<creator"))
        open()
        assertTrue("the title block is above the first system: ${firstSystem()}", titled())
    }

    @Test
    fun onItsSideTheMusicStartsAtTheTop() {
        ScreenDevice.turn(rule, sideways = true)
        open()
        assertTrue("on its side, no title block: ${firstSystem()}", !titled())
    }

    @Test
    fun onTheMusicStandTheMusicStartsAtTheTop() {
        open()
        rule.onNodeWithTag("stand-enter").performClick()
        waitUntil(20_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isNotEmpty() }
        settle()
        assertTrue("on the stand, no title block: ${firstSystem()}", !titled())
        ScreenDevice.back(rule)
        waitUntil(10_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isEmpty() }
        settle()
        assertTrue("off the stand, the title is back: ${firstSystem()}", titled())
    }

    @Test
    fun aLongTitleIsShownWholeAndNoTitleLeavesNoGap() {
        // A long title: still engraved upright, and the music under it.
        val long = "Old Hundredth, the Doxology, as sung in the Genevan Psalter of 1551 and arranged for the whole band"
        open(hymn.replace(Regex("<work-title>[^<]*</work-title>"), "<work-title>$long</work-title>"))
        assertEquals(null, vm.scoreController!!.state.value.error)
        assertTrue("the long title is above the first system: ${firstSystem()}", titled())
        // No title, no composer: no empty block above the music.
        open(hymn.replace(Regex("<work-title>[^<]*</work-title>"), "").replace(Regex("<movement-title>[^<]*</movement-title>"), "")
            .replace(Regex("<creator[^>]*>[^<]*</creator>"), "").replace(Regex("<rights>[^<]*</rights>"), ""))
        assertTrue("without a title, the music is at the top: ${firstSystem()}", !titled())
    }
}
