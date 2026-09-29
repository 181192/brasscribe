package no.brasscribe.play

import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class SavedScoreLibraryTest {
    @Test
    fun savesScoreAndRenamesItWithoutLosingComposition() {
        val root = Files.createTempDirectory("brasscribe-library").toFile()
        try {
            val library = SavedScoreLibrary(root)
            val saved = library.save(null, "First take", "solo", "<score-partwise/>", "{\"title\":\"First take\"}")

            val renamed = library.rename(saved.id, "Rehearsal take")

            assertNotNull(renamed)
            assertEquals("Rehearsal take", library.list().single().title)
            assertEquals("<score-partwise/>", library.list().single().musicXml)
            assertEquals("{\"title\":\"First take\"}", library.list().single().compositionJson)
            assertNull(library.rename("missing", "Unused"))

            val fromComputer = library.save(null, "Take", "brass-band", "<x/>", null, jobId = "run-1", evidenceJson = "{}", checked = setOf("melody:3"))
            val renamedComputer = library.rename(fromComputer.id, "Take 2")!!
            assertEquals("run-1", renamedComputer.jobId)
            assertEquals("{}", library.list().first { it.id == fromComputer.id }.evidenceJson)
            assertEquals(setOf("melody:3"), library.list().first { it.id == fromComputer.id }.checked)
            // A note changed on the phone is remembered: the computer's renders are older than the score.
            val changed = library.save(fromComputer.id, "Take 2", "brass-band", "<y/>", null, jobId = "run-1", changedOnPhone = true)
            assertEquals(true, library.list().first { it.id == changed.id }.changedOnPhone)
            assertEquals(true, library.rename(changed.id, "Take 3")!!.changedOnPhone)
            // So is what Brasscribe wrote for each changed note, by its Composition note.
            val was = mapOf("melody@480" to 70, "layer-2@1920" to 55)
            library.save(changed.id, "Take 3", "brass-band", "<y/>", null, jobId = "run-1", changedOnPhone = true, reviewChanges = was)
            assertEquals(was, library.list().first { it.id == changed.id }.reviewChanges)
            assertEquals(was, library.rename(changed.id, "Take 4")!!.reviewChanges)
            library.save(changed.id, "Take 4", "brass-band", "<y/>", null, jobId = "run-1", changedOnPhone = true)
            assertEquals(emptyMap<String, Int>(), library.list().first { it.id == changed.id }.reviewChanges)
            library.delete(fromComputer.id)
            assertEquals(1, library.list().size)
        } finally {
            root.deleteRecursively()
        }
    }
}