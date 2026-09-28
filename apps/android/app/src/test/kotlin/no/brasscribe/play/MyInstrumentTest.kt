package no.brasscribe.play

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import no.brasscribe.play.connection.CredentialStoreTest.MemoryStore
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.KeySig
import no.brasscribe.play.model.Meter
import no.brasscribe.play.model.Note
import no.brasscribe.play.model.PartSource
import no.brasscribe.play.model.reading
import no.brasscribe.play.model.Seat
import no.brasscribe.play.model.SeatPart
import no.brasscribe.play.model.Voice
import no.brasscribe.play.model.VoiceRole
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** "What do you play?": the stored answer, and "your part" in each lineup (the core's table injected). */
class MyInstrumentTest {
    private val seats = listOf(
        Seat("solo-cornet", "Solo Cornet", "Solokornett", "bb-cornet", "treble", listOf("treble"), -2, tune = true),
        Seat("1st-baritone", "1st Baritone", "1. baryton", "baritone", "treble", listOf("treble", "bass"), -14, tune = false),
        Seat("eb-bass", "E♭ Bass", "Ess-bass", "eb-bass", "treble", listOf("treble", "bass"), -21, tune = false),
        Seat("percussion", "Percussion", "Slagverk", "drum-kit", "percussion", emptyList(), 0, tune = false),
        Seat("euphonium", "Euphonium", "Eufonium", "euphonium", "treble", listOf("treble", "bass"), -14, tune = true),
    )

    @org.junit.Test
    fun anEmptyPartIsNotArranged() {
        assertEquals(PartSource.EMPTY, PartSource.of("empty"))
        assertEquals(R.string.source_empty, no.brasscribe.play.ui.sourceWords(PartSource.EMPTY))
        assertEquals(R.string.explain_empty, no.brasscribe.play.ui.explainOf(PartSource.EMPTY))
        assertEquals(R.string.explain_arranged, no.brasscribe.play.ui.explainOf(PartSource.ARRANGED))
    }

    @org.junit.Test
    fun theReadingDefaultsToTheSeatsOwn() {
        val bassTrombone = Seat("bass-trombone", "Bass Trombone", "Bassbasun", "bass-trombone", "bass", listOf("bass"), 0, tune = false)
        assertEquals("bass", bassTrombone.reading(null))
        assertEquals("treble", seats[1].reading(null))
        assertEquals("bass", seats[1].reading("bass"))
        assertNull(seats[3].reading(null))
    }

    @org.junit.Test
    fun aDrummersSoloTakeIsRefused() {
        org.junit.Assert.assertTrue(percussionSeat(SeatChoice.Player("percussion"), seats))
        org.junit.Assert.assertFalse(percussionSeat(SeatChoice.Player("euphonium"), seats))
        org.junit.Assert.assertFalse(percussionSeat(SeatChoice.Conductor, seats))
        org.junit.Assert.assertFalse(percussionSeat(SeatChoice.NotSet, seats))
    }

    /** A few rows of the core's table (instruments.rs SEAT_PARTS). */
    private val table = mapOf(
        ("minimal" to "1st-baritone") to SeatPart("Euphonium", false, true),
        ("quartet" to "1st-baritone") to SeatPart("Euphonium", false, true),
        ("quartet" to "eb-bass") to SeatPart("Euphonium", false, false),
        ("quartet" to "percussion") to SeatPart(null, false, false),
        ("band" to "1st-baritone") to SeatPart("1st Baritone", true, true),
    )
    private val seatPart = { lineup: String, seat: String -> table[lineup to seat] }

    private val band = listOf("Soprano Cornet", "Solo Cornet", "Repiano Cornet", "1st Baritone", "Euphonium", "E♭ Bass")
    private val minimal = listOf("Solo Cornet", "2nd Cornet", "Solo Horn", "Euphonium", "E♭ Bass")

    private fun resolve(parts: List<String>, lineup: Lineup?, choice: SeatChoice, override: String? = null) =
        YourParts.resolve(parts, lineup, choice, override, seats, seatPart)

    @Test fun storeKeepsTheAnswerAndForgetsNothingElse() {
        val mem = MemoryStore()
        val store = SeatStore(mem)
        assertEquals(SeatChoice.NotSet, store.load())
        store.save(SeatChoice.Player("1st-baritone", "bass"))
        assertEquals(SeatChoice.Player("1st-baritone", "bass"), store.load())
        store.save(SeatChoice.Player("euphonium"))
        assertEquals(SeatChoice.Player("euphonium", null), store.load())
        store.save(SeatChoice.Conductor)
        assertEquals(SeatChoice.Conductor, store.load())
        store.save(SeatChoice.NotSet)
        assertEquals(emptySet<String>(), mem.keys())
    }

    @Test fun notSetKeepsTheLeadAsBefore() {
        assertEquals(YourPart(1), resolve(band, Lineup.FULL, SeatChoice.NotSet))
    }

    @Test fun conductorHasNoPart() {
        assertNull(resolve(band, Lineup.FULL, SeatChoice.Conductor).index)
    }

    @Test fun theSeatsOwnPartInTheFullBand() {
        assertEquals(YourPart(3), resolve(band, Lineup.FULL, SeatChoice.Player("1st-baritone")))
    }

    @Test fun aLineupWithoutTheSeatSaysWhichPartItGave() {
        val p = resolve(minimal, Lineup.MINIMAL, SeatChoice.Player("1st-baritone"))
        assertEquals(3, p.index)
        assertEquals(MappedSeat(Lineup.MINIMAL, seats[1], "Euphonium", true), p.mapped)
        val q = resolve(Lineup.QUARTET_PARTS, Lineup.QUARTET, SeatChoice.Player("eb-bass"))
        assertEquals(3, q.index)
        assertEquals(false, q.mapped!!.sameKey)
    }

    @Test fun percussionInTheQuartetOpensEveryPart() {
        val p = resolve(Lineup.QUARTET_PARTS, Lineup.QUARTET, SeatChoice.Player("percussion"))
        assertNull(p.index)
        assertNull(p.mapped!!.part)
    }

    @Test fun thisScoresPickWins() {
        assertEquals(YourPart(4), resolve(band, Lineup.FULL, SeatChoice.Player("1st-baritone"), override = "Euphonium"))
        assertEquals(YourPart(4), resolve(band, Lineup.FULL, SeatChoice.Conductor, override = "Euphonium"))
    }

    @Test fun aSoloTakeForSomeoneElseIsStillTheOnePart() {
        assertEquals(YourPart(0), resolve(listOf("Euphonium"), Lineup.FULL, SeatChoice.Player("solo-cornet")))
    }

    @Test fun outputOptionsTakeTheSeatAndDropTheDefaultClef() {
        val o = OutputOptions().withSeat(SeatChoice.Player("1st-baritone", "treble"), seats)
        assertEquals("1st-baritone", o.seat)
        assertNull(o.reads)
        assertEquals("bass", OutputOptions().withSeat(SeatChoice.Player("1st-baritone", "bass"), seats).toCore().reads)
        assertNull(OutputOptions().withSeat(SeatChoice.Conductor, seats).seat)
        assertNull(OutputOptions(lead = "seat").toCore().lead)
    }

    @Test fun anEditKeepsTheSeatRecorded() {
        val c = composition(null).arrangedFor(Lineup.FULL, "faithful", seat = "euphonium", reads = "bass", soloTake = true)
        assertEquals("euphonium", c.arrangementString("seat"))
        assertEquals("bass", c.arrangementString("reads"))
        assertEquals("seat", c.arrangementString("lead"))
        assertNull(c.arrangedFor(Lineup.FULL, "faithful").arrangementString("seat"))
    }

    @Test fun leadPartAndTheVoiceYourPartFollows() {
        val c = composition(JsonObject(mapOf("lineup" to JsonPrimitive("band"), "seat" to JsonPrimitive("euphonium"), "lead" to JsonPrimitive("seat"))))
        val parts = listOf("Solo Cornet", "Euphonium")
        val eu = { l: String, s: String -> if (s == "euphonium") SeatPart("Euphonium", true, true) else null }
        assertEquals("Euphonium", YourParts.leadPart(c, parts, eu))
        assertEquals("melody", YourParts.voiceOf("Euphonium", "Euphonium", PartSource.RECORDING, c))
        assertNull(YourParts.voiceOf("Euphonium", "Euphonium", PartSource.ARRANGED, c))
        assertEquals("Solo Cornet", YourParts.leadPart(composition(null), parts, eu))
    }

    private fun composition(arrangement: JsonObject?) = Composition(
        "T", listOf(Voice("melody", VoiceRole.MELODY, listOf(Note(70, 0, 24)))), listOf(Meter(0, 4)), listOf(KeySig(0, -2)),
        arrangement = arrangement,
    )
}
