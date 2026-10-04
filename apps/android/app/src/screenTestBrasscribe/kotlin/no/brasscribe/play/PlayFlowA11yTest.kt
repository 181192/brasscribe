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
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performKeyInput
import androidx.compose.ui.test.requestFocus
import androidx.compose.ui.test.pressKey
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.unit.dp
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.accessibility.AccessibilityChecks
import androidx.test.espresso.action.ViewActions
import androidx.test.espresso.matcher.ViewMatchers.isRoot
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.engine.FixtureSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith

/**
 * Walks the main flow on a fixture engine that serves "Old Hundredth" (apps/fixtures/old-hundredth, a
 * public-domain hymn arranged by the core) with
 * Compose accessibility checks (ATF) on every action, and asserts the semantics TalkBack depends on:
 * headings, radio roles with collection positions, progress range info, the per-note announcements with
 * their custom actions, and bar navigation on the score.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class PlayFlowA11yTest : ScreenTest() {
    @Before
    fun setUp() {
        // A fresh install opens on the first-run screen once, and Get started asks "What do you play?" next.
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
    }

    /**
     * Opens a source straight onto What is this?, with the fixture engine standing in for a paired
     * computer: the file picker can't be driven from a test.
     */
    private fun openOldHundredth() {
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
        }
        rule.waitForIdle()
    }

    /** Whether the fixture has an engine file (the PDF, MP3 and braille are engine renders it may lack). */
    private fun fixtureHas(name: String) =
        ScreenDevice.fixture("old-hundredth/$name") != null

    private fun waitFor(matcher: SemanticsMatcher, ms: Long = 20_000) =
        waitUntil(ms) { rule.onAllNodes(matcher, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }

    private fun SemanticsNode.customAction(label: String) =
        config.getOrNull(SemanticsActions.CustomActions)?.firstOrNull { it.label == label }

    @Test
    fun homeButtonsAreLargeLabelledTargets() {
        for (label in listOf("Open a recording", "Record with the microphone", "Record what's playing", "Open a score")) {
            val h = rule.onNodeWithText(label).fetchSemanticsNode().boundsInRoot.height / rule.density.density
            assertTrue("$label is $h dp", h >= 48f)
        }
        rule.onNode(isHeading() and hasText("Turn a recording into", substring = true)).assertExists()
        rule.onNodeWithContentDescription("Settings").assertHeightIsAtLeast(48.dp)
        checkAccessibility()
    }

    @Test
    fun flowFromWhatIsThisToScore() {
        openOldHundredth()

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

        // Review: the fixture's solo has uncertain notes, each announced with its uncertainty.
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
        waitUntil(5_000) { rule.onAllNodesWithText("Kept.", substring = true).fetchSemanticsNodes().isNotEmpty() }

        // Finish later asks first; then Output, then the score with bar and part navigation as custom actions.
        rule.onNodeWithText("Finish later (", substring = true).assertHeightIsAtLeast(48.dp).performClick()
        rule.onNodeWithText("Finish later").performClick()
        rule.onNode(isHeading() and hasText("How should the score be?")).assertExists()
        rule.onNodeWithText("Show the score").performClick()
        waitFor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "score-view"))
        waitUntil(20_000) {
            rule.onNodeWithTag("score-view").fetchSemanticsNode().config.getOrNull(SemanticsProperties.ContentDescription)
                ?.firstOrNull()?.let { Regex("""Bar 1 of \d+""").containsMatchIn(it) && !it.contains("of 1.") } == true
        }
        val score = rule.onNodeWithTag("score-view").fetchSemanticsNode()
        val summary = score.config[SemanticsProperties.ContentDescription].first()
        // The title keeps its words together (no-break spaces).
        assertTrue(summary, summary.replace('\u00A0', ' ').startsWith("Score of Old Hundredth") && summary.contains("Solo Cornet"))
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

    /**
     * Show the score is docked on its own band: the key buttons scroll fully clear of it, so no
     * control (and no focused one) is hidden behind the button (WCAG 2.4.11).
     */
    @Test
    fun showScoreBandLeavesTheKeyButtonsClear() {
        openOldHundredth()
        rule.onNodeWithText("Soloist with orchestra or band").performClick()
        rule.onNodeWithText("Continue").performClick()
        waitFor(isHeading() and hasText("Check ", substring = true), 60_000)
        rule.onNodeWithText("Finish later (", substring = true).performClick()
        rule.onNodeWithText("Finish later").performClick()
        rule.onNode(isHeading() and hasText("How should the score be?")).assertExists()
        val show = rule.onNodeWithText("Show the score").fetchSemanticsNode().boundsInRoot
        for (label in listOf("− Lower", "Higher +")) {
            rule.onNodeWithText(label).performScrollTo()
            val b = rule.onNodeWithText(label).fetchSemanticsNode().boundsInRoot
            assertTrue("$label ends at ${b.bottom}, the button band starts above ${show.top}", b.bottom <= show.top)
        }
    }

    /** The music stand from the View menu: the score alone, the stand's controls, and none of the practice chrome. */
    @Test
    fun fullScreenLeavesOnlyTheScoreAndTheTransport() {
        openOldHundredth()
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

        // The score, the stand's layer (paused, so it shows) and Leave stay; the toolbar and the practice chips go.
        rule.onNodeWithTag("score-view").assertExists()
        rule.onNodeWithTag("stand-score").assertExists()
        rule.onNodeWithTag("play").assertExists().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithTag("performance-exit").assertExists().assertHeightIsAtLeast(48.dp)
        for (gone in listOf("Read aloud", "Metronome", "Count-in", "Mute my part", "As written", "Concert")) {
            rule.onAllNodesWithText(gone).assertCountEquals(0)
        }
        checkAccessibility()

        rule.onNodeWithTag("performance-exit").performClick()
        rule.waitForIdle()
        rule.onNodeWithContentDescription("Share or print").assertExists()
        rule.onNodeWithTag("score-view").assertExists()
    }

    @Test
    fun exportsEveryFormatIncludingBraille() {
        openOldHundredth()
        rule.onNodeWithText("Soloist with orchestra or band").performClick()
        rule.onNodeWithText("Continue").performClick()
        waitFor(isHeading() and hasText("Check ", substring = true), 60_000)
        rule.onNodeWithText("Finish later (", substring = true).performClick()
        rule.onNodeWithText("Finish later").performClick()
        rule.onNodeWithText("Show the score").performClick()
        waitFor(hasContentDescription("Share or print"))
        rule.onNodeWithContentDescription("Share or print").performClick()
        rule.onNode(isHeading() and hasText("Share or print")).assertExists()
        rule.onNode(hasText("Solo Cornet (you)") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).assertIsSelected()
        val exports = rule.activity.cacheDir.resolve("exports")
        exports.deleteRecursively()
        // Braille is the engine's render: checked when the fixture carries it. The PDF is the engine's when the fixture
        // has it, else the phone lays it out.
        val pdf = Product.PHONE_PDF || (fixtureHas("brass-band.pdf") && fixtureHas("parts/02-Solo-Cornet.pdf"))
        val braille = fixtureHas("brass-band.brf")
        if (pdf) {
            // My part and PDF are the default (print your own part): that makes the Solo Cornet's PDF.
            rule.onNodeWithTag("share").performClick()
            waitUntil(20_000) { exports.listFiles().orEmpty().any { it.extension == "pdf" && it.name.contains("Solo Cornet") && it.length() > 0 } }
            val part = exports.listFiles()!!.first { it.extension == "pdf" }
            assertEquals("%PDF", String(part.readBytes(), 0, 4))
            ScreenDevice.closeSystemSheet(rule)
            exports.deleteRecursively()
        }
        // The conductor's score, with the other formats.
        rule.onNode(hasText("Conductor's score") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).performClick()
        if (pdf) rule.onNode(hasText("PDF") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Checkbox)).assertExists()
        for (f in listOf("MusicXML", "MIDI", "Talking score") + listOfNotNull("Braille music".takeIf { braille })) {
            val box = rule.onNode(hasText(f) and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Checkbox)).performScrollTo()
            // Without a PDF, MusicXML is the format already chosen.
            if (box.fetchSemanticsNode().config.getOrNull(SemanticsProperties.ToggleableState) != androidx.compose.ui.state.ToggleableState.On) box.performClick()
        }
        if (pdf) rule.onNodeWithText("Print").assertHeightIsAtLeast(48.dp)

        // One Share builds every chosen file (MusicXML, PDF, alphaTab MIDI, talking-score HTML, BRF), then opens the chooser.
        rule.onNodeWithTag("share").performClick()
        for (ext in listOf("musicxml", "mid", "html") + listOfNotNull("pdf".takeIf { pdf }, "brf".takeIf { braille })) {
            runCatching { waitUntil(20_000) { exports.listFiles().orEmpty().any { it.extension == ext && it.length() > 0 } } }.onFailure {
                throw AssertionError("no .$ext; files ${exports.listFiles().orEmpty().map { f -> f.name }}", it)
            }
        }
        ScreenDevice.closeSystemSheet(rule)
        val midi = exports.listFiles()!!.first { it.extension == "mid" }.readBytes()
        assertEquals("MThd", String(midi, 0, 4))
        val html = exports.listFiles()!!.first { it.extension == "html" }.readText()
        // The core's talking score of the arranged score: every part, one line per event.
        assertTrue(html.contains("Solo Cornet") && html.contains("Solo Horn") && html.contains("uncertain"))
        if (!braille) return
        val brf = exports.listFiles()!!.first { it.extension == "brf" }.readText()
        // North American Braille ASCII with CRLF lines; the music lines fit 40 cells (the title may not).
        val lines = brf.split("\r\n")
        assertTrue("BRF", brf.length > 1000 && lines.size > 50 && lines.count { it.length <= 40 } >= lines.size * 9 / 10)
    }

    /** Listen to this bar turns into Stop in the same place and size; Space and Enter toggle it; it comes back by itself. */
    @Test
    fun listenToThisBarIsStoppable() {
        // The score's bar is cut from the engine's rendered MP3.
        assumeTrue("the fixture has no rendered MP3", fixtureHas("brass-band.mp3"))
        openOldHundredth()
        rule.onNodeWithText("Soloist with orchestra or band").performClick()
        rule.onNodeWithText("Continue").performClick()
        waitFor(isHeading() and hasText("Check ", substring = true), 60_000)
        val button = rule.onNodeWithTag("listen-bar", useUnmergedTree = false)
        button.performScrollTo()
        val before = button.fetchSemanticsNode().boundsInRoot
        button.performClick()
        // The score's bar is decoded from the rendered MP3 first.
        waitUntil(20_000) { rule.onAllNodesWithText("Stop").fetchSemanticsNodes().isNotEmpty() }
        val during = button.fetchSemanticsNode().boundsInRoot
        assertEquals("same place and size", before, during)
        rule.onNodeWithText("Listen to this bar").assertDoesNotExist()
        // A hardware keyboard: out of touch mode, so the button can take focus.
        ScreenDevice.keyboard(rule)
        button.requestFocus()
        button.performKeyInput { pressKey(Key.Spacebar) }
        runCatching { waitUntil(5_000) { rule.onAllNodesWithText("Listen to this bar").fetchSemanticsNodes().isNotEmpty() } }.onFailure {
            throw AssertionError("after Space: " + button.fetchSemanticsNode().config.toString(), it)
        }
        // Announced without a bar over the card.
        waitUntil(5_000) { rule.onAllNodes(hasContentDescription("Stopped"), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        button.requestFocus()
        button.performKeyInput { pressKey(Key.Enter) }
        waitUntil(20_000) { rule.onAllNodesWithText("Stop").fetchSemanticsNodes().isNotEmpty() }
        // A bar lasts a few seconds: then it is Listen again, without a press.
        waitUntil(30_000) { rule.onAllNodesWithText("Listen to this bar").fetchSemanticsNodes().isNotEmpty() }
        checkAccessibility()
    }
}
