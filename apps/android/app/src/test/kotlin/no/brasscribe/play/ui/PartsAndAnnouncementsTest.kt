package no.brasscribe.play.ui

import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.KeySig
import no.brasscribe.play.model.KotlinCoreBridge
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.Meter
import no.brasscribe.play.model.Note
import no.brasscribe.play.model.Voice
import no.brasscribe.play.model.VoiceRole
import org.junit.Assert.assertEquals
import org.junit.Test

class PartsAndAnnouncementsTest {
    @Test
    fun defaultPartIsTheSoloCornet() {
        assertEquals(1, defaultPart(listOf("Soprano Cornet", "Solo Cornet", "Repiano Cornet")))
        assertEquals(0, defaultPart(listOf("Trumpet")))
    }

    @Test
    fun reviewListSpeaksEachNoteInContext() {
        val c = Composition(
            "T", listOf(Voice("solo", VoiceRole.MELODY, listOf(Note(70, 0, 24, 0.5, listOf("swiftf0")), Note(72, 24, 24, 0.9)))),
            listOf(Meter(0, 4)), listOf(KeySig(0, -2)),
        )
        // The Norwegian part name is the core's (part_name_nb); here a stand-in for it.
        val core = object : no.brasscribe.play.model.CoreBridge by KotlinCoreBridge {
            override fun partNameNb(name: String) = if (name == "Solo Cornet") "Solokornett" else name
        }
        val view = partViewFor(c, "solo", emptySet(), core)
        assertEquals(
            listOf("Solo Cornet. bar 1, no sharps or flats, beat 1: C 5, quarter note, uncertain", "beat 2: D 5, quarter note"),
            announcements(view, Lang.EN, KotlinCoreBridge),
        )
        assertEquals(
            listOf("Solokornett. takt 1, ingen faste fortegn, slag 1: C 5, fjerdedelsnote, usikker", "slag 2: D 5, fjerdedelsnote"),
            announcements(view, Lang.NB, KotlinCoreBridge),
        )
    }

    /** Home's "N to check" is what Review opens on: one per engine group, only in the parts it grouped. */
    @Test
    fun homeCountsTheSamePlacesAsReview() {
        val f = java.io.File("../../../data/golden/mikkel-arranged-band/composition.json")
        org.junit.Assume.assumeTrue(f.exists())
        val c = no.brasscribe.play.model.CompositionJson.decode(f.readText())
        val groups = c.review!!.size
        val solo = reviewGroups(c, "solo", partViewFor(c, "solo", emptySet(), KotlinCoreBridge)).size
        assertEquals(groups, solo)
        assertEquals(groups, itemsToCheck(c, emptyMap(), KotlinCoreBridge))
    }
}
