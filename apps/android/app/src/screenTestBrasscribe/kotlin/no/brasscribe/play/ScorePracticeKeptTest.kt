package no.brasscribe.play

import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * A score from Your scores opens where it was left in practice, also after the app was closed: the speed, the bars
 * repeated and the bar. Deleting the score takes its place with it.
 */
@RunWith(AndroidJUnit4::class)
class ScorePracticeKeptTest : ScreenTest() {
    @Before
    fun setUp() {
        container.firstRunDone = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    private fun controller() = vm.scoreController!!
    private fun loaded() = vm.scoreController?.state?.value?.loaded == true

    @Test
    fun aScoreOpensWhereItWasLeftAfterTheAppWasClosed() {
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.home(); vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { loaded() && vm.practiceScoreId != null }
        val id = vm.practiceScoreId!!
        rest()
        // Practise: 70 %, bars 9–10 repeated, at bar 10.
        rule.runOnUiThread { controller().setSpeed(70); controller().setLoop(9..10); controller().goToBar(10) }
        rule.waitForIdle()
        rule.runOnUiThread { vm.home() }
        val kept = File(rule.activity.noBackupFilesDir, "score-practice/$id")
        waitUntil(10_000) { kept.isFile && kept.readText() == "10 70 9 10" }

        // What a new process would not have: the view model's memory of it.
        rule.runOnUiThread { vm.forgetPracticeInMemory() }
        waitUntil(10_000) { vm.savedScores.value.any { it.id == id } }
        rule.runOnUiThread { vm.openSavedScore(vm.savedScores.value.first { it.id == id }) }
        waitUntil(30_000) { loaded() && controller().state.value.speed == 70 }
        val st = controller().state.value
        assertEquals(70, st.speed)
        assertEquals(9..10, st.loop)
        assertEquals(10, st.bar)

        // Deleted from Your scores, its place goes.
        rule.runOnUiThread { vm.home() }
        rule.runOnUiThread { vm.deleteEntry(vm.scores.value.first { it.saved?.id == id }) }
        waitUntil(10_000) { !kept.exists() }
        assertFalse(kept.exists())
    }
}
