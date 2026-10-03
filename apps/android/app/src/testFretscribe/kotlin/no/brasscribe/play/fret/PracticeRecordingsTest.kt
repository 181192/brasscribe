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
        val whole = store.arrived("job-1", part)
        assertNotNull(whole)
        assertEquals(whole, store.find("job-1"))
        // One that came empty is dropped.
        val empty = store.arriving("job-2")!!.apply { writeBytes(ByteArray(0)) }
        assertNull(store.arrived("job-2", empty))
        assertNull(store.find("job-2"))
        assertEquals(false, empty.exists())
    }

    @Test
    fun aFetchGivenUpLateNeverTakesTheFileOfTheFetchAfterIt() {
        // Leaving the screen gives the first fetch up; it clears its file only once the next fetch has begun.
        val first = store.arriving("job-1")!!.apply { writeBytes(ByteArray(3)) }
        val second = store.arriving("job-1")!!
        assertTrue("each fetch writes its own file ($first, $second)", first != second)
        second.writeBytes(ByteArray(12))
        store.dropped(first)
        assertTrue("the second fetch's file is still there", second.isFile)
        assertEquals(12L, store.arrived("job-1", second)!!.length())
        assertEquals(12L, store.find("job-1")!!.length())
        // The first one coming to an end after that changes nothing either.
        assertNull(store.arrived("job-1", first))
        assertEquals(12L, store.find("job-1")!!.length())
    }

    @Test
    fun aSongThatIsGoneTakesItsRecordingWithIt() {
        store.keep("job-1", take(10))
        store.keep("job-2", take(20))
        store.arriving("job-3")!!.writeBytes(ByteArray(5))
        store.prune(setOf("job-2"))
        assertNull(store.find("job-1"))
        assertNotNull(store.find("job-2"))
        assertEquals(listOf(store.find("job-2")!!.name), File(dir, "kept").list()!!.toList())
    }

    @Test
    fun aJobsIdNeverLeavesTheFolder() {
        val kept = store.keep("../../outside", take(10))
        assertEquals(File(dir, "kept"), kept.parentFile)
        assertEquals(File(dir, "kept"), store.keep("/..", take(10)).parentFile)
        // No id keeps nothing.
        val take = take(10)
        assertEquals(take, store.keep("", take))
        assertNull(store.find(""))
    }

    @Test
    fun idsThatReadAlikeAreStillTwoSongs() {
        val a = store.keep("job/1", take(10))
        val b = store.keep("job1", take(20))
        assertTrue("two files ($a, $b)", a != b)
        assertEquals(10L, store.find("job/1")!!.length())
        assertEquals(20L, store.find("job1")!!.length())
        // Also past the length a file name keeps of the id.
        val long = "x".repeat(200)
        val c = store.keep(long + "a", take(30))
        val d = store.keep(long + "b", take(40))
        assertTrue(c != d && c.name.length < 100)
        assertEquals(30L, store.find(long + "a")!!.length())
    }

    @Test
    fun whatATryLeftBehindIsCleared() {
        // A fetch that stopped half way: its part is gone when it is given up, and when the songs are gone through.
        val again = store.arriving("job-1")!!
        again.writeBytes(ByteArray(7))
        store.dropped(again)
        assertEquals(false, again.exists())
        store.arriving("job-1")!!.writeBytes(ByteArray(7))
        store.arriving("job-1")!!.writeBytes(ByteArray(7))
        store.keep("job-2", take(5))
        store.prune(setOf("job-1", "job-2"))
        assertEquals(1, File(dir, "kept").list()!!.size)
        assertNotNull(store.find("job-2"))
        assertTrue(store.room > 0)
    }

    @Test
    fun aRecordingThatDidNotComeSaysWhy() {
        val plenty = 1L shl 30
        assertEquals(RecordingState.GONE, PracticeRecordings.whyNot(no.brasscribe.play.engine.EngineException(404, "gone"), plenty))
        assertEquals(RecordingState.TOO_LARGE, PracticeRecordings.whyNot(no.brasscribe.play.engine.EngineException(413, "too large"), plenty))
        assertEquals(RecordingState.NO_ANSWER, PracticeRecordings.whyNot(no.brasscribe.play.engine.EngineException(500, "broken"), plenty))
        assertEquals(RecordingState.NO_ANSWER, PracticeRecordings.whyNot(java.net.ConnectException("refused"), plenty))
        assertEquals(RecordingState.NO_ANSWER, PracticeRecordings.whyNot(java.io.IOException("the recording came empty"), plenty))
        // The phone is full, or the file could not be made: it is not the computer that is away.
        assertEquals(RecordingState.NO_ROOM, PracticeRecordings.whyNot(java.io.IOException("write failed: ENOSPC"), 1000))
        assertEquals(RecordingState.NO_ROOM, PracticeRecordings.whyNot(java.io.FileNotFoundException("no such directory"), plenty))
        assertEquals(RecordingState.NO_ROOM, PracticeRecordings.whyNot(IllegalStateException("no place to keep the recording"), plenty))
    }

    @Test
    fun aKeptRecordingIsSentAgainNamedForTheKindOfFileItIs() {
        fun kind(vararg head: Int): String = PracticeRecordings.extensionOf(File(dir, "kind").apply { writeBytes(ByteArray(head.size) { head[it].toByte() } + ByteArray(16)) })
        fun kind(text: String, at: Int = 0): String = kind(*(IntArray(at) + text.map { it.code }.toIntArray()))
        assertEquals("wav", kind("RIFF\u0000\u0000\u0000\u0000WAVE"))
        assertEquals("m4a", kind("ftypM4A ", at = 4))
        assertEquals("mp3", kind("ID3"))
        assertEquals("mp3", kind(0xFF, 0xFB, 0x90))
        assertEquals("ogg", kind("OggS"))
        assertEquals("flac", kind("fLaC"))
        assertEquals("webm", kind(0x1A, 0x45, 0xDF, 0xA3))
        // Anything else is taken as it was before there was a name: the computer reads it as a WAV file.
        assertEquals("wav", kind("hello"))
        assertEquals("wav", PracticeRecordings.extensionOf(File(dir, "none")))
        // A kept recording is found by the song's job, under the name the store gives it.
        val kept = store.keep("job-1", File(dir, "take.m4a").apply { writeBytes(IntArray(4).map { 0.toByte() }.toByteArray() + "ftypM4A ".toByteArray()) })
        assertEquals("m4a", PracticeRecordings.extensionOf(kept))
    }
}
