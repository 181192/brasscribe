package no.brasscribe.play

import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performKeyInput
import androidx.compose.ui.test.pressKey
import androidx.compose.ui.test.requestFocus
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Page pedals on the music stand while a repeat is set (design/music-stand.md §7): right (Page Down) plays and pauses,
 * left (Page Up) goes back to the repeat's first bar, and the stand says so under Repeat. Without a repeat they turn pages.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class StandPedalRepeatTest : ScreenTest() {
    override val shots = "brasscribe/stand-pedal-repeat"

    @Before
    fun setUp() {
        container.firstRunDone = true
        container.standFollow = true
        container.standKeepControls = false
        container.standHintShown = true
        container.assistiveOverride = false
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @After
    fun tearDown() {
        container.assistiveOverride = null
        runCatching { vm.scoreController?.let { c -> if (c.state.value.playing) rule.runOnUiThread { c.togglePlay() } } }
    }

    private fun state() = vm.scoreController!!.state.value

    private fun position() = rule.onAllNodes(hasTestTag("stand-position"), useUnmergedTree = false).fetchSemanticsNodes().firstOrNull()
        ?.let { n -> n.config.getOrNull(SemanticsProperties.Text)?.joinToString(" ") { it.text } }.orEmpty()

    private fun page() = Regex("""(?:pages?|side) (\d+)(?:–\d+)? (?:of|av)""").find(position())?.groupValues?.get(1)?.toInt() ?: -1

    private fun pageCount() = Regex("""(?:of|av) (\d+)$""").find(position())?.groupValues?.get(1)?.toInt() ?: -1

    @Test
    fun withARepeatThePedalsPlayPauseAndGoBackWithoutItTheyTurnPages() {
        val xml = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(20_000) { rule.onAllNodesWithTag("stand-enter").fetchSemanticsNodes().isNotEmpty() }
        waitUntil(20_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.scoreController!!.setZoom(400) }
        rule.onNodeWithTag("stand-enter").performClick()
        // The stand's pages at 400 %, laid out from the engraving at that zoom (as MusicStandTest waits for them).
        waitUntil(20_000) { page() >= 1 && pageCount() >= 3 }
        settle()
        ScreenDevice.keyboard(rule)
        val score = rule.onNodeWithTag("stand-score")
        score.requestFocus()

        // No repeat: the pedal turns the page, and the stand says nothing about pedals.
        assertTrue(rule.onAllNodesWithTag("stand-pedals").fetchSemanticsNodes().isEmpty())
        score.performKeyInput { pressKey(Key.PageDown) }
        waitUntil(10_000) { page() == 2 }
        assertTrue("no repeat: a pedal never starts the music", !state().playing)
        score.performKeyInput { pressKey(Key.PageUp) }
        waitUntil(10_000) { page() == 1 }

        // A repeat of bars 5 to 6: the stand says what the pedals do now.
        rule.runOnUiThread { vm.scoreController!!.setLoop(5..6) }
        waitUntil(3_000) { state().loop == 5..6 }
        rule.onNodeWithText("Pedals: right plays and pauses, left goes back to bar 5.").assertExists()
        checkAccessibility()
        shot("repeat-set")

        // Right plays and pauses; the page stays the repeat's.
        score.performKeyInput { pressKey(Key.PageDown) }
        waitUntil(10_000) { state().playing }
        score.performKeyInput { pressKey(Key.DirectionRight) }
        waitUntil(10_000) { !state().playing }

        // A held pedal plays once, not on and off with every repeat of its key; held again, it pauses once.
        ScreenDevice.hold(rule, android.view.KeyEvent.KEYCODE_PAGE_DOWN, repeats = 5)
        waitUntil(10_000) { state().playing }
        rule.mainClock.advanceTimeBy(500)
        assertTrue("held: still playing", state().playing)
        ScreenDevice.hold(rule, android.view.KeyEvent.KEYCODE_PAGE_DOWN, repeats = 4)
        waitUntil(10_000) { !state().playing }
        rule.mainClock.advanceTimeBy(500)
        assertTrue("held: still paused", !state().playing)

        // Left goes back to the repeat's first bar, and says so.
        rule.runOnUiThread { vm.scoreController!!.goToBar(9) }
        waitUntil(3_000) { state().bar == 9 }
        score.performKeyInput { pressKey(Key.PageUp) }
        waitUntil(3_000) { state().bar == 5 }
        waitUntil(3_000) { rule.onAllNodes(hasContentDescription("Back to bar 5.", substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        assertTrue("going back does not start the music", !state().playing)

        // The repeat stopped: the pedals turn pages again.
        rule.runOnUiThread { vm.scoreController!!.setLoop(null) }
        waitUntil(3_000) { state().loop == null }
        val before = page()
        score.performKeyInput { pressKey(Key.PageDown) }
        waitUntil(10_000) { page() == before + 1 }
        assertEquals(false, state().playing)
    }
}
