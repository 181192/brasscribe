package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/** Recordings kept in Your scores before they have a score: kept, listed again after a restart, deleted with their file. */
class KeptRecordingStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun take(name: String = "take-1.wav", bytes: Int = 1000): File =
        File(tmp.root, "cache/takes").apply { mkdirs() }.resolve(name).apply { writeBytes(ByteArray(bytes) { 7 }) }

    private fun store() = KeptRecordingStore(File(tmp.root, "no_backup/kept-recordings"))

    @Test
    fun aKeptTakeMovesOutOfTheCacheAndIsListedAfterARestart() {
        val take = take()
        val kept = store().keep(take, "Recording 3 Oct 14:02", SourceKind.MICROPHONE, 754.5, now = 1000L)
        assertFalse("the cache's copy is gone", take.exists())
        assertTrue(kept.file.isFile)
        assertEquals(1000L, kept.file.length())
        assertEquals("wav", kept.file.extension)
        // A new store over the same folder (the app was closed and opened again) lists it as it was kept.
        val again = store().list().single()
        assertEquals(kept, again)
        assertEquals("Recording 3 Oct 14:02", again.title)
        assertEquals(SourceKind.MICROPHONE, again.kind)
        assertEquals(754.5, again.seconds, 0.0)
        assertEquals(kept, store().entryOf(kept.file))
    }

    @Test
    fun keepingAKeptRecordingAgainKeepsItWhereItIs() {
        val s = store()
        val first = s.keep(take(), "Band practice", SourceKind.FILE, 60.0, now = 1L)
        val second = s.keep(first.file, "Band practice", SourceKind.FILE, 60.0, now = 2L)
        assertEquals(first.id, second.id)
        assertEquals(first.file, second.file)
        assertEquals(listOf(2L), s.list().map { it.updated })
    }

    @Test
    fun theNewestComesFirst() {
        val s = store()
        s.keep(take("a.wav"), "Older", SourceKind.FILE, 1.0, now = 1L)
        s.keep(take("b.m4a"), "Newer", SourceKind.VIDEO, 2.0, now = 2L)
        assertEquals(listOf("Newer", "Older"), s.list().map { it.title })
        assertEquals("m4a", s.list().first().file.extension)
    }

    @Test
    fun aRecordingWithAScoreLeavesTheListAndItsFileGoesOnceItIsNotInHand() {
        val s = store()
        val kept = s.keep(take(), "Chorale", SourceKind.FILE, 30.0)
        s.forget(kept.id)
        assertTrue(s.list().isEmpty())
        assertNull(s.entryOf(kept.file))
        assertTrue("still in store", s.owns(kept.file))
        // While it is the recording in hand it stays (What is this? under the score can send it again).
        s.prune(inUse = kept.file)
        assertTrue(kept.file.isFile)
        s.prune(inUse = null)
        assertFalse(kept.file.exists())
        assertFalse(kept.file.parentFile!!.exists())
    }

    @Test
    fun deletingItRemovesTheFile() {
        val s = store()
        val kept = s.keep(take(), "Chorale", SourceKind.FILE, 30.0)
        val other = s.keep(take("other.wav"), "Other", SourceKind.FILE, 30.0)
        s.delete(kept.id)
        assertFalse(kept.file.exists())
        assertEquals(listOf(other), s.list())
        assertEquals(other.file.length(), s.bytes())
    }

    @Test
    fun aFileOutsideTheStoreIsNotItsOwnAndThePhonesScoresAreNeverTouched() {
        val scores = SavedScoreLibrary(File(tmp.root, "files/scores"))
        val score = scores.save(null, "Old Hundredth", "brass-band", "<score-partwise/>", null)
        val s = store()
        assertFalse(s.owns(take()))
        assertNull(s.entryOf(take()))
        s.keep(take("x.wav"), "X", SourceKind.FILE, 1.0)
        s.prune(inUse = null)
        assertEquals(listOf(score.id), scores.list().map { it.id })
        assertEquals("<score-partwise/>", scores.content(score.id)?.musicXml)
    }

    @Test
    fun aRecordingFoundWithoutDetailsIsListedAgainAndAFolderWithoutARecordingIsCleared() {
        val root = File(tmp.root, "no_backup/kept-recordings")
        val orphan = File(root, "orphan").apply { mkdirs() }
        File(orphan, "recording.wav").writeBytes(ByteArray(10))
        File(orphan, "kept.properties.tmp").writeText("title=Half")
        val empty = File(root, "empty").apply { mkdirs() }
        File(empty, "kept.properties").writeText("title=Never moved in\nfile=recording.wav\n")
        val s = store()
        assertTrue(s.list().isEmpty())
        s.prune(inUse = null)
        assertFalse("nothing to lose there", empty.exists())
        val back = s.list().single()
        assertEquals("orphan", back.id)
        assertEquals(10L, back.file.length())
    }

    /** The file operations of a keep, each named; [at] fails (an exception, or a rename that returns false) or ends the process there. */
    private class Steps(val at: String, val dies: Boolean = false, val renameAcross: Boolean = true) : KeptRecordingStore.Files() {
        class Died : Error()
        var reached = false
        private fun step(name: String): Boolean {
            if (name != at) return true
            reached = true
            if (dies) throw Died()
            return false
        }
        override fun write(file: File, details: java.util.Properties) {
            if (!step("write details")) throw java.io.IOException("disk full")
            super.write(file, details)
        }
        override fun rename(from: File, to: File): Boolean {
            val name = when {
                to.name == "kept.properties" -> "rename details"
                from.name.endsWith(".tmp") -> "rename copy"
                else -> "move recording"
            }
            // Across file systems a rename cannot move the recording: it is copied instead.
            if (name == "move recording" && !renameAcross) return false
            return step(name) && super.rename(from, to)
        }
        override fun copy(from: File, to: File) {
            if (!step("copy")) throw java.io.IOException("disk full")
            super.copy(from, to)
        }
        override fun delete(file: File): Boolean = step(if (file.isDirectory) "clear folder" else "delete original") && super.delete(file)
    }

    private fun storeWith(steps: Steps) = KeptRecordingStore(File(tmp.root, "no_backup/kept-recordings"), steps)

    @Test
    fun aKeepThatFailsLeavesTheRecordingWhereItWasAndListsNothing() {
        for ((at, across) in listOf("write details" to true, "rename details" to true, "copy" to false, "rename copy" to false)) {
            val take = take("take-$at.wav")
            val steps = Steps(at, renameAcross = across)
            val failed = runCatching { storeWith(steps).keep(take, "Band practice", SourceKind.FILE, 2.0) }
            assertTrue(at, steps.reached)
            assertTrue(at, failed.isFailure)
            assertTrue("$at: the recording is where it was", take.isFile)
            assertEquals(at, 1000L, take.length())
            assertTrue(at, store().list().isEmpty())
            assertTrue("$at: no folder left behind", File(tmp.root, "no_backup/kept-recordings").listFiles().orEmpty().isEmpty())
        }
    }

    @Test
    fun aRecordingThatCannotBeRenamedInIsCopiedInWhole() {
        val take = take()
        val kept = storeWith(Steps("none", renameAcross = false)).keep(take, "Band practice", SourceKind.FILE, 2.0)
        assertFalse(take.exists())
        assertEquals(1000L, kept.file.length())
        assertEquals(listOf(kept), store().list())
    }

    @Test
    fun theProcessEndingAtAnyStepLosesNoRecording() {
        val points = listOf("write details" to true, "rename details" to true, "move recording" to true,
            "copy" to false, "rename copy" to false, "delete original" to false)
        for ((at, across) in points) {
            File(tmp.root, "no_backup").deleteRecursively()
            val take = take("take.wav")
            val steps = Steps(at, dies = true, renameAcross = across)
            assertTrue(at, runCatching { storeWith(steps).keep(take, "Band practice", SourceKind.FILE, 2.0) }.exceptionOrNull() is Steps.Died)
            // The next start: the source still names the take while it is there, and the store is pruned.
            val s = store()
            s.prune(inUse = take.takeIf(File::isFile))
            val kept = s.list()
            assertTrue("$at: the recording is somewhere", take.isFile || kept.isNotEmpty())
            kept.forEach { assertEquals(at, 1000L, it.file.length()) }
            // Pruned again with nothing in hand, still nothing is lost.
            s.prune(inUse = null)
            assertTrue("$at: still somewhere", take.isFile || s.list().isNotEmpty())
        }
    }

    @Test
    fun withATimeLimitARecordingKeptLongerIsDeletedUnlessItIsInHand() {
        val day = 24L * 60 * 60 * 1000
        val s = KeptRecordingStore(File(tmp.root, "no_backup/kept-recordings"), keepFor = 30 * day)
        val now = 100 * day
        val old = s.keep(take("a.wav"), "Old", SourceKind.MICROPHONE, 1.0, now = now - 31 * day)
        val young = s.keep(take("b.wav"), "Young", SourceKind.MICROPHONE, 1.0, now = now - 29 * day)
        val inHand = s.keep(take("c.wav"), "In hand", SourceKind.MICROPHONE, 1.0, now = now - 40 * day)
        s.prune(inUse = inHand.file, now = now)
        assertEquals(listOf("Young", "In hand"), s.list().map { it.title })
        assertFalse(old.file.exists())
        assertTrue(young.file.isFile && inHand.file.isFile)
        // Without a time limit (Brasscribe) nothing is deleted for its age.
        val forever = store()
        forever.prune(inUse = null, now = now + 1000 * day)
        assertEquals(listOf("Young", "In hand"), forever.list().map { it.title })
    }
}
