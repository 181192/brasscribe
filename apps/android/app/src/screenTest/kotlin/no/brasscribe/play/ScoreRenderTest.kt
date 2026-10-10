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
import androidx.compose.ui.test.click
import androidx.compose.ui.test.performTouchInput
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
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

    /**
     * The score is still the score after the talking score took its place, and after a turn while it was there: it is
     * drawn, it is engraved again when asked (a zoom), a tap on a bar moves the cursor there, and it plays. The talking
     * score's own "play this bar" plays too. alphaTab tears its view down for good when it leaves the window, so it never does.
     */
    @Test
    fun theScoreSurvivesTheTalkingScore() {
        val detaches = openAndCountDetaches()
        fun readAloud(on: Boolean) {
            rule.onNodeWithTag("top-more").performClick()
            rule.onNodeWithText(text(R.string.read_aloud)).performClick()
            waitUntil(5_000) { rule.onAllNodesWithTag("score-view").fetchSemanticsNodes().isEmpty() == on }
        }
        val c = vm.scoreController!!
        readAloud(true)
        assertTargetsAre48Dp("on the talking score")
        checkAccessibility()
        assertPlays("on the talking score")
        assertTargetsAre48Dp("on the talking score, playing")
        // A change made while the talking score is read (it has the pitch and the parts) is engraved under it, and shown after.
        val renders = c.renders.value
        rule.runOnUiThread { c.setConcertPitch(!c.state.value.concertPitch) }
        readAloud(false)
        runCatching { waitForEngravedScore() }.onFailure { throw AssertionError("the pitch changed on the talking score is not engraved", it) }
        assertTrue("no render for the pitch changed on the talking score (renders $renders, then ${c.renders.value})", c.renders.value > renders)
        assertScoreWorks("after the talking score", detaches)
        // Left on its side: the new width is engraved without anything else asking for a render.
        readAloud(true)
        ScreenDevice.turn(rule, sideways = true); settle()
        readAloud(false)
        runCatching { waitForEngravedScore() }.onFailure { throw AssertionError("the width of a phone turned on the talking score is not engraved", it) }
        ScreenDevice.turn(rule, sideways = false); settle()
        assertScoreWorks("after a turn on the talking score", detaches)
    }

    /**
     * Everything a finger can act on is at least 48 dp tall and wide: as it is laid out, and for the part picker and
     * Music stand above the score also as much of it as shows (nothing over the score's place may cut into them). A
     * line of the talking score that its list has scrolled half out of view is the one thing that may show less.
     */
    private fun assertTargetsAre48Dp(where: String) {
        val min = 48 * rule.activity.resources.displayMetrics.density - 0.5f
        val small = rule.onAllNodes(androidx.compose.ui.test.SemanticsMatcher.keyIsDefined(androidx.compose.ui.semantics.SemanticsActions.OnClick))
            .fetchSemanticsNodes().filter { it.size.height < min || it.size.width < min }
        assertTrue("$where: targets under 48 dp: ${small.map { "${it.config} ${it.size}" }}", small.isEmpty())
        for (tag in listOf("part-picker", "stand-enter")) {
            val shows = rule.onNodeWithTag(tag).fetchSemanticsNode().boundsInWindow
            assertTrue("$where: $tag shows ${shows.width} x ${shows.height} px of its 48 dp", shows.height >= min && shows.width >= min)
        }
    }

    /** As [theScoreSurvivesTheTalkingScore], for the music stand. */
    @Test
    fun theScoreSurvivesTheMusicStand() {
        val detaches = openAndCountDetaches()
        fun stand(on: Boolean) {
            if (on) {
                rule.onNodeWithTag("top-more").performClick()
                rule.onNodeWithTag("performance").performClick()
            } else ScreenDevice.back(rule)
            waitUntil(5_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isNotEmpty() == on }
        }
        stand(true); stand(false)
        assertScoreWorks("after the music stand", detaches)
        stand(true); turnAround(); stand(false)
        assertScoreWorks("after a turn on the music stand", detaches)
    }

    /** Opens the hymn, checks the score works, and counts how often its view leaves the window from then on. */
    private fun openAndCountDetaches(): IntArray {
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitForEngravedScore()
        assertScoreWorks("before", IntArray(1))
        val detaches = IntArray(1)
        rule.runOnUiThread {
            vm.scoreController!!.view.addOnAttachStateChangeListener(object : android.view.View.OnAttachStateChangeListener {
                override fun onViewAttachedToWindow(v: android.view.View) {}
                override fun onViewDetachedFromWindow(v: android.view.View) { detaches[0]++ }
            })
        }
        return detaches
    }

    private fun turnAround() {
        ScreenDevice.turn(rule, sideways = true); settle()
        ScreenDevice.turn(rule, sideways = false); settle()
    }

    private fun assertPlays(label: String) {
        val c = vm.scoreController!!
        rule.runOnUiThread { c.togglePlay() }
        try { waitUntil(15_000) { c.state.value.playing } }
        catch (e: AssertionError) { throw AssertionError("$label: Play did not start the music", e) }
        rule.runOnUiThread { c.togglePlay() }
        waitUntil(15_000) { !c.state.value.playing }
    }

    /** The score on screen is drawn, engraves a new zoom, takes a tap on a bar, and plays; its view never left the window. */
    private fun assertScoreWorks(label: String, detaches: IntArray) {
        val c = vm.scoreController!!
        rule.waitForIdle()
        assertEquals("$label: times the score's view left the window", 0, detaches[0])
        var attached = false
        rule.runOnUiThread { attached = c.view.isAttachedToWindow && c.view.width > 0 }
        assertTrue("$label: the score's view is on screen", attached)
        var ink = 0.0
        runCatching { waitUntil(5_000) { ink = inkShare(rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap()); ink >= MIN_INK } }
        assertTrue("$label: no notation on screen (ink ${"%.4f".format(ink)})", ink >= MIN_INK)

        // Engraved again at another zoom, and back.
        val renders = c.renders.value
        val zoom = c.state.value.zoom
        rule.runOnUiThread { c.setZoom(zoom + 10) }
        runCatching { waitForEngravedScore() }.onFailure { throw AssertionError("$label: not engraved again at a new zoom", it) }
        assertTrue("$label: no new render at a new zoom (renders $renders, then ${c.renders.value})", c.renders.value > renders)
        rule.runOnUiThread { c.setZoom(zoom) }
        runCatching { waitForEngravedScore() }.onFailure { throw AssertionError("$label: not engraved again at its zoom", it) }
        ink = inkShare(rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap())
        assertTrue("$label: no notation on screen after a new render (ink ${"%.4f".format(ink)})", ink >= MIN_INK)

        // A tap on a bar's first note puts the cursor there (on bar 3, or bar 4 when it is already at bar 3).
        var at: androidx.compose.ui.geometry.Offset? = null
        var start = -1.0
        var target = 0
        rule.runOnUiThread {
            val systems = c.view.api.boundsLookup?.staffSystems ?: return@runOnUiThread
            val beat = (0 until systems.length.toInt()).flatMap { i -> val b = systems[i].bars; (0 until b.length.toInt()).map { b[it] } }
                .filter { it.index.toInt() in 2..3 }.map { it.bars[0].beats[0] }
                .firstOrNull { kotlin.math.abs(it.beat.absolutePlaybackStart - c.view.api.tickPosition) > TICK_SLACK } ?: return@runOnUiThread
            target = beat.beat.voice.bar.index.toInt() + 1
            start = beat.beat.absolutePlaybackStart
            val f = c.view.resources.displayMetrics.density
            val b = beat.visualBounds
            val sp = IntArray(2).also { surface(c).getLocationInWindow(it) }
            val vp = IntArray(2).also { c.view.getLocationInWindow(it) }
            at = androidx.compose.ui.geometry.Offset((sp[0] - vp[0] + (b.x + b.w / 2) * f).toFloat(), (sp[1] - vp[1] + (b.y + b.h / 2) * f).toFloat())
        }
        val tap = checkNotNull(at) { "$label: bars 3 and 4 are not in the engraving" }
        rule.onNodeWithTag("score-view").performTouchInput { click(tap) }
        try { waitUntil(5_000) { kotlin.math.abs(c.view.api.tickPosition - start) <= TICK_SLACK } }
        catch (e: AssertionError) { throw AssertionError("$label: a tap on bar $target left the cursor at tick ${c.view.api.tickPosition}, not $start", e) }

        assertPlays(label)
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
        /** A tap puts the player at the beat's start or a tick after it. */
        const val TICK_SLACK = 2.0
    }
}
