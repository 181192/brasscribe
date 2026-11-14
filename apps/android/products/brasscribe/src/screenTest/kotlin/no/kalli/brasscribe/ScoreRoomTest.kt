package no.kalli.brasscribe

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.text.TextLayoutResult
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The score on a small phone, upright with larger text: the player under it is two rows (the transport, then Mute
 * my part and Practice), "Bar 1 of 12" is on one line, and the score keeps the rest.
 */
@RunWith(AndroidJUnit4::class)
class ScoreRoomTest : ScreenTest() {
    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    private fun theScore() {
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitForEngravedScore()
        waitForTag("player", 20_000)
        rest()
    }

    private fun dp(px: Int) = px / rule.density.density

    private fun onASmallPhone(width: Int, height: Int, language: String) {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, width, height))
        textSize(1.3f)
        language(language)
        theScore()
        shot("score-$width-$language")
        val lines = mutableListOf<TextLayoutResult>()
        rule.onNodeWithTag("bar-of", useUnmergedTree = true).fetchSemanticsNode().config.getOrNull(SemanticsActions.GetTextLayoutResult)?.action?.invoke(lines)
        assertEquals("the bar's number is on one line", 1, lines.single().lineCount)
    }

    @Test
    fun at360DpInBokmalThePlayerIsTwoRows() {
        onASmallPhone(360, 640, "nb-NO")
        val player = dp(rule.onNodeWithTag("player").fetchSemanticsNode().size.height)
        assertTrue("the player is two rows ($player dp)", player <= 150f)
        val score = dp(rule.onNodeWithTag("score-view").fetchSemanticsNode().size.height)
        assertTrue("the score keeps the rest ($score dp)", score >= 280f)
    }

    @Test
    fun at320DpTheBarNumberIsOnOneLine() = onASmallPhone(320, 568, "en-GB")
}
