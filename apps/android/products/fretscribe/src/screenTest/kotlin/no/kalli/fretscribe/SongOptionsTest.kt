package no.kalli.fretscribe

import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** A song's menu in Your songs offers what Fretscribe has: no music stand, which is Brasscribe's. */
@RunWith(AndroidJUnit4::class)
class SongOptionsTest : TabScreenTest() {
    @Test
    fun theMenuOffersNoMusicStand() {
        computer("bass-line-marks")
        showTheTab()
        waitUntil(10_000) { vm.savedScores.value.isNotEmpty() }
        rule.runOnUiThread { vm.home() }
        rest()
        rule.onAllNodesWithTag("score-options")[0].performScrollTo().performClick()
        waitForTag("score-delete", 5_000)
        assertTrue("no music stand in the menu", rule.onAllNodesWithTag("open-on-stand").fetchSemanticsNodes().isEmpty())
    }
}
