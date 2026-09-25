package no.brasscribe.play

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
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
    }

    private fun waitFor(matcher: SemanticsMatcher, ms: Long = 20_000) =
        rule.waitUntil(ms) { rule.onAllNodes(matcher, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }

    private fun SemanticsNode.customAction(label: String) =
        config.getOrNull(SemanticsActions.CustomActions)?.firstOrNull { it.label == label }

    @Test
    fun homeButtonsAreLargeLabelledTargets() {
        for (label in listOf("Import audio or video", "Record with the microphone", "Record sound playing on this phone", "Open the Mikkel sample")) {
            rule.onNodeWithText(label).assertHeightIsAtLeast(48.dp)
        }
        rule.onNode(isHeading() and hasText("Companion engine")).assertExists()
        rule.onRoot().tryPerformAccessibilityChecks()
    }

    @Test
    fun sampleFlowFromWhatIsThisToScore() {
        rule.onNodeWithText("Open the Mikkel sample").performClick()

        // What is this? Four radio options, Continue disabled until one is chosen.
        rule.onNode(isHeading() and hasText("What is this?")).assertExists()
        rule.onNodeWithText("Continue").assertIsNotEnabled()
        val option = rule.onNode(hasText("Orchestra with soloist", substring = false) and
            SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton), useUnmergedTree = false)
        option.performClick()
        option.assertIsSelected()
        val info = option.fetchSemanticsNode().config.getOrNull(SemanticsProperties.CollectionItemInfo)
        assertEquals(2, info?.rowIndex)
        rule.onNodeWithText("Continue").assertIsEnabled().performClick()

        // Transcribing: a progress bar with range info and a label.
        waitFor(hasContentDescription("Transcription progress"))
        val bar = rule.onNode(hasContentDescription("Transcription progress"), useUnmergedTree = true).fetchSemanticsNode()
        assertTrue(bar.config.contains(SemanticsProperties.ProgressBarRangeInfo))
        rule.onNodeWithText("Cancel").assertExists()

        // Review: the golden solo has uncertain notes, each announced with its uncertainty.
        waitFor(isHeading() and hasText("Check the transcription"), 60_000)
        val uncertain = rule.onAllNodes(SemanticsMatcher("announces uncertain") { n ->
            n.config.getOrNull(SemanticsProperties.ContentDescription)?.any { it.endsWith(", uncertain") } == true
        }).fetchSemanticsNodes()
        assertTrue("uncertain notes are announced", uncertain.isNotEmpty())
        val first = uncertain.first()
        val text = first.config[SemanticsProperties.ContentDescription].first()
        // In free time (ad lib.) the position is the performed time, otherwise the beat.
        assertTrue(text, Regex("""(bar \d+, )?(beat \d|at \d+ (seconds|minutes?)).*: [A-G][^,]* \d, [^,]*note.*, uncertain$""").containsMatchIn(text))
        // Only the first note of a free-time region announces it.
        val adLib = rule.onAllNodes(SemanticsMatcher("ad lib entry") { n ->
            n.config.getOrNull(SemanticsProperties.ContentDescription)?.any { it.contains("Ad lib, free time") } == true
        }).fetchSemanticsNodes().size
        assertTrue("ad lib entries: $adLib", adLib <= 1)
        assertTrue(first.customAction("Listen to this bar") != null)
        assertTrue(first.customAction("Next uncertain note") != null)
        rule.runOnUiThread { first.customAction("Mark as checked")!!.action() }
        rule.waitUntil(5_000) { rule.onAllNodesWithText("Checked.", substring = true).fetchSemanticsNodes().isNotEmpty() }

        // Output, then the score with bar and part navigation as custom actions.
        rule.onNodeWithText("Choose output").performClick()
        rule.onNode(isHeading() and hasText("Choose output")).assertExists()
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

    @Test
    fun exportListsFormatsAndExplainsBraille() {
        rule.onNodeWithText("Open the Mikkel sample").performClick()
        rule.onNodeWithText("Orchestra with soloist").performClick()
        rule.onNodeWithText("Continue").performClick()
        waitFor(isHeading() and hasText("Check the transcription"), 60_000)
        rule.onNodeWithText("Choose output").performClick()
        rule.onNodeWithText("Show the score").performClick()
        waitFor(hasText("Export"))
        rule.onNodeWithText("Export").performClick()
        for (f in listOf("MusicXML, full score", "PDF", "MIDI", "Audio (MP3)", "Talking score (text)", "Braille music (BRF)")) {
            rule.onNode(isHeading() and hasText(f)).assertExists()
        }
        rule.onNodeWithText("Needs braille export in the engine.", substring = true).assertExists()

        // Share builds each file (MusicXML, PDF, alphaTab MIDI, talking-score HTML), then opens the chooser.
        val exports = rule.activity.cacheDir.resolve("exports")
        for ((i, ext) in listOf(0 to "musicxml", 1 to "pdf", 2 to "mid", 4 to "html")) {
            rule.onAllNodesWithText("Share")[i].performClick()
            rule.waitUntil(15_000) { exports.listFiles().orEmpty().any { it.extension == ext && it.length() > 0 } }
            Thread.sleep(1500)
            androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().uiAutomation
                .performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
            rule.waitForIdle()
        }
        val midi = exports.listFiles()!!.first { it.extension == "mid" }.readBytes()
        assertEquals("MThd", String(midi, 0, 4))
        val html = exports.listFiles()!!.first { it.extension == "html" }.readText()
        assertTrue(html.contains("<h2>Solo Cornet</h2>") && html.contains("<h3>Bar 2</h3>") && html.contains(", uncertain</li>"))
        rule.onNodeWithText("Exported", substring = true).assertExists()
    }
}
