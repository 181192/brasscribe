package no.kalli.brasscribe

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The engraved title block ("Old Hundredth / arr. Brasscribe": the title, composer, arranger and rights) shows on a
 * tablet's score upright, where it does not crowd the music. On a phone (whose top bar names the score), on the music
 * stand and on its side the music starts at the top: on a small phone the block and the part's line took about 150 dp
 * above the first system.
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
        val before = vm.scoreController
        rule.runOnUiThread { vm.home(); vm.openScoreUri(android.net.Uri.fromFile(file)) }
        // The new score's controller, engraved and drawn: not the one of the score opened before it.
        waitForEngravedScore(before)
        settle()
        waitForEngravedScore()
    }

    /** The first engraved system: how far down it starts, against its own height. */
    private fun firstSystem(): Pair<Float, Float> {
        val first = vm.scoreController!!.standSystems().first()
        return first.top to (first.bottom - first.top)
    }

    private fun titled() = firstSystem().let { (top, height) -> top >= height / 2 }

    /** A tablet upright: the one place the title block is engraved. */
    private fun tablet() = assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 800, 1280))

    @Test
    fun onAPhoneUprightTheMusicStartsAtTheTop() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        open()
        assertTrue("on a phone, no title block: ${firstSystem()}", !titled())
        // The top bar names it.
        assertTrue(rule.onAllNodesWithText("Old Hundredth").fetchSemanticsNodes().isNotEmpty())
        // And what the block said is in the score's menu: the title in full, who arranged it.
        rule.onNodeWithTag("top-more").performClick()
        waitUntil(5_000) { rule.onAllNodesWithTag("score-credits").fetchSemanticsNodes().isNotEmpty() }
        val credits = rule.onNodeWithTag("score-credits").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].joinToString("\n") { it.text }
        assertTrue(credits, credits.contains("Old Hundredth") && credits.contains("arr. Brasscribe"))
        assertTrue(credits, credits.contains(text(R.string.about_part, "")))
        checkAccessibility()
    }

    /** In bokmål the menu says it in its words, and a long title is there in full. */
    @Test
    fun onAPhoneTheMenuHasTheTitleInFullInBokmal() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        language("nb-NO")
        val long = "Old Hundredth, the Doxology, as sung in the Genevan Psalter of 1551 and arranged for the whole band"
        open(hymn.replace(Regex("<work-title>[^<]*</work-title>"), "<work-title>$long</work-title>"))
        rule.onNodeWithTag("top-more").performClick()
        waitUntil(5_000) { rule.onAllNodesWithTag("score-credits").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(rule.onAllNodesWithText("Om partituret").fetchSemanticsNodes().isNotEmpty())
        val credits = rule.onNodeWithTag("score-credits").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].joinToString("\n") { it.text }
        assertTrue(credits, credits.contains(long) && credits.contains("Stemme: "))
    }

    @Test
    fun uprightOnATabletTheScoreShowsItsTitle() {
        tablet()
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
        tablet()
        open()
        rule.onNodeWithTag("stand-enter").performClick()
        waitUntil(20_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isNotEmpty() }
        settle()
        waitForEngravedScore()
        assertTrue("on the stand, no title block: ${firstSystem()}", !titled())
        ScreenDevice.back(rule)
        waitUntil(10_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isEmpty() }
        settle()
        waitForEngravedScore()
        assertTrue("off the stand, the title is back: ${firstSystem()}", titled())
    }

    @Test
    fun aLongTitleIsShownWholeAndNoTitleLeavesNoGap() {
        tablet()
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
