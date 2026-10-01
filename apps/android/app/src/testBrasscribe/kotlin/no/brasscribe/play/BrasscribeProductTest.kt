package no.brasscribe.play

import no.brasscribe.play.engine.Profile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** What Brasscribe does with a score and its result: as before there were two apps, and a bass tab is not its to open. */
class BrasscribeProductTest {
    @Test
    fun everyBandScoreIsMadeAndArrangedHereAndABassTabIsNot() {
        Profile.entries.filter { it != Profile.BASS_TAB }.forEach {
            assertTrue(it.id, Product.makes(it.id))
            assertTrue(it.id, Product.arranges(it))
        }
        assertFalse(Product.makes("bass-tab"))
        assertFalse(Product.arranges(Profile.BASS_TAB))
    }

    @Test
    fun aTranscriptionIsFollowedByCheckTheNotes() {
        Profile.entries.forEach {
            assertEquals(it.id, Screen.REVIEW, Product.afterTranscription(TranscriptionResult(null, "<score-partwise/>", it, onDevice = false)))
        }
    }
}
