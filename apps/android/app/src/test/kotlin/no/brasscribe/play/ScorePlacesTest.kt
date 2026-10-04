package no.brasscribe.play

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Where each score was left in practice ([ScorePlaces]): kept on the phone by the score's id, and gone with the score. */
class ScorePlacesTest {
    private val dir: File = Files.createTempDirectory("score-practice").toFile()
    private val places = ScorePlaces(File(dir, "places"))
    private val one = "0b6f4f1e-2a9c-4a53-9d0e-6f1c2b3a4d5e"
    private val two = "7c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f"

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    @Test
    fun aPlaceIsKeptAndReadBack() {
        assertNull(places.read(one))
        places.save(one, ScorePlace(10, 70, 9..10))
        places.save(two, ScorePlace(1, 100, null))
        assertEquals(ScorePlace(10, 70, 9..10), places.read(one))
        assertEquals(ScorePlace(1, 100, null), places.read(two))
        // The latest is what is kept, and nothing is left half-written beside it.
        places.save(one, ScorePlace(3, 60, 2..2))
        assertEquals(ScorePlace(3, 60, 2..2), places.read(one))
        assertEquals(listOf(one, two).sorted(), File(dir, "places").list()!!.sorted())
    }

    @Test
    fun whatCantBeReadIsNoPlace() {
        File(dir, "places").mkdirs()
        fun kept(text: String): ScorePlace? { File(dir, "places/$one").writeText(text); return places.read(one) }
        assertNull(kept(""))
        assertNull(kept("bar"))
        assertNull(kept("Infinity 100"))
        assertNull(kept("NaN 100"))
        assertNull(kept("-3 100"))
        assertNull(kept("0 100"))
        assertNull(kept("4.5 100"))
        assertNull(kept("4 1000"))
        assertNull(kept("4 Infinity"))
        assertNull(kept("99999999999 100"))
        // A repeat that is no range is left out; the rest stays.
        assertEquals(ScorePlace(4, 80, null), kept("4 80 9 2"))
        assertEquals(ScorePlace(4, 80, null), kept("4 80 Infinity 9"))
        // A name that is not a score's id is never a file.
        places.save("../outside", ScorePlace(1, 100, null))
        assertEquals(false, File(dir, "outside").exists())
        assertNull(places.read("../outside"))
    }

    @Test
    fun aScoreThatLeavesTakesItsPlaceWithIt() {
        places.save(one, ScorePlace(5, 75, null))
        places.save(two, ScorePlace(6, 75, null))
        places.forget(one)
        assertNull(places.read(one))
        places.save(one, ScorePlace(5, 75, null))
        // Only a score that is gone loses its place; nothing is pruned for a score that is still there.
        places.prune { it == one || it == two }
        assertEquals(ScorePlace(5, 75, null), places.read(one))
        File(dir, "places/$two.part").writeText("1 100")
        places.prune { it == two }
        assertNull(places.read(one))
        assertEquals(ScorePlace(6, 75, null), places.read(two))
        assertEquals(listOf(two), File(dir, "places").list()!!.toList())
    }
}
