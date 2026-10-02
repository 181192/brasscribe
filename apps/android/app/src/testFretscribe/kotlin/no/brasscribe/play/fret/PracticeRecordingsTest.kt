package no.brasscribe.play.fret

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** The recordings kept on the phone for practising ([PracticeRecordings]): one to a song, by its job on the computer. */
class PracticeRecordingsTest {
    private val dir: File = Files.createTempDirectory("recordings").toFile()
    private val store = PracticeRecordings(File(dir, "kept"))

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    private fun take(bytes: Int): File = File(dir, "take.wav").apply { writeBytes(ByteArray(bytes) { it.toByte() }) }

    @Test
    fun aRecordingInHandIsCopiedAndFoundAgain() {
        assertNull(store.find("job-1"))
        val take = take(1000)
        val kept = store.keep("job-1", take)
        assertTrue("the copy is the store's own file", kept != take && kept.isFile)
        assertEquals(1000L, kept.length())
        // The take can go: the song still has its recording.
        take.delete()
        assertEquals(kept, store.find("job-1"))
        // Kept once: the same recording again is the same file.
        assertEquals(kept, store.keep("job-1", take(1000)))
        assertNull(store.find("job-2"))
    }

    @Test
    fun aRecordingBeingFetchedIsNotThereUntilItIsWhole() {
        val part = store.arriving("job-1")!!
        part.writeBytes(ByteArray(10))
        assertNull("half a recording is no recording", store.find("job-1"))
        val whole = store.arrived("job-1")
        assertNotNull(whole)
        assertEquals(whole, store.find("job-1"))
        // One that came empty is dropped.
        store.arriving("job-2")!!.writeBytes(ByteArray(0))
        assertNull(store.arrived("job-2"))
        assertNull(store.find("job-2"))
    }

    @Test
    fun aSongThatIsGoneTakesItsRecordingWithIt() {
        store.keep("job-1", take(10))
        store.keep("job-2", take(20))
        store.arriving("job-3")!!.writeBytes(ByteArray(5))
        store.prune(setOf("job-2"))
        assertNull(store.find("job-1"))
        assertNotNull(store.find("job-2"))
        assertEquals(listOf("job-2"), File(dir, "kept").list()!!.toList())
    }

    @Test
    fun aJobsIdNeverLeavesTheFolder() {
        val kept = store.keep("../../outside", take(10))
        assertEquals(File(dir, "kept"), kept.parentFile)
        // An id with nothing to name a file by keeps nothing.
        val take = take(10)
        assertEquals(take, store.keep("/..", take))
        assertNull(store.find("/.."))
    }
}
