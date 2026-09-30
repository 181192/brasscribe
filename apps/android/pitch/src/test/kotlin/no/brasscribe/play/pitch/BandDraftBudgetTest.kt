package no.brasscribe.play.pitch

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** A band draft is refused up front when the take is longer than free memory holds. */
class BandDraftBudgetTest {
    @Test
    fun theDraftFitsFreeMemoryByLength() {
        val mb = 1L shl 20
        assertTrue(BandDraftPipeline.fits(5 * 60.0, 2048 * mb))
        assertTrue(BandDraftPipeline.fits(0.0, BandDraftPipeline.FIXED_BYTES))
        assertFalse(BandDraftPipeline.fits(10 * 60.0, 512 * mb))
        assertFalse(BandDraftPipeline.fits(1.0, 100 * mb))
    }
}
