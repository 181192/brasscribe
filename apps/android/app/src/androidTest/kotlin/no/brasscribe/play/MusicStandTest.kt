package no.brasscribe.play

import android.app.UiAutomation
import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performKeyInput
import androidx.compose.ui.test.pressKey
import androidx.compose.ui.test.requestFocus
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The music stand (design/music-stand.md) on "Old Hundredth" (apps/fixtures/old-hundredth, in the test
 * APK only), opened straight from its MusicXML: a turn keeps the music playing and the place, the
 * controls stay while assistive tech or a keyboard is in use, and the keys turn pages. Assistive tech
 * is simulated with AppContainer.assistiveOverride (a real TalkBack cannot be switched on from a test).
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class MusicStandTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val container get() = (rule.activity.application as PlayApplication).container
    private val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]

    @Before
    fun setUp() {
        rule.enableAccessibilityChecks()
        rule.activity.getSharedPreferences("engine", 0).edit().clear().commit()
        container.firstRunDone = true
        container.standFollow = true
        container.standKeepControls = false
        container.standOnTurn = false
        container.standHintShown = true
        container.assistiveOverride = false
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @After
    fun tearDown() {
        container.assistiveOverride = null
        runCatching { vm.scoreController?.let { c -> if (c.state.value.playing) rule.runOnUiThread { c.togglePlay() } } }
        instrumentation.uiAutomation.setRotation(UiAutomation.ROTATION_FREEZE_0)
        instrumentation.setInTouchMode(true)
    }

    /** Opens the fixture score as a MusicXML file (no transcription), and waits for alphaTab to lay it out. */
    private fun openScore() {
        val xml = instrumentation.context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        rule.waitUntil(20_000) { rule.onAllNodesWithTag("stand-enter").fetchSemanticsNodes().isNotEmpty() }
        rule.waitUntil(20_000) { vm.scoreController?.state?.value?.loaded == true }
    }

    private fun controllerState() = vm.scoreController!!.state.value

    /** Opens the stand; at [zoom] % the twelve bars of the hymn make [minPages] pages or more. */
    private fun openStand(zoom: Int = 100, minPages: Int = 1) {
        if (zoom != 100) rule.runOnUiThread { vm.scoreController!!.setZoom(zoom) }
        rule.onNodeWithTag("stand-enter").performClick()
        waitForPages(minPages)
    }

    private fun waitForPages(minPages: Int = 1) {
        try {
            rule.waitUntil(20_000) { positionText()?.contains(Regex("""(?:pages?|side) \d+(?:–\d+)? (?:of|av) (\d+)""")) == true && pageCount() >= minPages }
        } catch (e: Throwable) {
            saveScreenshot("failed-pages")
            throw AssertionError("fewer than $minPages pages: '${positionText()}'", e)
        }
    }

    private fun saveScreenshot(name: String) {
        val dir = File(rule.activity.getExternalFilesDir(null), "stand-shots").apply { mkdirs() }
        val bmp = instrumentation.uiAutomation.takeScreenshot() ?: return
        File(dir, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun positionText(): String? = rule.onAllNodes(hasTestTag("stand-position"), useUnmergedTree = false).fetchSemanticsNodes()
        .firstOrNull()?.let { n -> n.config.getOrNull(SemanticsProperties.Text)?.joinToString(" ") { it.text } }

    private fun page() = Regex("""(?:pages?|side) (\d+)(?:–\d+)? (?:of|av)""").find(positionText().orEmpty())?.groupValues?.get(1)?.toInt() ?: -1
    private fun pageCount() = Regex("""(?:of|av) (\d+)$""").find(positionText().orEmpty())?.groupValues?.get(1)?.toInt()
        ?: Regex("""(?:pages?|side) \d+(?:–\d+)? (?:of|av) (\d+)""").find(positionText().orEmpty())?.groupValues?.get(1)?.toInt() ?: -1

    private fun play() {
        rule.runOnUiThread { vm.scoreController!!.togglePlay() }
        rule.waitUntil(15_000) { controllerState().playing }
    }

    private fun layerShown() = rule.onAllNodesWithTag("stand-layer").fetchSemanticsNodes().isNotEmpty()

    /** Paused, the layer shows and stays; every control is a large, labelled target. (Playing: MusicStandPlaybackTest.) */
    @Test
    fun theLayerIsLargeLabelledAndStaysWhilePaused() {
        openScore()
        openStand()
        assertTrue(layerShown())
        rule.onNodeWithTag("play").assertHeightIsAtLeast(56.dp)
        for (tag in listOf("stand-prev-page", "stand-next-page", "stand-slower", "stand-faster", "stand-repeat", "stand-only-mine", "stand-lock", "performance-exit")) {
            rule.onNodeWithTag(tag).assertHeightIsAtLeast(48.dp)
        }
        rule.onNodeWithContentDescription("Leave the music stand").assertExists()
        rule.onRoot().tryPerformAccessibilityChecks()
        rule.mainClock.advanceTimeBy(6_000)
        assertTrue("paused: the layer stays", layerShown())
        // The stand's speed steppers: 5 % a step.
        rule.onNodeWithTag("stand-slower").performClick()
        rule.waitUntil(2_000) { controllerState().speed == 95 }
    }

    @Test
    fun pageKeysTurnPagesSpacePlaysEscLeaves() {
        openScore()
        openStand(zoom = 400, minPages = 3)
        instrumentation.setInTouchMode(false)
        rule.waitForIdle()
        val score = rule.onNodeWithTag("stand-score")
        score.requestFocus()
        assertEquals(1, page())
        val count = pageCount()
        assertTrue("pages: $count", count >= 3)

        score.performKeyInput { pressKey(Key.PageDown) }
        rule.waitUntil(3_000) { page() == 2 }
        // The turn is announced; a quiet live region, nothing drawn over the music.
        rule.waitUntil(3_000) {
            rule.onAllNodes(hasContentDescription("Page 2 of $count, bars", substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
        }
        score.performKeyInput { pressKey(Key.DirectionRight) }
        rule.waitUntil(3_000) { page() == 3 }
        score.performKeyInput { pressKey(Key.DirectionUp) }
        rule.waitUntil(3_000) { page() == 2 }
        score.performKeyInput { pressKey(Key.PageUp) }
        rule.waitUntil(3_000) { page() == 1 }
        score.performKeyInput { pressKey(Key.MoveEnd) }
        rule.waitUntil(3_000) { page() == count }
        score.performKeyInput { pressKey(Key.MoveHome) }
        rule.waitUntil(3_000) { page() == 1 }
        // The page buttons and the TalkBack actions do the same.
        rule.onNodeWithTag("stand-next-page").performClick()
        rule.waitUntil(3_000) { page() == 2 }
        val actions = rule.onNodeWithTag("stand-score").fetchSemanticsNode().config.getOrNull(SemanticsActions.CustomActions).orEmpty()
        for (a in listOf("Next page", "Previous page", "Next bar", "Previous bar", "Play this bar")) assertNotNull(a, actions.firstOrNull { it.label == a })
        rule.runOnUiThread { actions.first { it.label == "Previous page" }.action() }
        rule.waitUntil(3_000) { page() == 1 }

        // Space plays and pauses.
        rule.onNodeWithTag("stand-score").requestFocus()
        rule.onNodeWithTag("stand-score").performKeyInput { pressKey(Key.Spacebar) }
        rule.waitUntil(10_000) { controllerState().playing }
        rule.onNodeWithTag("stand-score").performKeyInput { pressKey(Key.Spacebar) }
        rule.waitUntil(10_000) { !controllerState().playing }

        // Esc leaves; the focus goes back to the Music stand button, and it is said.
        rule.onNodeWithTag("stand-score").performKeyInput { pressKey(Key.Escape) }
        rule.waitUntil(3_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isEmpty() }
        rule.waitUntil(3_000) { rule.onAllNodes(hasContentDescription("Music stand closed."), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("stand-enter").assertIsFocused()
        rule.onNodeWithContentDescription("Share or print").assertExists()

        // F opens it again, and says so.
        rule.onNodeWithTag("stand-enter").performKeyInput { pressKey(Key.F) }
        rule.waitUntil(3_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isNotEmpty() }
        rule.waitUntil(3_000) {
            rule.onAllNodes(hasContentDescription("Music stand. Solo Cornet (you), bar ", substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
        }
    }

    @Test
    fun backLeavesTheLockIsReleasedAndOnlyMyPartToggles() {
        openScore()
        // The View menu still has it, with the old test tag.
        rule.onNodeWithContentDescription("More").performClick()
        rule.onNodeWithTag("performance").performClick()
        waitForPages()
        assertTrue(positionText().orEmpty(), positionText().orEmpty().startsWith("Solo Cornet (you)"))
        assertEquals(setOf(1), controllerState().shown)

        // Only my part off goes back to every part (the score opened on your part alone).
        rule.onNodeWithTag("stand-only-mine").performClick()
        rule.waitUntil(5_000) { controllerState().shown.size > 1 }
        rule.waitUntil(5_000) { positionText().orEmpty().startsWith("All parts") }
        rule.onNodeWithTag("stand-only-mine").performClick()
        rule.waitUntil(5_000) { controllerState().shown.size == 1 }

        // Lock rotation locks this way up, and says so; leaving gives the rotation back to the system.
        rule.onNodeWithTag("stand-lock").performClick()
        rule.waitForIdle()
        assertEquals(ActivityInfo.SCREEN_ORIENTATION_LOCKED, rule.activity.requestedOrientation)
        rule.onNodeWithText("Rotation locked").assertExists()
        rule.waitUntil(3_000) { rule.onAllNodes(hasContentDescription("Rotation locked. The music stays this way up."), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        instrumentation.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        rule.waitUntil(3_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isEmpty() }
        assertEquals(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED, rule.activity.requestedOrientation)
        rule.onNodeWithTag("stand-enter").assertExists()
    }

    @Test
    fun openOnTheMusicStandFromTheLibrary() {
        openScore()
        rule.runOnUiThread { vm.back() }
        rule.waitUntil(5_000) { rule.onAllNodesWithText("Old Hundredth", substring = true).fetchSemanticsNodes().isNotEmpty() }
        rule.onAllNodes(hasContentDescription("Options for Old Hundredth", substring = true))[0].performClick()
        rule.onNodeWithTag("open-on-stand").performClick()
        rule.waitUntil(20_000) { rule.onAllNodesWithTag("stand-score").fetchSemanticsNodes().isNotEmpty() }
        waitForPages()
        rule.onNodeWithTag("performance-exit").performClick()
        // Leaving a stand opened from the library goes back to the library.
        rule.waitUntil(5_000) {
            rule.onAllNodesWithTag("stand-enter").fetchSemanticsNodes().isEmpty() &&
                rule.onAllNodes(hasContentDescription("Options for Old Hundredth", substring = true)).fetchSemanticsNodes().isNotEmpty()
        }
        rule.waitUntil(3_000) { rule.onAllNodes(hasContentDescription("Music stand closed."), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
    }

    /**
     * Screenshots of the mockup states, saved on the device under Android/data/no.brasscribe.play/files/stand-shots/
     * (run with -e shots true; the locale is whatever the app is set to).
     */
    @Test
    fun screenshots() {
        val args = InstrumentationRegistry.getArguments()
        org.junit.Assume.assumeTrue(args.getString("shots") == "true")
        val tag = args.getString("shotsTag") ?: "en"
        val dir = File(rule.activity.getExternalFilesDir(null), "stand-shots").apply { mkdirs() }
        fun shot(name: String) {
            rule.waitForIdle()
            Thread.sleep(900)
            val bmp = instrumentation.uiAutomation.takeScreenshot()
            File(dir, "$tag-$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        openScore()
        shot("score-entry")
        // A zoom (-e zoom 200) gives the twelve bars of the hymn enough pages for a tablet's spread.
        openStand(zoom = args.getString("zoom")?.toIntOrNull() ?: 100)
        // Mid-score, as in the mockups.
        rule.runOnUiThread { vm.scoreController!!.goToBar(7) }
        Thread.sleep(800)
        shot("portrait-shown")
        rule.onNodeWithTag("stand-score").performClick()
        rule.waitUntil(3_000) { !layerShown() }
        shot("portrait-hidden")
        rule.onNodeWithTag("stand-score").performClick()
        rule.waitUntil(3_000) { layerShown() }
        instrumentation.uiAutomation.setRotation(UiAutomation.ROTATION_FREEZE_90)
        rule.waitUntil(10_000) { rule.activity.resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE }
        waitForPages()
        shot("landscape-shown")
        if (rule.onAllNodesWithTag("stand-lock").fetchSemanticsNodes().isNotEmpty()) {
            rule.onNodeWithTag("stand-lock").performClick()
            shot("landscape-locked")
            rule.onNodeWithTag("stand-lock").performClick()
        }
        rule.onNodeWithTag("stand-score").performClick()
        rule.waitUntil(3_000) { !layerShown() }
        shot("landscape-hidden")
        rule.onNodeWithTag("stand-score").performClick()
        instrumentation.uiAutomation.setRotation(UiAutomation.ROTATION_FREEZE_0)
        rule.waitUntil(10_000) { rule.activity.resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_PORTRAIT }
        // The first time the layer hides: the hint.
        rule.runOnUiThread { container.standHintShown = false }
        rule.onNodeWithTag("stand-score").performClick()
        rule.waitUntil(3_000) { !layerShown() }
        shot("portrait-hint")
        // Hold for a host-side "Turn the music" capture when asked (adb emu rotate while this waits).
        args.getString("holdMs")?.toLongOrNull()?.let { Thread.sleep(it) }
    }
}
