package no.brasscribe.play

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.click
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The "?" marks on the score lead to their notes (design/system.md §5): a tap on one opens Check the notes at that
 * note. And Check them goes on where the player left Check the notes, not from the start of the queue.
 */
@RunWith(AndroidJUnit4::class)
class MarksOpenCheckTheNotesTest : ScreenTest() {
    @Before
    fun setUp() {
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        waitUntil(20_000) { cardTitle() != null }
    }

    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    /** The note card's title: "Bar 5 · Solo Cornet" (or "Bars 5–6 · …"). */
    private fun cardTitle(): String? = rule.onAllNodes(SemanticsMatcher("card title") { n ->
        n.config.getOrNull(SemanticsProperties.Text)?.any { CARD.containsMatchIn(it.text) } == true
    }, useUnmergedTree = true).fetchSemanticsNodes().firstOrNull()?.config?.get(SemanticsProperties.Text)?.first { CARD.containsMatchIn(it.text) }?.text

    /** The bars the card is about. */
    private fun cardBars(): IntRange {
        val m = CARD.find(cardTitle().orEmpty()) ?: return IntRange.EMPTY
        val first = m.groupValues[1].toInt()
        return first..(m.groupValues[2].takeIf { it.isNotEmpty() }?.toInt() ?: first)
    }

    private fun showScore() {
        rule.runOnUiThread { vm.navigate(Screen.SCORE) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        settle()
    }

    /** A mark on screen: the bar as the score numbers it, its "?" and the top of its staff, in the score view's own pixels. */
    private class Mark(val bar: Int, val at: Offset, val staffTop: Float)

    private fun marksOnScreen(): List<Mark> {
        val controller = vm.scoreController!!
        val box = rule.onNodeWithTag("score-view").fetchSemanticsNode().boundsInWindow
        val origin = IntArray(2).also { controller.overlay.getLocationInWindow(it) }
        return controller.overlay.markSpots().map { s ->
            Mark(controller.reviewBar(s.beat.voice.bar.index.toInt() + 1),
                Offset(origin[0] + s.centre.x - box.left, origin[1] + s.centre.y - box.top), origin[1] + s.staffTop - box.top)
        }.filter { m -> m.at.x in 0f..box.width && m.at.y > 40 && m.staffTop < box.height - 40 }
    }

    private fun tap(at: Offset) = rule.onNodeWithTag("score-view").performTouchInput { click(at) }

    @Test
    fun aTapOnAMarkOpensCheckTheNotesAtThatNote() {
        val first = cardBars()
        showScore()
        // A mark in view, in another bar than the card the queue starts with.
        val marks = marksOnScreen()
        assertTrue("marks on screen", marks.isNotEmpty())
        val other = marks.filter { it.bar !in first }
        assertTrue("a mark in another bar than $first: ${marks.map { it.bar }}", other.isNotEmpty())
        val mark = other.first()
        tap(mark.at)
        waitUntil(10_000) { vm.screen.value.last() == Screen.REVIEW && cardTitle() != null }
        assertTrue("the card ${cardTitle()} is the note of bar ${mark.bar}", mark.bar in cardBars())
        checkAccessibility()
    }

    @Test
    fun aTapOnTheMusicUnderAMarkIsTheScores() {
        showScore()
        val mark = marksOnScreen().first()
        // On the staff, under the "?" but inside its old 48 dp square: alphaTab's (the cursor), not Check the notes.
        tap(Offset(mark.at.x, mark.staffTop + 3f))
        rest()
        assertEquals(Screen.SCORE, vm.screen.value.last())
        tap(mark.at)
        waitUntil(10_000) { vm.screen.value.last() == Screen.REVIEW }
    }

    @Test
    fun theNotesPutOffStayPutOffWhenAMarkOpensCheckTheNotes() {
        rule.onNodeWithText(text(R.string.review_skip)).performClick()
        rule.waitForIdle()
        rule.onNodeWithText(text(R.string.review_skip)).performClick()
        rule.waitForIdle()
        val put = vm.reviewPlace()!!
        assertEquals(2, put.skipped.size)
        showScore()
        tap(marksOnScreen().first().at)
        waitUntil(10_000) { vm.screen.value.last() == Screen.REVIEW && cardTitle() != null }
        rule.waitForIdle()
        assertEquals(put.voice, vm.reviewPlace()!!.voice)
        assertEquals(put.skipped, vm.reviewPlace()!!.skipped)
    }

    @Test
    fun theScoreOffersTheMarksOfItsBarToTalkBack() {
        val first = cardBars()
        showScore()
        val controller = vm.scoreController!!
        val bar = marksOnScreen().first { it.bar !in first }.bar
        val name = text(R.string.action_check_marks)
        fun action() = rule.onNodeWithTag("score-view").fetchSemanticsNode().config.getOrNull(SemanticsActions.CustomActions).orEmpty().firstOrNull { it.label == name }
        // In a bar with no "?", there is no such action.
        val plain = (1..controller.state.value.totalBars).firstOrNull { !controller.marksIn(it) }
        if (plain != null) {
            rule.runOnUiThread { controller.goToBar(plain) }
            rule.waitForIdle()
            assertEquals(null, action())
        }
        // Shown bar of the score's numbering bar: the pickup, when there is one, is alphaTab's bar 1.
        val shown = (1..controller.state.value.totalBars).first { controller.reviewBar(it) == bar }
        rule.runOnUiThread { controller.goToBar(shown) }
        rule.waitForIdle()
        val check = action()
        assertTrue("the action is there in bar $bar", check != null)
        rule.runOnUiThread { check!!.action() }
        waitUntil(10_000) { vm.screen.value.last() == Screen.REVIEW && cardTitle() != null }
        assertTrue("the card ${cardTitle()} is in bar $bar", bar in cardBars())
    }

    @Test
    fun checkThemGoesOnWhereThePlayerLeftOff() {
        val first = cardTitle()
        // Two put off: the card is the third.
        rule.onNodeWithText(text(R.string.review_skip)).performClick()
        waitUntil(5_000) { cardTitle() != first }
        rule.onNodeWithText(text(R.string.review_skip)).performClick()
        rule.waitForIdle()
        val left = cardTitle()
        assertNotEquals(first, left)
        showScore()
        // Check them.
        rule.runOnUiThread { vm.navigate(Screen.REVIEW) }
        waitUntil(10_000) { vm.screen.value.last() == Screen.REVIEW && cardTitle() != null }
        assertEquals(left, cardTitle())
    }

    private companion object {
        val CARD = Regex("""^Bars? (\d+)(?:–(\d+))? · """)
    }
}
