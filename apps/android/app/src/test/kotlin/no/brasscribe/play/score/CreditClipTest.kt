package no.brasscribe.play.score

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CreditClipTest {
    @Test
    fun clipSpansTheEngravingNotTheSurface() {
        // A 1080 px wide phone at density 2.75: the engraving is 392 units wide, the music ends at 874.5.
        val (right, bottom) = creditClip(engravedWidth = 392.0, musicBottom = 874.5, density = 2.75f)
        assertEquals(1078, right)
        assertEquals(2405, bottom)
    }

    @Test
    fun widthRoundsUpSoTheLastColumnStays() {
        assertEquals(3, creditClip(1.1, 10.0, 2f).first)
    }

    @Test
    fun noReportedWidthLeavesTheSidesOpen() {
        val (right, _) = creditClip(0.0, 100.0, 3f)
        assertTrue("a missing width must not hide the score ($right)", right > 100_000)
    }
}
