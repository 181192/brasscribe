package no.kalli.scribe.play

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import no.kalli.scribe.play.screen.testedProduct
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * While a recording is being written down, a small phone still shows how far it has come: the step, the percentage
 * and Cancel are in view without scrolling, upright with larger text and on its side. In both apps (the screen is shared).
 */
@RunWith(AndroidJUnit4::class)
class WritingDownRoomTest : ScreenTest() {
    private val tab get() = testedProduct.name == "Fretscribe"
    private var pace = 0.0

    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
        container.fixtureSource = null
        if (pace > 0) container.fixtureStageSeconds = pace
    }

    private fun writingDown() {
        // A computer that takes its time: the screen stays as it is while it is looked at.
        computer(if (tab) "bass-line" else "old-hundredth")
        if (pace == 0.0) pace = container.fixtureStageSeconds
        container.fixtureStageSeconds = 60.0
        val file = recording("Room test.wav")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Room test.wav", SourceKind.FILE, 2.0, file = file))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(if (tab) Profile.TAB else Profile.BRASS_BAND)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running }
        settle()
    }

    /** The step's title, the percentage and Cancel are drawn whole. */
    private fun theProgressIsInView() {
        val step = rule.onNode(hasText(text(vm.transcribe.value.step.text)) and isHeading()).fetchSemanticsNode()
        val percent = rule.onNodeWithTag("transcribe-percent").fetchSemanticsNode()
        val cancel = rule.onNodeWithText(text(R.string.cancel)).fetchSemanticsNode()
        for ((what, node) in listOf("the step" to step, "the percentage" to percent, "Cancel" to cancel)) {
            assertEquals("$what is in view, whole", node.size.height.toFloat(), node.boundsInWindow.height, 1f)
        }
    }

    @Test
    fun aSmallPhoneWithLargerTextShowsTheProgress() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        writingDown()
        shot("writing-down-small")
        theProgressIsInView()
    }

    @Test
    fun aSmallPhoneOnItsSideShowsTheProgress() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        writingDown()
        shot("writing-down-small-landscape")
        theProgressIsInView()
    }
}
