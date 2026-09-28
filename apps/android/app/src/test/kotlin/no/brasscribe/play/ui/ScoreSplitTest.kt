package no.brasscribe.play.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScoreSplitTest {
    @Test
    fun phoneOnItsSideKeeps55PercentForTheScore() {
        // 370 dp inside the system bars, a 64 dp top bar: 306 dp under it.
        val controls = ScoreSplit.controlsMax(available = 370f, content = 306f, twoSystems = 150f)
        assertEquals(306f - 370f * 0.55f, controls, 0.01f)
        assertTrue(306f - controls >= 370f * 0.55f - 0.01f)
    }

    @Test
    fun twoSystemsWinOverTheShareWhenTaller() {
        val controls = ScoreSplit.controlsMax(available = 370f, content = 306f, twoSystems = 230f)
        assertEquals(76f, controls, 0.01f)
    }

    @Test
    fun controlsAlwaysKeepOneRow() {
        assertEquals(ScoreSplit.CONTROLS_ROW, ScoreSplit.controlsMax(available = 200f, content = 140f, twoSystems = 300f), 0.01f)
    }

    @Test
    fun onlyShortLandscapeWindowsAreCompact() {
        assertTrue(ScoreSplit.compact(landscape = true, screenHeightDp = 380))
        assertFalse(ScoreSplit.compact(landscape = true, screenHeightDp = 800))
        assertFalse(ScoreSplit.compact(landscape = false, screenHeightDp = 380))
    }
}
