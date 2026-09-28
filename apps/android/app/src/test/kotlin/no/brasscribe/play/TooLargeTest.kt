package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/** Running out of memory, however it arrives, gets the "too big" problem, not the raw exception. */
class TooLargeTest {
    private val owners = "Failed to allocate a 8208 byte allocation with 201088 free bytes and 196KB until OOM, " +
        "target footprint 536870912, growth limit 536870912"

    @Test
    fun theOwnersErrorIsTooLarge() {
        assertTrue(PlayViewModel.isTooLarge(OutOfMemoryError(owners)))
        // As an HTTP client reports it: the message alone, wrapped.
        assertTrue(PlayViewModel.isTooLarge(IOException(owners)))
    }

    @Test
    fun anOutOfMemoryErrorAsCauseOrSuppressed() {
        assertTrue(PlayViewModel.isTooLarge(IOException("canceled due to java.lang.OutOfMemoryError", OutOfMemoryError())))
        assertTrue(PlayViewModel.isTooLarge(IOException("canceled").apply { addSuppressed(OutOfMemoryError("x")) }))
        assertTrue(PlayViewModel.isTooLarge(RuntimeException(IOException("write failed", OutOfMemoryError()))))
    }

    @Test
    fun otherErrorsAreNot() {
        assertFalse(PlayViewModel.isTooLarge(IOException("connection reset")))
        assertFalse(PlayViewModel.isTooLarge(IllegalStateException("job failed")))
        // A cycle of causes ends.
        val a = IOException("a"); val b = IOException("b", a); a.initCause(b)
        assertFalse(PlayViewModel.isTooLarge(a))
    }

    @Test
    fun readLimitedStopsAtTheLimit() {
        assertEquals(10, PlayViewModel.readLimited(ByteArray(10).inputStream(), 10).size)
        assertTrue(runCatching { PlayViewModel.readLimited(ByteArray(1 shl 17).inputStream(), 1000) }.isFailure)
    }
}
