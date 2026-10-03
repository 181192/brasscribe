package no.brasscribe.play

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.ui.STEP_HOLD_MS
import no.brasscribe.play.ui.STEP_REPEAT_MS
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Setting up practice takes fewer taps: Repeat opens on the bar the player is at (four bars from there), and holding
 * − or + on the music stand's speed keeps stepping.
 */
@RunWith(AndroidJUnit4::class)
class PracticeControlsTest : ScreenTest() {
    @Before
    fun setUp() {
        container.firstRunDone = true
        container.standHintShown = true
        container.standKeepControls = false
        container.assistiveOverride = false
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.home(); vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && rule.onAllNodesWithTag("stand-enter").fetchSemanticsNodes().isNotEmpty() }
    }

    @After
    fun tearDown() {
        container.assistiveOverride = null
        rule.mainClock.autoAdvance = true
    }

    private fun speed() = vm.scoreController!!.state.value.speed

    /** The values of the text fields on screen, in order. */
    private fun fields(): List<String> = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.EditableText)).fetchSemanticsNodes()
        .map { it.config[SemanticsProperties.EditableText].text }

    @Test
    fun repeatOpensOnTheBarThePlayerIsAt() {
        rule.runOnUiThread { vm.scoreController!!.goToBar(7) }
        rule.waitForIdle()
        rule.onNodeWithText(text(R.string.practice)).performClick()
        rule.onNodeWithText(text(R.string.loop)).performClick()
        waitUntil(5_000) { fields().size == 2 }
        assertEquals(listOf("7", "10"), fields())
        rule.onNodeWithText(text(R.string.loop_set)).performClick()
        waitUntil(5_000) { vm.scoreController!!.state.value.loop == 7..10 }

        // Near the end it stops at the last bar.
        rule.runOnUiThread { vm.scoreController!!.setLoop(null); vm.scoreController!!.goToBar(11) }
        rule.waitForIdle()
        rule.onNodeWithText(text(R.string.practice)).performClick()
        rule.onNodeWithText(text(R.string.loop)).performClick()
        waitUntil(5_000) { fields().size == 2 }
        assertEquals(listOf("11", "12"), fields())
        // (Set, the sheet closes: the score is the screen the test ends on.)
        rule.onNodeWithText(text(R.string.loop_set)).performClick()
        waitUntil(5_000) { vm.scoreController!!.state.value.loop == 11..12 }
    }

    @Test
    fun holdingTheStandsSpeedKeepsStepping() {
        rule.onNodeWithTag("stand-enter").performClick()
        waitUntil(20_000) { rule.onAllNodesWithTag("stand-slower").fetchSemanticsNodes().isNotEmpty() }
        // A tap is one step.
        rule.onNodeWithTag("stand-slower").performClick()
        waitUntil(2_000) { speed() == 95 }
        // Held, it steps again and again until it is let go; letting go adds no step of its own.
        fun composeTime(ms: Long) { rule.mainClock.advanceTimeBy(ms); rule.waitForIdle() }
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("stand-slower").performTouchInput { down(center) }
        composeTime(STEP_HOLD_MS / 2)
        assertEquals("no step before the hold", 95, speed())
        composeTime(1_000)
        val held = speed()
        assertTrue("held for a second, it stepped on its own ($held %)", held <= 80)
        rule.onNodeWithTag("stand-slower").performTouchInput { up() }
        composeTime(1_000)
        assertEquals("let go, it stops", held, speed())
        // Held to the end, it stops there, and the next click (as a screen reader or a switch presses) still steps.
        rule.onNodeWithTag("stand-faster").performTouchInput { down(center) }
        composeTime(STEP_HOLD_MS + 40 * STEP_REPEAT_MS)
        rule.onNodeWithTag("stand-faster").performTouchInput { up() }
        composeTime(500)
        assertEquals(150, speed())
        rule.onNodeWithTag("stand-slower").performSemanticsAction(SemanticsActions.OnClick)
        composeTime(100)
        assertEquals("a click after a hold to the end steps", 145, speed())
        // The button that was held to the end and turned off has let go of its hold too: its next click steps.
        rule.onNodeWithTag("stand-faster").performSemanticsAction(SemanticsActions.OnClick)
        composeTime(100)
        assertEquals("the held button's next click steps", 150, speed())
        rule.onNodeWithTag("stand-slower").performSemanticsAction(SemanticsActions.OnClick)
        composeTime(100)
        assertEquals(145, speed())
        // A hold the finger slides off ends with no click either: the next one steps once.
        rule.onNodeWithTag("stand-slower").performTouchInput { down(center) }
        composeTime(STEP_HOLD_MS + STEP_REPEAT_MS + STEP_REPEAT_MS / 2)
        rule.onNodeWithTag("stand-slower").performTouchInput { moveBy(androidx.compose.ui.geometry.Offset(0f, -2_000f)); up() }
        composeTime(500)
        val cancelled = speed()
        assertTrue("the cancelled hold stepped ($cancelled %)", cancelled < 145)
        rule.onNodeWithTag("stand-slower").performSemanticsAction(SemanticsActions.OnClick)
        composeTime(100)
        assertEquals("a click after a cancelled hold steps", cancelled - 5, speed())
        rule.mainClock.autoAdvance = true
    }
}
