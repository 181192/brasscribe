package no.kalli.fretscribe

import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.tab.RepeatBars
import no.kalli.scribe.tab.SpeedTrainer
import no.kalli.scribe.test.Slow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.experimental.categories.Category
import org.junit.runner.RunWith

/**
 * The speed trainer and the saved repeats in Repeat bars, on a fixture computer: the bars chosen start slow and go
 * faster each time the recording has played them through, and a repeat that was saved starts with one tap.
 */
@RunWith(AndroidJUnit4::class)
@Category(Slow::class)
class SpeedTrainerTest : TabScreenTest() {
    override val shots = "fretscribe/speed-trainer"

    private fun there(tag: String) = rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()

    private fun openRepeat() {
        rule.onNodeWithTag("fs-practice-repeat").performClick()
        waitForTag("fs-practice-repeat-set", 5_000)
    }

    @Test
    fun theBarsStartSlowAndGoFasterAsTheRecordingPlaysThemThrough() {
        computer("bass-line-marks")
        showTheTab()
        waitForTag("fs-practice-play", 20_000)
        openRepeat()
        // Off until it is turned on; then where it starts, how far it goes and how often each speed is played.
        rule.onNodeWithTag("fs-practice-trainer").performScrollTo().assertIsOff()
        assertFalse(there("fs-practice-trainer-from"))
        rule.onNodeWithTag("fs-practice-trainer").performClick()
        rule.onNodeWithTag("fs-practice-trainer").assertIsOn()
        rule.onNodeWithTag("fs-practice-trainer-from").performScrollTo().assertContentDescriptionEquals("Start at 60%")
        rule.onNodeWithTag("fs-practice-trainer-to").performScrollTo().assertContentDescriptionEquals("Up to 100%")
        rule.onNodeWithTag("fs-practice-trainer-every").performScrollTo().assertContentDescriptionEquals("Times through at each speed 2")
        rule.onNodeWithTag("fs-practice-trainer-every-down").performScrollTo().assertContentDescriptionEquals("Times through at each speed: less").performClick()
        rule.onNodeWithTag("fs-practice-trainer").assertTextContains("Starts at 60% and goes 5% faster after every time through, up to 100%.")
        rule.onNodeWithTag("fs-practice-trainer-every-up").performScrollTo().performClick()
        rule.onNodeWithTag("fs-practice-trainer").assertTextContains("Starts at 60% and goes 5% faster after every 2 times through, up to 100%.")
        rule.onNodeWithTag("fs-practice-trainer-every-down").performScrollTo().performClick()
        checkAccessibility()
        shot("speed-trainer")
        // One bar, the first: the recording made for the test is two seconds long.
        repeat(8) { if (practice.repeat == null) rule.onNodeWithTag("fs-practice-to-down").performScrollTo().performClick() }
        rule.onNodeWithTag("fs-practice-repeat-set").performScrollTo().performClick()
        waitUntil(5_000) { !there("fs-practice-repeat-set") }
        assertEquals(SpeedTrainer(60, 100, every = 1), practice.trainer)
        assertEquals(60, practice.speed)
        rule.onNodeWithTag("fs-practice-speed").assertContentDescriptionEquals("Speed 60%")

        // Played: every time the recording turns back to the start of the bars, they are 5 % faster.
        val bars = practice.repeat!!
        assertEquals(bars.first, bars.last)
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(60_000) { practice.speed >= 70 }
        assertTrue(practice.playing)
        assertEquals(bars, practice.repeat)
        // A speed the player sets ends the trainer.
        rule.onNodeWithTag("fs-practice-slower").performClick()
        assertNull(practice.trainer)
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntil(10_000) { !practice.playing }
    }

    @Test
    fun aSavedRepeatStartsWithOneTap() {
        computer("bass-line-marks")
        showTheTab()
        waitForTag("fs-practice-play", 20_000)
        openRepeat()
        assertFalse(there("fs-practice-saved"))
        // The bars the dialog opens on are saved; then the button takes them out again.
        rule.onNodeWithTag("fs-practice-repeat-save").performScrollTo().performClick()
        waitForTag("fs-practice-saved-0-3", 5_000)
        assertEquals(listOf(RepeatBars(0, 3)), practice.savedRepeats)
        assertTrue(there("fs-practice-repeat-forget"))
        rule.onNodeWithTag("fs-practice-from-up").performScrollTo().performClick()
        rule.onNodeWithTag("fs-practice-repeat-save").performScrollTo().performClick()
        waitForTag("fs-practice-saved-1-3", 5_000)
        rule.onNodeWithTag("fs-practice-saved-1-3").assertContentDescriptionEquals("Repeat bars 2 to 4")
        checkAccessibility()
        shot("saved-repeats")
        rule.onNodeWithTag("fs-practice-repeat-cancel").performScrollTo().performClick()
        waitUntil(5_000) { !there("fs-practice-repeat-set") }
        assertNull(practice.repeat)

        // One tap on a saved repeat starts it.
        openRepeat()
        rule.onNodeWithTag("fs-practice-saved-0-3").performScrollTo().performClick()
        waitUntil(5_000) { !there("fs-practice-repeat-set") }
        assertEquals(RepeatBars(0, 3), practice.repeat)
        // And it is taken out again from the same dialog.
        openRepeat()
        rule.onNodeWithTag("fs-practice-repeat-forget").performScrollTo().performClick()
        waitUntil(5_000) { !there("fs-practice-saved-0-3") }
        assertEquals(listOf(RepeatBars(1, 3)), practice.savedRepeats)
    }

