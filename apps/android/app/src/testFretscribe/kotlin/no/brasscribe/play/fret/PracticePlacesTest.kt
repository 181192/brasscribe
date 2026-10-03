package no.brasscribe.play.fret

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Where each song was left in practice ([PracticePlaces]): kept on the phone by the song's job, and gone with the song. */
class PracticePlacesTest {
    private val dir: File = Files.createTempDirectory("practice").toFile()
    private val places = PracticePlaces(File(dir, "places"))

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    @Test
    fun aPlaceIsKeptAndReadBack() {
        assertNull(places.read("job-1"))
        places.save("job-1", PracticePlace(12.25, 70, RepeatBars(8, 9)))
        places.save("job-2", PracticePlace(0.0, 100, null))
        assertEquals(PracticePlace(12.25, 70, RepeatBars(8, 9)), places.read("job-1"))
        assertEquals(PracticePlace(0.0, 100, null), places.read("job-2"))
        // The latest is what is kept.
        places.save("job-1", PracticePlace(3.5, 60, RepeatBars(2, 2)))
        assertEquals(PracticePlace(3.5, 60, RepeatBars(2, 2)), places.read("job-1"))
        assertEquals(listOf(PracticeRecordings.fileName("job-1"), PracticeRecordings.fileName("job-2")).sortedBy { it }, File(dir, "places").list()!!.sorted())
    }

    @Test
    fun whatCantBeReadIsNoPlace() {
        File(dir, "places").mkdirs()
        File(dir, "places/${PracticeRecordings.fileName("job-1")}").writeText("not a place")
        assertNull(places.read("job-1"))
        // A repeat that isn't one is left out; the rest is kept.
        File(dir, "places/${PracticeRecordings.fileName("job-2")}").writeText("4.0 80 5 2")
        assertEquals(PracticePlace(4.0, 80, null), places.read("job-2"))
        assertNull(places.read(""))
    }

    @Test
    fun aSongThatLeftTakesItsPlaceWithIt() {
        places.save("job-1", PracticePlace(1.0, 90, null))
        places.save("job-2", PracticePlace(2.0, 80, null))
        places.prune(setOf("job-2"))
        assertNull(places.read("job-1"))
        assertEquals(PracticePlace(2.0, 80, null), places.read("job-2"))
    }
}
