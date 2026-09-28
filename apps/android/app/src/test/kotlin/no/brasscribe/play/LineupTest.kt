package no.brasscribe.play

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.CompositionJson
import no.brasscribe.play.model.KeySig
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.Meter
import no.brasscribe.play.model.Note
import no.brasscribe.play.model.Voice
import no.brasscribe.play.model.VoiceRole
import no.brasscribe.play.ui.PartNames
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
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
        // A take without layers is arranged for the small band when the full band is asked for.
        assertEquals(Lineup.MINIMAL, Lineup.recorded(composition(null).arrangedFor(Lineup.FULL, "faithful")))
        assertEquals(Lineup.QUARTET, Lineup.recorded(composition(null).arrangedFor(Lineup.QUARTET, "faithful")))
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
