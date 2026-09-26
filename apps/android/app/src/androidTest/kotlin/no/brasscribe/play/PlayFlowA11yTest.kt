package no.brasscribe.play

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.unit.dp
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.accessibility.AccessibilityChecks
import androidx.test.espresso.action.ViewActions
import androidx.test.espresso.matcher.ViewMatchers.isRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Walks the main flow on the built-in sample engine (debug builds carry the golden Mikkel output) with
 * Compose accessibility checks (ATF) on every action, and asserts the semantics TalkBack depends on:
 * headings, radio roles with collection positions, progress range info, the per-note announcements with
 * their custom actions, and bar navigation on the score.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class PlayFlowA11yTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    @Before
    fun setUp() {
        rule.enableAccessibilityChecks()
        rule.activity.getSharedPreferences("engine", 0).edit().clear().commit()
        // A fresh install opens on the first-run screen once.
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    private fun waitFor(matcher: SemanticsMatcher, ms: Long = 20_000) =
        rule.waitUntil(ms) { rule.onAllNodes(matcher, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }

    private fun SemanticsNode.customAction(label: String) =
        config.getOrNull(SemanticsActions.CustomActions)?.firstOrNull { it.label == label }

    @Test
    fun homeButtonsAreLargeLabelledTargets() {
        for (label in listOf("Open a recording", "Record with the microphone", "Record what's playing", "Try the demo")) {
            val h = rule.onNodeWithText(label).fetchSemanticsNode().boundsInRoot.height / rule.density.density
            assertTrue("$label is $h dp", h >= 48f)
        }
        rule.onNode(isHeading() and hasText("Turn a recording into", substring = true)).assertExists()
        rule.onNodeWithContentDescription("Settings").assertHeightIsAtLeast(48.dp)
        rule.onRoot().tryPerformAccessibilityChecks()
    }

    @Test
    fun sampleFlowFromWhatIsThisToScore() {
        rule.onNodeWithText("Try the demo").performClick()

        // What is this? Four radio options, Continue disabled until one is chosen.
        rule.onNode(isHeading() and hasText("What is this?")).assertExists()
        rule.onNodeWithText("Continue").assertIsNotEnabled()
        val option = rule.onNode(hasText("Soloist with orchestra or band", substring = false) and
            SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton), useUnmergedTree = false)
        option.performClick()
        option.assertIsSelected()
        val info = option.fetchSemanticsNode().config.getOrNull(SemanticsProperties.CollectionItemInfo)
        assertEquals(2, info?.rowIndex)
        rule.onNodeWithText("Continue").assertIsEnabled().performClick()

        // Transcribing: a progress bar with range info and a label.
        waitFor(hasContentDescription("Progress"))
        val bar = rule.onNode(hasContentDescription("Progress"), useUnmergedTree = true).fetchSemanticsNode()
        assertTrue(bar.config.contains(SemanticsProperties.ProgressBarRangeInfo))
        rule.onNodeWithText("Cancel").assertExists()

        // Review: the golden solo has uncertain notes, each announced with its uncertainty.
        waitFor(isHeading() and hasText("Check ", substring = true), 60_000)
        val uncertain = rule.onAllNodes(SemanticsMatcher("announces uncertain") { n ->
            n.config.getOrNull(SemanticsProperties.ContentDescription)?.any { it.contains(", uncertain") } == true
        }).fetchSemanticsNodes()
        assertTrue("uncertain notes are announced", uncertain.isNotEmpty())
        val first = uncertain.first()
        val text = first.config[SemanticsProperties.ContentDescription].first()
        // In free time (ad lib.) the position is the performed time, otherwise the beat.
        assertTrue(text, Regex("""(bar \d+, )?(beat \d|at \d+ (seconds|minutes?)).*: [A-G][^,]* \d, [^,]*note.*, uncertain""").containsMatchIn(text))
        // Only the first note of a free-time region announces it.
        val adLib = rule.onAllNodes(SemanticsMatcher("ad lib entry") { n ->
            n.config.getOrNull(SemanticsProperties.ContentDescription)?.any { it.contains("Ad lib, free time") } == true
        }).fetchSemanticsNodes().size
        assertTrue("ad lib entries: $adLib", adLib <= 1)
        assertTrue(first.customAction("Listen to this bar") != null)
        assertTrue(first.customAction("Next uncertain note") != null)
        rule.runOnUiThread { first.customAction("Keep")!!.action() }
        rule.waitUntil(5_000) { rule.onAllNodesWithText("Kept.", substring = true).fetchSemanticsNodes().isNotEmpty() }

        // Finish later asks first; then Output, then the score with bar and part navigation as custom actions.
        rule.onNodeWithText("Finish later (", substring = true).assertHeightIsAtLeast(48.dp).performClick()
        rule.onNodeWithText("Finish later").performClick()
        rule.onNode(isHeading() and hasText("How should the score be?")).assertExists()
        rule.onNodeWithText("Show the score").performClick()
        waitFor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "score-view"))
        rule.waitUntil(20_000) {
            rule.onNodeWithTag("score-view").fetchSemanticsNode().config.getOrNull(SemanticsProperties.ContentDescription)
                ?.firstOrNull()?.let { Regex("""Bar 1 of \d+""").containsMatchIn(it) && !it.contains("of 1.") } == true
        }
        val score = rule.onNodeWithTag("score-view").fetchSemanticsNode()
        val summary = score.config[SemanticsProperties.ContentDescription].first()
        assertTrue(summary, summary.startsWith("Score of Mikkel") && summary.contains("Solo Cornet"))
        for (a in listOf("Next bar", "Previous bar", "Next part", "Previous part", "Play this bar")) {
            assertTrue("custom action $a", score.customAction(a) != null)
        }
        rule.runOnUiThread { assertTrue(score.customAction("Next bar")!!.action()) }
        rule.waitForIdle()
        val texts = rule.onAllNodes(SemanticsMatcher("any text") { it.config.contains(SemanticsProperties.Text) })
            .fetchSemanticsNodes().flatMap { it.config[SemanticsProperties.Text].map { t -> t.text } }
        assertTrue("after Next bar: $texts", texts.any { it.startsWith("Bar 2") })
        rule.onNodeWithTag("play").assertHeightIsAtLeast(48.dp)

        // The AlphaTabView is a classic View: run the Espresso (ATF) view checks over the whole window too.
        AccessibilityChecks.enable().setRunChecksFromRootView(true)
        onView(isRoot()).perform(ViewActions.closeSoftKeyboard())
    }

    /** Full screen on a music stand: the score alone, with only the transport left. */
    @Test
    fun fullScreenLeavesOnlyTheScoreAndTheTransport() {
        rule.onNodeWithText("Try the demo").performClick()
        rule.onNodeWithText("Soloist with orchestra or band").performClick()
        rule.onNodeWithText("Continue").performClick()
        waitFor(isHeading() and hasText("Check ", substring = true), 60_000)
        rule.onNodeWithText("Finish later (", substring = true).performClick()
        rule.onNodeWithText("Finish later").performClick()
        rule.onNodeWithText("Show the score").performClick()
        waitFor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "score-view"))

        rule.onNodeWithContentDescription("More").performClick()
        rule.onNodeWithTag("performance").performClick()
        rule.waitForIdle()

        // The score and the transport stay; every other control goes.
        rule.onNodeWithTag("score-view").assertExists()
        rule.onNodeWithTag("play").assertExists().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithTag("performance-exit").assertExists().assertHeightIsAtLeast(48.dp)
        for (gone in listOf("Read aloud", "Metronome", "Count-in", "Mute my part", "Speed 100%")) {
            rule.onAllNodesWithText(gone).assertCountEquals(0)
        }
        rule.onRoot().tryPerformAccessibilityChecks()

        rule.onNodeWithTag("performance-exit").performClick()
        rule.waitForIdle()
        rule.onNodeWithContentDescription("Share or print").assertExists()
        rule.onNodeWithTag("score-view").assertExists()
    }

    @Test
    fun exportsEveryFormatIncludingBraille() {
        rule.onNodeWithText("Try the demo").performClick()
        rule.onNodeWithText("Soloist with orchestra or band").performClick()
        rule.onNodeWithText("Continue").performClick()
        waitFor(isHeading() and hasText("Check ", substring = true), 60_000)
        rule.onNodeWithText("Finish later (", substring = true).performClick()
        rule.onNodeWithText("Finish later").performClick()
        rule.onNodeWithText("Show the score").performClick()
        waitFor(hasContentDescription("Share or print"))
        rule.onNodeWithContentDescription("Share or print").performClick()
        rule.onNode(isHeading() and hasText("Share or print")).assertExists()
        // My part and PDF are the default (print your own part): that makes the Solo Cornet's PDF.
        rule.onNode(hasText("Solo Cornet (you)") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).assertIsSelected()
        val exports = rule.activity.cacheDir.resolve("exports")
        exports.deleteRecursively()
        rule.onNodeWithTag("share").performClick()
        rule.waitUntil(20_000) { exports.listFiles().orEmpty().any { it.extension == "pdf" && it.name.contains("Solo Cornet") && it.length() > 0 } }
        val part = exports.listFiles()!!.first { it.extension == "pdf" }
        assertEquals("%PDF", String(part.readBytes(), 0, 4))
        Thread.sleep(1500)
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().uiAutomation
            .performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        rule.waitForIdle()
        exports.deleteRecursively()
        // The conductor's score, with the other formats.
        rule.onNode(hasText("Conductor's score") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).performClick()
        rule.onNode(hasText("PDF") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Checkbox)).assertExists()
        for (f in listOf("MusicXML", "MIDI", "Talking score", "Braille music")) {
            rule.onNode(hasText(f) and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Checkbox)).performScrollTo().performClick()
        }
        rule.onNodeWithText("Print").assertHeightIsAtLeast(48.dp)

        // One Share builds every chosen file (MusicXML, PDF, alphaTab MIDI, talking-score HTML, BRF), then opens the chooser.
        rule.onNodeWithTag("share").performClick()
        for (ext in listOf("musicxml", "pdf", "mid", "html", "brf")) {
            runCatching { rule.waitUntil(20_000) { exports.listFiles().orEmpty().any { it.extension == ext && it.length() > 0 } } }.onFailure {
                throw AssertionError("no .$ext; files ${exports.listFiles().orEmpty().map { f -> f.name }}", it)
            }
        }
        Thread.sleep(1500)
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().uiAutomation
            .performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        rule.waitForIdle()
        val midi = exports.listFiles()!!.first { it.extension == "mid" }.readBytes()
        assertEquals("MThd", String(midi, 0, 4))
        val html = exports.listFiles()!!.first { it.extension == "html" }.readText()
        // The core's talking score of the arranged score: every part, one line per event.
        assertTrue(html.contains("Solo Cornet") && html.contains("Solo Horn") && html.contains("uncertain"))
        val brf = exports.listFiles()!!.first { it.extension == "brf" }.readText()
        // North American Braille ASCII with CRLF lines; the music lines fit 40 cells (the title may not).
        val lines = brf.split("\r\n")
        assertTrue("BRF", brf.length > 1000 && lines.size > 50 && lines.count { it.length <= 40 } >= lines.size * 9 / 10)
    }
}
