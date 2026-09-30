package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class RestoredStateTest {
    @Test
    fun theSourceKeepsItsNameKindLengthAndFile() {
        val s = SavedSource("Take 1 | band\nsecond line", SourceKind.MICROPHONE, 12.5, File("/cache/takes/take-1.wav"))
        assertEquals(s, SavedSource.decode(s.encode()))
        val score = SavedSource("Old Hundredth", SourceKind.SCORE, 0.0, null)
        assertEquals(score, SavedSource.decode(score.encode()))
        assertNull(score.toSource().audio)
        assertNull(SavedSource.decode("nonsense"))
    }

    @Test
    fun aScreenThatCannotBeResumedGoesBackToTheOneBefore() {
        assertEquals(listOf(Screen.HOME), RestoredStack.plain(listOf(Screen.HOME, Screen.RECORD), hasSource = false))
        assertEquals(listOf(Screen.HOME, Screen.PROFILE),
            RestoredStack.plain(listOf(Screen.HOME, Screen.PROFILE, Screen.TRANSCRIBE), hasSource = true))
        assertEquals(listOf(Screen.HOME), RestoredStack.plain(listOf(Screen.HOME, Screen.PROFILE, Screen.PROBLEM), hasSource = false))
    }

    @Test
    fun theScoreScreensComeBackOnceTheScoreIsRead() {
        val stack = listOf(Screen.HOME, Screen.SCORE, Screen.EXPORT)
        assertTrue(RestoredStack.needsScore(stack))
        assertEquals(listOf(Screen.HOME), RestoredStack.plain(stack, hasSource = false))
        assertEquals(stack, RestoredStack.withScore(stack, hasSource = false))
        assertFalse(RestoredStack.needsScore(listOf(Screen.HOME, Screen.SETTINGS, Screen.COMPANION)))
        assertEquals(listOf(Screen.HOME, Screen.SETTINGS, Screen.COMPANION),
            RestoredStack.plain(listOf(Screen.HOME, Screen.SETTINGS, Screen.COMPANION), hasSource = false))
    }

    @Test
    fun theFirstRunQuestionComesBackButNotOneOpenedFromSettings() {
        assertEquals(listOf(Screen.WHAT_DO_YOU_PLAY), RestoredStack.plain(listOf(Screen.WHAT_DO_YOU_PLAY), hasSource = false))
        assertEquals(listOf(Screen.HOME, Screen.SETTINGS),
            RestoredStack.plain(listOf(Screen.HOME, Screen.SETTINGS, Screen.WHAT_DO_YOU_PLAY), hasSource = false))
        assertEquals(listOf(Screen.HOME), RestoredStack.plain(emptyList(), hasSource = false))
    }
}
