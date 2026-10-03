package no.brasscribe.play

import android.app.UiAutomation
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.model.ArrangeOptions
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File

/**
 * Upright, the score keeps the height too: with your part in a lineup that lacks your seat (the mapping
 * banner) and its source pill both showing, the score view has at least 55 % of the height inside the
 * system bars and shows notation, at 100 % and 200 % text. Closing the banner keeps it closed for the score.
 */
@RunWith(AndroidJUnit4::class)
class ScorePortraitTest : ScreenTest() {
    override val shots = "brasscribe/score-portrait"

    @Before
    fun setUp() {
        rule.runOnUiThread { container.firstRunDone = true; container.updateSeat(SeatChoice.Player("1st-baritone")) }
    }

    @After
    fun tearDown() {
        rule.runOnUiThread { container.updateSeat(SeatChoice.NotSet) }
    }

    /** Old Hundredth for the small band, which has no 1st Baritone: your part is Euphonium. */
    private fun openSmallBand() {
        val json = String(checkNotNull(ScreenDevice.fixture("old-hundredth/composition.json")))
        val composition = container.core.decodeComposition(json)
        val small = composition.arrangedFor(Lineup.MINIMAL, "faithful")
        val xml = container.core.arrangeMusicXmlWith(composition, ArrangeOptions(lineup = "minimal"))!!
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth", SourceKind.SCORE, 0.0))
            vm.result.value = TranscriptionResult(small, xml, Profile.BRASS_BAND, onDevice = true, compositionJson = container.core.encodeComposition(small))
            vm.navigate(Screen.SCORE)
        }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        settle()
    }

    private fun check(label: String, fontScale: String) {
        textSize(fontScale.toFloat())
        openSmallBand()
        shot(label)
        val placed = { tag: String -> rule.onAllNodesWithTag(tag).fetchSemanticsNodes().any { it.layoutInfo.isPlaced } }
        if (fontScale == "1.0") assertTrue("$label: the mapping banner shows", placed("mapped-notice"))
        assertTrue("$label: the source pill shows", rule.onAllNodesWithTag("source-recording").fetchSemanticsNodes().isNotEmpty() ||
            rule.onAllNodesWithTag("source-arranged").fetchSemanticsNodes().isNotEmpty())

        var available = 0
        rule.runOnUiThread {
            val decor = rule.activity.window.decorView
            val bars = ViewCompat.getRootWindowInsets(decor)!!.getInsets(WindowInsetsCompat.Type.systemBars())
            available = decor.height - bars.top - bars.bottom
        }
        val density = rule.activity.resources.displayMetrics.density
        val score = rule.onNodeWithTag("score-view").getBoundsInRoot()
        val share = (score.bottom - score.top).value * density / available
        assertTrue("$label: the score has ${"%.0f".format(share * 100)} % of $available px", share >= 0.55f)
        val ink = inkShare(rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap())
        assertTrue("$label: no notation on screen (ink ${"%.4f".format(ink)})", ink >= 0.005)
        // Rule 7: every control shows whole, or not at all. None is cut by its container or runs under the score.
        val scoreBox = rule.onNodeWithTag("score-view").fetchSemanticsNode().boundsInRoot
        val controls = rule.onAllNodes(hasClickAction() and !hasAnyAncestor(hasTestTag("score-view"))).fetchSemanticsNodes()
            .filter { it.layoutInfo.isPlaced }
        assertTrue("$label: no controls", controls.size >= 4)
        for (n in controls) {
            val b = n.boundsInRoot
            val full = n.layoutInfo.height
            assertTrue("$label: a control shows ${b.height} of $full px (${n.config})", b.height >= full - 1)
            assertTrue("$label: a control runs under the score (${n.config})", b.bottom <= scoreBox.top + 1 || b.top >= scoreBox.bottom - 1)
        }
        // Mute my part is in reach without scrolling.
        assertTrue("$label: Mute my part shows", rule.onAllNodesWithText(rule.activity.getString(R.string.mute_my_part)).fetchSemanticsNodes().any { it.layoutInfo.isPlaced })
    }

    private fun inkShare(bmp: Bitmap): Double {
        fun lum(p: Int) = (android.graphics.Color.red(p) * 299 + android.graphics.Color.green(p) * 587 + android.graphics.Color.blue(p) * 114) / 1000
        val base = lum(bmp.getPixel(1, 1))
        var ink = 0
        var n = 0
        for (y in 0 until bmp.height step 2) for (x in 0 until bmp.width step 2) {
            n++
            if (kotlin.math.abs(lum(bmp.getPixel(x, y)) - base) > 80) ink++
        }
        return ink.toDouble() / n
    }

    @Test
    fun portraitAt100PercentText() = check("portrait-100", "1.0")

    @Test
    fun portraitAt200PercentText() = check("portrait-200", "2.0")

    @Test
    fun theBannerStaysClosedForTheScore() {
        openSmallBand()
        rule.onNodeWithTag("mapped-close").performClick()
        rule.waitForIdle()
        assertTrue(vm.mappedNoticeSeen.value)
        assertFalse(rule.onAllNodesWithTag("mapped-notice").fetchSemanticsNodes().any { it.layoutInfo.isPlaced })
    }
}
