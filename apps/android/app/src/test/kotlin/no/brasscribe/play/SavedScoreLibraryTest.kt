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
        } finally {
            root.deleteRecursively()
        }
    }
}