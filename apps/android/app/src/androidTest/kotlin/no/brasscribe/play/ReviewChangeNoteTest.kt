package no.brasscribe.play

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.accessibility.disableAccessibilityChecks
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.model.VoiceRole
import no.brasscribe.play.score.BarAudio
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

/**
 * "Change note…" → Save stays on the note (owner's report: saving jumped to the next note, so there
 * was no way to try a pitch and listen again). On the Old Hundredth fixture: Save writes the note and
 * keeps the card with "Changed to … (was …)", Listen plays the bar with the new note, the note can be
 * changed again or undone, and only Keep checks it and moves on.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class ReviewChangeNoteTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val vm by lazy { ViewModelProvider(rule.activity)[PlayViewModel::class.java] }

    @Before
    fun setUp() {
        // ATF checks are not on for every action: the bottom sheet's own Material 3 drag handle (32 dp
        // wide) fails the touch-target check. The review screen is checked once the card shows the change.
        rule.activity.getSharedPreferences("engine", 0).edit().clear().commit()
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        (rule.activity.application as PlayApplication).container.fixtureSource =
            FixtureSource { name -> runCatching { assets.open("old-hundredth/$name").use { it.readBytes() } }.getOrNull() }
        rule.runOnUiThread {
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
        }
        rule.waitForIdle()
        rule.onNodeWithText("Soloist with orchestra or band").performClick()
        rule.onNodeWithText("Continue").performClick()
        rule.waitUntil(60_000) {
            rule.onAllNodes(isHeading() and hasText("Check ", substring = true)).fetchSemanticsNodes().isNotEmpty()
        }
    }

    /** "1 of 7": the card's place in the queue. */
    private fun position(): String = rule.onAllNodes(SemanticsMatcher("position") { n ->
        n.config.getOrNull(SemanticsProperties.Text)?.any { Regex("""^\d+ of \d+$""").matches(it.text) } == true
    }, useUnmergedTree = true).fetchSemanticsNodes().first().config[SemanticsProperties.Text].first().text

    private fun changedText(): String? = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "note-changed"), useUnmergedTree = true)
        .fetchSemanticsNodes().firstOrNull()?.config?.get(SemanticsProperties.Text)?.first()?.text

    private fun changeUp() {
        rule.onNodeWithText("Change note…").performScrollTo().performClick()
        rule.onNodeWithText("Up a semitone").performClick()
        rule.onNodeWithText("Save").performScrollTo().performClick()
        rule.waitForIdle()
    }

    private fun melodyPitches() = vm.result.value!!.composition!!.voices.first { it.role == VoiceRole.MELODY }.notes.map { it.pitch }

    @Test
    fun saveStaysOnTheNoteUntilKeep() {
        val before = position()
        val checkedBefore = vm.checked.value
        val xmlBefore = vm.result.value!!.musicXml
        val pitchesBefore = melodyPitches()

        // Save with nothing changed does nothing.
        rule.onNodeWithText("Change note…").performScrollTo().performClick()
        rule.onNodeWithText("Save").assertIsNotEnabled()
        rule.onNodeWithText("Cancel").performClick()
        rule.waitForIdle()

        // Save stays on the note: same place in the queue, not kept, "Changed to X (was Y)" on the card.
        changeUp()
        assertEquals(before, position())
        assertEquals(checkedBefore, vm.checked.value)
        val changed = changedText()
        assertNotNull(changed)
        changed!!
        assertTrue(changed, Regex("""^Changed to \S+ \(was \S+\)$""").matches(changed))
        val was = changed.substringAfter("(was ").removeSuffix(")")
        assertTrue(vm.result.value!!.changedOnPhone)
        val xmlChanged = vm.result.value!!.musicXml
        assertTrue("the score has the new note", xmlChanged != xmlBefore)
        assertEquals(1, melodyPitches().zip(pitchesBefore).count { (a, b) -> a == b + 1 })
        // TalkBack reads the change on the card and offers Undo there.
        val card = rule.onAllNodes(SemanticsMatcher("card") { n ->
            n.config.getOrNull(SemanticsProperties.ContentDescription)?.any { it.contains("Changed to") } == true
        }).fetchSemanticsNodes().first()
        assertTrue(card.config[SemanticsActions.CustomActions].any { it.label == "Undo change" })
        rule.enableAccessibilityChecks()
        rule.onRoot().tryPerformAccessibilityChecks()
        rule.disableAccessibilityChecks()

        // Listen plays the bar as it is now: rendered on the phone from the changed score.
        val context = rule.activity.applicationContext
        val bar = card.config.getOrNull(SemanticsProperties.Text).orEmpty()
            .firstNotNullOf { Regex("""^Bar (\d+)""").find(it.text)?.groupValues?.get(1)?.toInt() }
        val old = BarAudio.render(context, xmlBefore, bar)!!
        val now = BarAudio.render(context, xmlChanged, bar)!!
        assertTrue("the bar is not silent", now.peak() > 0.01f)
        assertTrue("the new note sounds different", old.samples.size != now.samples.size ||
            old.samples.indices.any { abs(old.samples[it] - now.samples[it]) > 1e-3f })
        rule.onNodeWithTag("listen-bar").performScrollTo().performClick()
        rule.waitUntil(20_000) { rule.onAllNodesWithText("Stop").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("listen-bar").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithText("Listen to this bar").fetchSemanticsNodes().isNotEmpty() }

        // Change again: still this note, "was" is still what Brasscribe wrote.
        changeUp()
        assertEquals(before, position())
        assertTrue(changedText()!!, changedText()!!.endsWith("(was $was)"))
        assertEquals(1, melodyPitches().zip(pitchesBefore).count { (a, b) -> a == b + 2 })

        // Undo: back to the transcription, still this note, still open.
        rule.onNodeWithTag("undo-change").performScrollTo().performClick()
        rule.waitForIdle()
        assertEquals(null, changedText())
        assertEquals(pitchesBefore, melodyPitches())
        assertEquals(before, position())
        assertTrue(vm.reviewChanges.value.isEmpty())

        // Change and Keep: checked, and the review goes on with one fewer.
        changeUp()
        rule.onNodeWithText("Keep, go to next").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithText("Kept.", substring = true).fetchSemanticsNodes().isNotEmpty() }
        val total = { p: String -> p.substringAfter(" of ").toInt() }
        assertEquals(total(before) - 1, total(position()))
        assertTrue(vm.checked.value.values.sumOf { it.size } > checkedBefore.values.sumOf { it.size })
        assertEquals(null, changedText())
    }
}