    /**
     * Plays the first bar over and over with the trainer from 60 % up to 100 %, one step every time through, and
     * follows the speed: each step is exactly 5 %, and each speed is held for one time through the bar at that speed
     * (about its length over the speed), so a turn counted twice (a step held for no time) or missed (held for two)
     * fails. The pass lengths are the app's own time, which goes as fast as the wall's.
     */
    private fun eachTimeThroughIsOneStep(what: String) {
        rule.runOnUiThread {
            practice.repeat(RepeatBars(0, 0))
            practice.train(SpeedTrainer(60, 100, every = 1))
        }
        assertEquals(60, practice.speed)
        val bar = practice.repeatSeconds()!!
        rule.onNodeWithTag("fs-practice-play").performClick()
        val changes = ArrayList<Pair<Int, Long>>()
        var last = practice.speed
        val started = System.nanoTime()
        waitUntil(90_000) {
            if (practice.speed != last) { last = practice.speed; changes += last to System.nanoTime() }
            practice.speed >= 100 || !practice.playing
        }
        rule.runOnUiThread { practice.pause() }
        assertEquals("$what: the speeds", (65..100 step 5).toList(), changes.map { it.first })
        var from = started
        var speedBefore = 60
        for ((speed, at) in changes) {
            val held = (at - from) / 1e9
            val pass = (bar.endInclusive - bar.start) / (speedBefore / 100.0)
            assertTrue("$what: $speedBefore % held ${"%.2f".format(held)} s for a pass of ${"%.2f".format(pass)} s", held > 0.5 * pass && held < 1.6 * pass + 0.3)
            from = at
            speedBefore = speed
        }
        assertNull("$what: the trainer ends at its last speed", practice.trainer)
    }

    @Test
    fun eachTimeThroughTheRecordingIsExactlyOneStep() {
        computer("bass-line-marks")
        showTheTab()
        waitForTag("fs-practice-play", 20_000)
        waitUntil(20_000) { practice.recording == no.kalli.scribe.tab.RecordingState.HERE }
        eachTimeThroughIsOneStep("the recording")
    }

    @Test
    fun eachTimeThroughTheTabsOwnSoundIsExactlyOneStep() {
        computer("bass-line-marks")
        showTheTab()
        waitForTag("fs-practice-play", 20_000)
        // The song opened again without its recording on the phone: the tab's own sound plays it.
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { vm.scores.value.isNotEmpty() }
        settle()
        java.io.File(rule.activity.noBackupFilesDir, "recordings").deleteRecursively()
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        waitUntil(20_000) { practice.recording != no.kalli.scribe.tab.RecordingState.LOOKING && practice.tabSound }
        assertEquals(no.kalli.scribe.tab.PracticeSound.TAB, practice.hears)
        eachTimeThroughIsOneStep("the tab's own sound")
    }

    /** Saved repeats are the song's in Your songs: written again (a new job), the song still has them where its bars are. */
    @Test
    fun aSavedRepeatStaysWhenTheSongIsWrittenAgain() {
        computer("bass-line-marks")
        showTheTab()
        waitForTag("fs-practice-play", 20_000)
        waitUntil(10_000) { vm.practiceScoreId != null }
        rule.runOnUiThread { practice.saveRepeat(RepeatBars(1, 2)) }
        assertEquals(listOf(RepeatBars(1, 2)), practice.savedRepeats)
        val job = vm.result.value!!.jobId
        // Check the song, a tap from the tab's header; another tuning writes the song again.
        rule.runOnUiThread { vm.back() }
        waitForTag("fs-check-change-tuning", 20_000)
        rule.onNodeWithTag("fs-check-change-tuning").performScrollTo().performClick()
        waitUntil(60_000) { vm.result.value?.jobId != job }
        waitForTag("fs-show-tab", 30_000)
        rule.onNodeWithTag("fs-show-tab").performScrollTo().performClick()
        engraved()
        waitUntil(10_000) { practice.savedRepeats == listOf(RepeatBars(1, 2)) }
        // And on the phone, as a new process would read it.
        rule.runOnUiThread { practice.forgetAllButThePhone() }
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { vm.scores.value.isNotEmpty() }
        settle()
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        waitUntil(10_000) { practice.savedRepeats == listOf(RepeatBars(1, 2)) }
    }
}
