package no.brasscribe.play

import android.app.UiAutomation
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * A phone on its side keeps the score in view: at 100 % and 200 % text the score view has at least 55 %
 * of the height inside the system bars and shows notation, and the controls under it keep 48 dp targets.
 * Screenshots go to the app's files, score-landscape/ (pulled into docs/screenshots/score-landscape).
 */
@RunWith(AndroidJUnit4::class)
class ScoreLandscapeTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]

    @Before
    fun setUp() {
        (rule.activity.application as PlayApplication).container.firstRunDone = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @After
    fun tearDown() {
        shell("settings put system font_scale 1.0")
        instrumentation.uiAutomation.setRotation(UiAutomation.ROTATION_FREEZE_0)
    }

    private fun shell(cmd: String) {
        instrumentation.uiAutomation.executeShellCommand(cmd).close()
        Thread.sleep(300)
    }

    private fun openScore() {
        val xml = instrumentation.context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        rule.waitUntil(20_000) { vm.scoreController?.state?.value?.loaded == true }
    }

    private fun check(label: String, fontScale: String) {
        shell("settings put system font_scale $fontScale")
        instrumentation.uiAutomation.setRotation(UiAutomation.ROTATION_FREEZE_90)
        rule.waitUntil(10_000) { rule.activity.resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE }
        rule.waitUntil(10_000) { rule.activity.resources.configuration.fontScale.toString().startsWith(fontScale.take(3)) }
        openScore()
        rule.waitUntil(20_000) { (vm.scoreController?.renders?.value ?: 0) > 0 && rule.onAllNodesWithTag("score-controls").fetchSemanticsNodes().isNotEmpty() }
        rule.waitForIdle()
        Thread.sleep(800)

        var available = 0
        rule.runOnUiThread {
            val decor = rule.activity.window.decorView
            val bars = ViewCompat.getRootWindowInsets(decor)!!.getInsets(WindowInsetsCompat.Type.systemBars())
            available = decor.height - bars.top - bars.bottom
        }
        val density = rule.activity.resources.displayMetrics.density
        val score = rule.onNodeWithTag("score-view").getBoundsInRoot()
        val scoreHeight = (score.bottom - score.top).value * density
        val share = scoreHeight / available

        val dir = File(rule.activity.getExternalFilesDir(null), "score-landscape").apply { mkdirs() }
        instrumentation.uiAutomation.takeScreenshot()?.let { b -> File(dir, "$label.png").outputStream().use { b.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        assertTrue("$label: the score has ${"%.0f".format(share * 100)} % of $available px", share >= 0.55f)

        val bmp = rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap()
        val ink = inkShare(bmp)
        assertTrue("$label: no notation on screen (ink ${"%.4f".format(ink)})", ink >= 0.005)

        // Every control under the score shows whole, at 48 dp or more (Play is 56 dp): nothing cut off at the edge.
        val controls = rule.onAllNodes(hasClickAction() and hasAnyAncestor(hasTestTag("score-controls"))).fetchSemanticsNodes()
            .filter { it.layoutInfo.isPlaced }
        assertTrue("$label: no controls", controls.size >= 4)
        for (n in controls) {
            val h = n.boundsInRoot.height / density
            assertTrue("$label: a control shows $h dp of its height (${n.config})", h >= 47.5f)
        }
        // The music stand is one tap away: in the row, or under More when the row has no room for it.
        if (rule.onAllNodesWithTag("stand-enter").fetchSemanticsNodes().none { it.layoutInfo.isPlaced }) {
            rule.onNodeWithTag("controls-more").performClick()
            rule.waitUntil(5_000) { rule.onAllNodesWithText("Music stand").fetchSemanticsNodes().isNotEmpty() }
            Thread.sleep(400)
            instrumentation.uiAutomation.takeScreenshot()?.let { b -> File(dir, "$label-more.png").outputStream().use { b.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        }
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
    fun landscapeAt100PercentText() = check("landscape-100", "1.0")

    @Test
    fun landscapeAt200PercentText() = check("landscape-200", "2.0")
}
