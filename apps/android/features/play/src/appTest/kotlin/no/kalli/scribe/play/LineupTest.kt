package no.kalli.scribe.play

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import no.kalli.scribe.model.Composition
import no.kalli.scribe.model.CompositionJson
import no.kalli.scribe.model.KeySig
import no.kalli.scribe.model.Lang
import no.kalli.scribe.model.Meter
import no.kalli.scribe.model.Note
import no.kalli.scribe.model.Voice
import no.kalli.scribe.model.VoiceRole
import no.kalli.scribe.play.ui.PartNames
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LineupTest {
    /** Every lineup, with the engine's and the core's name: exhaustive, so a new lineup must be added here. */
    private fun expected(l: Lineup): Pair<String, String> = when (l) {
        Lineup.FULL -> "full" to "band"
        Lineup.MINIMAL -> "minimal" to "minimal"
        Lineup.QUARTET -> "quartet" to "quartet"
    }

    @Test
    fun everyLineupHasItsEngineAndCoreName() {
        for (l in Lineup.entries) {
            val (engine, core) = expected(l)
            assertEquals("$l engine", engine, l.engine)
            assertEquals("$l core", core, l.core)
            assertEquals("$l core options", core, OutputOptions(lineup = l).toCore().lineup)
            assertEquals(l, Lineup.of(l.engine))
            assertEquals(l, Lineup.of(l.core))
        }
        for (name in listOf(Lineup.QUARTET.engine, Lineup.QUARTET.core)) {
            assertNotEquals("full", name)
            assertNotEquals("band", name)
        }
        assertNull(Lineup.of("quintet"))
    }

    @Test
    fun theRecordedLineupComesFromTheComposition() {
        val c = composition(JsonObject(mapOf("lineup" to JsonPrimitive("quartet"), "difficulty" to JsonPrimitive("easier"))))
        assertEquals(Lineup.QUARTET, Lineup.recorded(c))
        assertNull(Lineup.recorded(composition(null)))
        // The arrangement survives a round trip through the app's model.
        assertEquals(c.arrangement, CompositionJson.decode(CompositionJson.encode(c)).arrangement)
        // The lineup recorded is the one given: the Output screen gives the one that is made.
        assertEquals(Lineup.MINIMAL, Lineup.recorded(composition(null).arrangedFor(Lineup.MINIMAL, "faithful")))
        assertEquals(Lineup.QUARTET, Lineup.recorded(composition(null).arrangedFor(Lineup.QUARTET, "faithful")))
    }

    @Test
    fun aTakeWithoutLayersIsMadeForTheSmallBand() {
        val band = composition(null)
        assertFalse(band.fullBandMade)
        assertEquals(Lineup.MINIMAL, Lineup.FULL.madeFor(band.fullBandMade))
        assertEquals(Lineup.QUARTET, Lineup.QUARTET.madeFor(false))
        val layered = band.copy(voices = band.voices.map { it.copy(layer = "solo") })
        assertTrue(layered.fullBandMade)
        assertEquals(Lineup.FULL, Lineup.FULL.madeFor(layered.fullBandMade))
    }

    @Test
    fun myPartIsTheLineupsLead() {
        assertEquals(0, leadPartIndex(Lineup.QUARTET_PARTS, Lineup.QUARTET))
        assertEquals(0, leadPartIndex(Lineup.QUARTET_PARTS))
        assertEquals(1, leadPartIndex(listOf("Soprano Cornet", "Solo Cornet", "Repiano Cornet"), Lineup.FULL))
        assertEquals(0, leadPartIndex(listOf("Trumpet")))
        assertEquals(Lineup.QUARTET, Lineup.ofParts(Lineup.QUARTET_PARTS))
        assertNull(Lineup.ofParts(listOf("Solo Cornet", "Euphonium")))
    }

    private fun composition(arrangement: JsonObject?) = Composition(
        "T", listOf(Voice("melody", VoiceRole.MELODY, listOf(Note(70, 0, 24)))), listOf(Meter(0, 4)), listOf(KeySig(0, -2)),
        arrangement = arrangement,
    )
}
