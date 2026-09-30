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
            assertEquals("<score-partwise/>", library.content(saved.id)!!.musicXml)
            assertEquals("{\"title\":\"First take\"}", library.content(saved.id)!!.compositionJson)
            assertNull(library.rename("missing", "Unused"))

            val fromComputer = library.save(null, "Take", "brass-band", "<x/>", null, jobId = "run-1", evidenceJson = "{}", checked = setOf("melody:3"))
            val renamedComputer = library.rename(fromComputer.id, "Take 2")!!
            assertEquals("run-1", renamedComputer.jobId)
            assertEquals("{}", library.content(fromComputer.id)!!.evidenceJson)
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
            assertNull(library.content(fromComputer.id))
            assertNull(library.content("../outside"))
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun listingReadsOnlyTheDetails() {
        val root = Files.createTempDirectory("brasscribe-library").toFile()
        try {
            val library = SavedScoreLibrary(root)
            val saved = library.save(null, "Big band score", "brass-band", "<score-partwise/>", "{}", evidenceJson = "{}")
            // A score whose files cannot be read is still listed; it is its content that fails, when opened.
            java.io.File(root, "${saved.id}/score.musicxml").delete()
            assertEquals(listOf("Big band score"), library.list().map { it.title })
            assertEquals(saved.id, library.get(saved.id)?.id)
            assertNull(library.content(saved.id))
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun aDraftKeepsItsFlagAndRecordingThroughSavesAndRenames() {
        val root = Files.createTempDirectory("brasscribe-library").toFile()
        try {
            val library = SavedScoreLibrary(root)
            val take = java.io.File(root.parentFile, "take-${System.nanoTime()}.wav").apply { writeBytes(byteArrayOf(1, 2, 3)) }
            val saved = library.save(null, "Band", "brass-band", "<x/>", "{}", draft = true, recording = take)
            take.delete()
            assertEquals(true, saved.draft)
            assertEquals("recording.wav", saved.recording)
            // A later save (a checked note) has no recording to give: the kept one stays.
            library.save(saved.id, "Band", "brass-band", "<x/>", "{}", checked = setOf("melody:1"), draft = true)
            val renamed = library.rename(saved.id, "Band 2")!!
            assertEquals(true, renamed.draft)
            assertEquals(listOf(1, 2, 3), library.recordingFile(saved.id)!!.readBytes().map { it.toInt() })
            assertEquals(true, library.list().single().draft)
            // A score from before drafts reads as no draft, with no recording.
            val plain = library.save(null, "Solo", "solo", "<x/>", null)
            assertEquals(false, library.get(plain.id)!!.draft)
            assertNull(library.recordingFile(plain.id))
        } finally {
            root.deleteRecursively()
        }
    }
}
