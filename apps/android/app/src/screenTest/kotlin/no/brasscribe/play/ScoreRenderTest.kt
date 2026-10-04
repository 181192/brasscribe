package no.brasscribe.play

import android.app.UiAutomation
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File

/**
 * The score shows every time it is opened from Home, not only after a trip to the music stand: alphaTab
 * finished the render, laid out systems, and the notation is on screen (ink in the score view), for the
 * fixture opened over and over, a longer score, and after a rotation.
 */
@RunWith(AndroidJUnit4::class)
class ScoreRenderTest : ScreenTest() {

    @Before
    fun setUp() {
        container.firstRunDone = true
        container.standHintShown = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    /** The hymn's bars [times] over in every part, renumbered: a longer score. */
    private fun repeated(xml: String, times: Int): String {
        if (times <= 1) return xml
        val part = Regex("""(<part\s+id="[^"]+"\s*>)(.*?)(</part>)""", RegexOption.DOT_MATCHES_ALL)
        val measure = Regex("""<measure\b[^>]*>.*?</measure>""", RegexOption.DOT_MATCHES_ALL)
        return part.replace(xml) { m ->
            val bars = measure.findAll(m.groupValues[2]).map { it.value }.toList()
            var n = 0
            val body = (0 until times).joinToString("\n") {
                bars.joinToString("\n") { b -> n++; b.replaceFirst(Regex("""number="[^"]*""""), "number=\"$n\"") }
            }
            m.groupValues[1] + body + m.groupValues[3]
        }
    }

    /** Puts [title] in the library (opened once as a file), then goes Home. */
    private fun addToLibrary(title: String, times: Int = 1) {
        val xml = repeated(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml")).decodeToString(), times)
            .replace(Regex("""<work-title>[^<]*</work-title>"""), "<work-title>$title</work-title>")
        val file = File(rule.activity.cacheDir, "$title.musicxml").apply { writeText(xml) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(20_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
    }

    private fun openFromHome(title: String) {
        waitUntil(10_000) { rule.onAllNodesWithText(title, substring = true).fetchSemanticsNodes().isNotEmpty() }
        val before = vm.scoreController
        rule.onAllNodesWithText(title, substring = true).onFirst().performClick()
        waitUntil(20_000) { vm.scoreController !== before && rule.onAllNodesWithTag("score-view").fetchSemanticsNodes().isNotEmpty() }
    }

    /** Waits for a finished render with systems in it, then checks the notation is really on screen. */
    private fun assertScoreShows(label: String, onScreen: Boolean = true) {
        val c = vm.scoreController!!
        waitUntil(20_000) { c.renders.value > 0 && c.standSystems().isNotEmpty() }
        rule.waitForIdle()
        // The surface is laid out to the engraving on a pass after the render: wait for it.
        waitUntil(5_000) { var w = 0; rule.runOnUiThread { w = surface(c).width }; w > 0 }
        var detail = ""
        var clipped = false
        rule.runOnUiThread {
            val surface = surface(c)
            val clip = surface.clipBounds
            detail = "view ${c.view.width}x${c.view.height}, surface ${surface.width}x${surface.height}, clip $clip, systems ${c.standSystems().size}"
            // The credit clip may take off the bottom, never the width of the music.
            clipped = clip != null && clip.right < surface.width
        }
        android.util.Log.i("ScoreRenderTest", "$label: $detail")
        assertTrue("$label: the score is clipped to less than its width ($detail)", !clipped)
        if (!onScreen) return
        // alphaTab hands its page over in pieces once the render is done: the notation is there a moment later.
        var ink = 0.0
        runCatching { waitUntil(5_000) { ink = inkShare(rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap()); ink >= MIN_INK } }
        assertTrue("$label: no notation on screen (ink ${"%.4f".format(ink)}; $detail)", ink >= MIN_INK)
    }

    private fun surface(c: no.brasscribe.play.score.ScoreController) = c.view.findViewById<android.view.View>(net.alphatab.R.id.renderSurface)

    /** Share of pixels that differ clearly from the paper (the view's top-left corner). */
    private fun inkShare(bmp: Bitmap): Double {
        val paper = bmp.getPixel(1, 1)
        fun lum(p: Int) = (android.graphics.Color.red(p) * 299 + android.graphics.Color.green(p) * 587 + android.graphics.Color.blue(p) * 114) / 1000
        val base = lum(paper)
        var ink = 0
        var n = 0
        for (y in 0 until bmp.height step 2) for (x in 0 until bmp.width step 2) {
            n++
            if (kotlin.math.abs(lum(bmp.getPixel(x, y)) - base) > 80) ink++
        }
        return ink.toDouble() / n
    }

    private fun backHome() {
        rule.runOnUiThread { vm.back() }
        waitUntil(10_000) { rule.onAllNodesWithTag("score-view").fetchSemanticsNodes().isEmpty() }
    }

    @Test
    fun scoreShowsEveryTimeItIsOpenedFromHome() {
        addToLibrary("Old Hundredth")
        repeat(OPENS) { i ->
            openFromHome("Old Hundredth")
            assertScoreShows("open-$i")
            backHome()
        }
    }

    @Test
    fun longerScoreAndRotationShowTheScore() {
        addToLibrary("Hundredth Long", times = 8)
        repeat(5) { i ->
            openFromHome("Hundredth Long")
            assertScoreShows("long-$i")
            backHome()
        }
        openFromHome("Hundredth Long")
        ScreenDevice.turn(rule, sideways = true)
        settle()
        // A phone on its side leaves the score no height under the controls, so only the render is checked.
        assertScoreShows("long-landscape", onScreen = false)
        ScreenDevice.turn(rule, sideways = false)
        settle()
        assertScoreShows("long-portrait-again")
    }

    /**
     * The screen tests' wait for an engraved score ends once alphaTab has engraved what was asked for and painted it, not
     * before its thread has started on it, nor when the render is done and the parts in view are still blank: with
     * alphaTab's thread slow (as on a busy CI runner), the new engraving is on screen as soon as the wait is over.
     */
    @Test
    fun theWaitForAnEngravedScoreWaitsForThePaint() {
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        val before = vm.scoreController
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitForEngravedScore(before)
        val c = vm.scoreController!!
        val renders = c.renders.value
        slowEngraver(c)
        // Engraved again, without the title block (the score upright has it).
        rule.runOnUiThread { c.setTitleShown(false) }
        waitForEngravedScore()
        assertTrue("the wait was over before the new render (renders: $renders, then ${c.renders.value})", c.renders.value > renders)
        val ink = inkShare(rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap())
        assertTrue("no notation on screen when the wait was over (ink ${"%.4f".format(ink)})", ink >= MIN_INK)
    }

    /**
     * A score opened while another is on screen (from a share, or Open with) is the one shown and engraved: the score
     * view is the new score's, not the view of the one before it, which is no longer engraved.
     */
    @Test
    fun aScoreOpenedOverAnotherIsShown() {
        fun open(title: String) {
            val xml = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml")).decodeToString()
                .replace(Regex("""<work-title>[^<]*</work-title>"""), "<work-title>$title</work-title>")
            val file = File(rule.activity.cacheDir, "$title.musicxml").apply { writeText(xml) }
            val before = vm.scoreController
            rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
            waitForEngravedScore(before)
        }
        open("First score")
        open("Second score")
        val c = vm.scoreController!!
        var shown = false
        rule.runOnUiThread { shown = c.view.isAttachedToWindow && c.view.width > 0 }
        assertTrue("the second score's view is on screen", shown)
        val ink = inkShare(rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap())
        assertTrue("no notation on screen (ink ${"%.4f".format(ink)})", ink >= MIN_INK)
    }

    /** alphaTab's thread stops for a while before each render's work, the parts it paints afterwards included. */
    private fun slowEngraver(c: no.brasscribe.play.score.ScoreController) {
        // (alphaTab's thread is not public: it is reached through the renderer the view has.)
        val renderer: Any = c.view.api.renderer
        val inner = renderer.javaClass.getMethod("getInstance").invoke(renderer)!!
        val thread = inner.javaClass.getDeclaredField("_worker").apply { isAccessible = true }.get(inner)!!
        val post = thread.javaClass.getMethod("postToWorker", Function0::class.java)
        val pause: () -> Unit = { Thread.sleep(600) }
        rule.runOnUiThread {
            post.invoke(thread, pause)
            c.view.api.renderStarted.on { _ -> post.invoke(thread, pause) }
        }
    }

    private companion object {
        const val OPENS = 20
        /** A page of notation inks a few percent of the view; the clipped surface left well under 0.2 %. */
        const val MIN_INK = 0.005
    }
}
