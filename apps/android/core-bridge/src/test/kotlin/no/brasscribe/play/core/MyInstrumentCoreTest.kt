package no.brasscribe.play.core

import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.CompositionJson
import no.brasscribe.play.model.MusicXmlParts
import no.brasscribe.play.model.PartSource
import no.brasscribe.play.model.SeatPart
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.TimedNote
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** "What do you play?" through the core: the seats, seat → part, where parts come from and the nb names. */
class MyInstrumentCoreTest {
    private val core: RustCoreBridge? = RustCoreBridge.load()
    private fun core(): RustCoreBridge { assumeTrue("host build of the Rust core not found", core != null); return core!! }

    @Test
    fun seatsComeFromTheCoreInScoreOrder() {
        val seats = core().seats()
        assertEquals(19, seats.size)
        assertEquals("soprano-cornet", seats.first().id)
        // The contest band's 18 in score order, then the trumpet (it takes the lead part).
        assertEquals(listOf("percussion", "trumpet"), seats.takeLast(2).map { it.id })
        val baritone = seats.first { it.id == "1st-baritone" }
        assertEquals("1st Baritone", baritone.name)
        assertEquals("1. baryton", baritone.nbName)
        assertEquals(listOf("treble", "bass"), baritone.reads)
        assertEquals(-14, baritone.chromatic)
        assertEquals(listOf("bass"), seats.first { it.id == "bass-trombone" }.reads)
        assertTrue(seats.first { it.id == "percussion" }.reads.isEmpty())
    }

    /** Acceptance §6.4: three spot cases of the one seat → part table. */
    @Test
    fun seatPartSpotCases() {
        val c = core()
        assertEquals(SeatPart("Euphonium", exact = false, sameKey = true), c.seatPart("minimal", "1st-baritone"))
        assertEquals(SeatPart("Euphonium", exact = false, sameKey = false), c.seatPart("quartet", "eb-bass"))
        assertEquals(SeatPart("2nd Cornet", exact = true, sameKey = true), c.seatPart("band", "2nd-cornet"))
        assertEquals(SeatPart("Trumpet", exact = false, sameKey = true, takes = "Solo Cornet"), c.seatPart("band", "trumpet"))
        assertEquals(SeatPart("1st Cornet", exact = false, sameKey = true), c.seatPart("quartet", "trumpet"))
        assertNull(c.seatPart("quartet", "percussion")?.part)
        assertNull(c.seatPart("band", "no-such-seat"))
    }

    @Test
    fun partNamesInNorwegianComeFromTheCore() {
        val c = core()
        assertEquals("1. kornett", c.partNameNb("1st Cornet"))
        assertEquals("Althorn", c.partNameNb("Tenor Horn"))
        assertEquals("Solokornett", c.partNameNb("Solo Cornet"))
        assertEquals("Trompet", c.partNameNb("Trumpet"))
        assertEquals("Strings", c.partNameNb("Strings"))
    }

    /** Engine and saved scores reach the core through the Kotlin Composition: the sources must survive that. */
    @Test
    fun partSourcesSurviveTheKotlinRoundTrip() {
        val c = core()
        val raw = File("../../fixtures/old-hundredth/composition.json").readText()
        val direct = c.partSources(raw)
        assertTrue(direct.isNotEmpty())
        assertEquals(direct, c.partSources(CompositionJson.encode(c.decodeComposition(raw))))
    }

    /** A solo take with a seat is one part, the seat's, from "your recording"; a re-arrangement keeps it. */
    @Test
    fun soloTakeWithASeatIsTheSeatsPart() {
        val c = core()
        val notes = (0 until 16).map { i -> TimedNote(i * 0.5, i * 0.5 + 0.45, listOf(50, 52, 53, 55)[i % 4], 0.9, listOf("swift-f0")) }
        val beats = (0 until 20).joinToString("\n") { i -> "%.3f %d".format(java.util.Locale.ROOT, i * 0.5, i % 4 + 1) }
        val take = SoloTake("Practice", notes, notes, beats)
        val out = c.arrangeSolo(take, ArrangeOptions(seat = "1st-baritone"))
        assertEquals(listOf("1st Baritone"), MusicXmlParts.names(out.musicXml))
        assertEquals(mapOf("1st Baritone" to PartSource.YOUR_RECORDING), c.partSources(out.compositionJson))
        val again = c.arrangeMusicXmlWith(out.composition, ArrangeOptions(seat = "1st-baritone"))
        assertEquals(listOf("1st Baritone"), MusicXmlParts.names(again))
        val bass = c.arrangeSolo(take, ArrangeOptions(seat = "1st-baritone", reads = "bass")).musicXml
        assertTrue("bass clef", bass.contains("<sign>F</sign>"))
    }
}
