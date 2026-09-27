package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Calendar
import java.util.Locale

class ScoreTitlesTest {
    private val at = Calendar.getInstance().apply { set(2026, Calendar.SEPTEMBER, 26, 19, 2) }.timeInMillis

    @Test
    fun timestampsBecomeRecordingsAndFilesLoseTheirExtension() {
        assertTrue(ScoreTitles.isTimestamp("20260815_155324"))
        assertTrue(ScoreTitles.isTimestamp("take-1790415563026"))
        assertFalse(ScoreTitles.isTimestamp("Mikkel"))
        assertEquals("Recording, 26 Sep 19:02", ScoreTitles.display("20260815_155324.m4a", at, Locale.US))
        assertEquals("Recording, 26 Sep 19:02", ScoreTitles.display("take-1790415563026.wav", at, Locale.US))
        assertEquals("Abide with Me", ScoreTitles.display("Abide with Me.mp3", at, Locale.US))
        assertEquals("Mikkel — solo cornet & brass band", ScoreTitles.display("Mikkel — solo cornet & brass band (draft)", at, Locale.US))
        assertTrue(ScoreTitles.display("20260815_155324", at, Locale.forLanguageTag("nb")).startsWith("Opptak, 26. sep"))
    }
}
