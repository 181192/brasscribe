package no.brasscribe.play.core

import kotlinx.serialization.Serializable
import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.BrasscribeJson
import no.brasscribe.play.model.Instrument
import no.brasscribe.play.model.KotlinCoreBridge
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.MidiWriter
import no.brasscribe.play.model.MusicXmlParts
import no.brasscribe.play.model.PartView
import no.brasscribe.play.model.PitchMode
import no.brasscribe.play.model.ScoreNote
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.TimedNote
import no.brasscribe.play.model.TsBar
import no.brasscribe.play.model.TsContext
import no.brasscribe.play.model.TsEvent
import no.brasscribe.play.model.TsPart
import no.brasscribe.play.model.TsSettings
import no.brasscribe.play.model.TsStop
import no.brasscribe.play.model.VoiceRole
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * The Kotlin side of the Rust core on the JVM, against the host build of libbrasscribe_ffi
 * (`cargo build --release -p brasscribe-ffi` in core/). Skips when that library is missing.
 */
class RustCoreBridgeTest {
    private val core: RustCoreBridge? = RustCoreBridge.load()
    private fun core(): RustCoreBridge { assumeTrue("host build of the Rust core not found", core != null); return core!! }
    private val golden = File(System.getProperty("brasscribe.golden") ?: "missing")

    @Serializable
    data class Case(val id: String, val settings: TsSettings, val context: TsContext, val part: TsPart? = null, val bar: TsBar? = null,
                    val event: TsEvent, val expected: Map<String, String>)

    @Serializable
    data class Vectors(val cases: List<Case>)

    @Test
    fun announcerPassesTheConformanceVectorsThroughTheCore() {
        val c = core()
        val file = File("../model/src/test/resources/talking-score-vectors.json")
        val vectors = BrasscribeJson.decodeFromString(Vectors.serializer(), file.readText())
        val failures = mutableListOf<String>()
        for (v in vectors.cases) {
            val stop = TsStop(v.event, v.bar, v.part, keyFifths = 2, totalBars = 128)
            for ((lang, key) in listOf(Lang.EN to "en", Lang.NB to "nb")) {
                val got = c.announce(stop, v.context, v.settings, lang)
                if (got != v.expected.getValue(key)) failures += "${v.id} [$key] want ${v.expected[key]} got $got"
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    @Test
    fun ps13SpellingAndWrittenPitch() {
        val c = core()
        // D major context: the chromatic note between A and B is spelled A-sharp, and in F major B-flat.
        val sharp = c.spell(listOf(0.0, 1.0, 2.0, 3.0, 4.0), listOf(62, 66, 69, 70, 71))
        val flat = c.spell(listOf(0.0, 1.0, 2.0, 3.0), listOf(65, 69, 70, 72))
        assertEquals("B", flat[2].step); assertEquals(-1, flat[2].alter)
        assertEquals(5, sharp.size)
        // Cornet written pitch of concert B-flat 4 is C 5.
        assertEquals(no.brasscribe.play.model.SpelledPitch("C", 0, 5), Instrument.CORNET.written(flat[2]))
    }

    @Test
    fun arrangesASoloTakeForBrassBandWithOptions() {
        val c = core()
        val scale = listOf(70, 72, 74, 75, 77, 79, 81, 82, 81, 79, 77, 75, 74, 72, 70, 70)
        val sw = scale.mapIndexed { i, p -> TimedNote(1.0 + i * 0.5, 1.0 + i * 0.5 + 0.45, p, 0.9, listOf("swiftf0")) }
        val take = SoloTake("Scale", sw, sw, MidiWriter.steadyBeats(1.0, 120.0, 10.0))
        val full = c.arrangeSolo(take, ArrangeOptions())
        assertTrue(full.musicXml.contains("<part-name>Solo Cornet</part-name>"))
        val melody = full.composition.voices.first { it.role == VoiceRole.MELODY }
        assertEquals(scale, melody.notes.sortedBy { it.start }.map { it.pitch })
        assertTrue(full.parts.size >= 10)
        val minimal = c.arrangeSolo(take, ArrangeOptions(lineup = "minimal", difficulty = "easier", transpose = 2))
        assertTrue("minimal lineup has fewer parts", minimal.parts.size < full.parts.size)
        val up = minimal.composition.voices.first { it.role == VoiceRole.MELODY }.notes.sortedBy { it.start }.map { it.pitch }
        assertEquals(scale.map { it + 2 }, up)
    }

    @Test
    fun perPartTalkingScoreOfTheGoldenScore() {
        val c = core()
        assumeTrue(File(golden, "brass-band.musicxml").isFile)
        val doc = c.talkingScore(File(golden, "brass-band.musicxml").readText(), File(golden, "composition.json").readText())
        assertEquals(18, doc.partNames.size)
        val horn = doc.partNames.indexOf("Solo Horn")
        val lines = doc.partLines(horn, Lang.NB, PitchMode.WRITTEN)
        assertTrue(lines.isNotEmpty())
        val html = doc.toHtml(Lang.EN, listOf(horn))
        assertTrue(html.contains("Solo Horn"))
        doc.close()
    }

    @Test
    fun rearrangesACompositionForTheQuartet() {
        val c = core()
        val file = File("../../fixtures/old-hundredth/composition.json")
        assertTrue("fixture ${file.absolutePath}", file.isFile)
        val comp = c.decodeComposition(file.readText())
        val quartet = c.arrangeMusicXmlWith(comp, ArrangeOptions(lineup = "quartet"))
        assertEquals(listOf("1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"), MusicXmlParts.names(quartet))
        val easier = c.arrangeMusicXmlWith(comp, ArrangeOptions(lineup = "quartet", difficulty = "easier"))
        assertEquals(4, MusicXmlParts.names(easier).size)
        // The full band through the options is the same score as the old arranger's.
        assertEquals(c.arrangeMusicXml(comp, "auto"), c.arrangeMusicXmlWith(comp, ArrangeOptions(lineup = "band")))
        assertTrue(MusicXmlParts.names(c.arrangeMusicXmlWith(comp, ArrangeOptions(lineup = "minimal"))).size in 5..10)
    }

    @Test
    fun lineupNamesNeverFallBackToTheBand() {
        assertEquals("quartet", RustCoreBridge.coreLineup("quartet"))
        assertEquals("minimal", RustCoreBridge.coreLineup("minimal"))
        assertEquals("band", RustCoreBridge.coreLineup("full"))
        assertEquals("band", RustCoreBridge.coreLineup("band"))
        assertTrue(runCatching { RustCoreBridge.coreLineup("quintet") }.isFailure)
    }

    @Test
    fun humanizesAPart() {
        val c = core()
        val notes = (0 until 8).map { ScoreNote(it * 24L, 24, it * 0.5, it * 0.5 + 0.5, 72, 80) }
        val played = c.humanize(notes, "Solo Cornet", 0, null)!!
        assertEquals(8, played.size)
        assertTrue("timing moves", played.zip(notes).any { (p, n) -> p.startS != n.startS })
        assertTrue(played.all { kotlin.math.abs(it.startS - notes[played.indexOf(it)].startS) < 0.1 })
    }

    @Test
    fun aScoreParsesItsCompositionOnceForAllParts() {
        assumeTrue(File(golden, "composition.json").isFile)
        val c = core()
        val json = File(golden, "composition.json").readText()
        val parts = listOf("Solo Cornet", "Repiano Cornet", "Flugelhorn", "Solo Horn", "Baritone", "Euphonium", "Eb Bass")
        val notes = (0 until 16).map { ScoreNote(it * 24L, 24, it * 0.5, it * 0.5 + 0.5, 60 + it % 7, 80) }
        // The same text again as a new String (a score reloaded): equal content hits the cache too.
        val t0 = System.nanoTime()
        val shared = parts.mapIndexed { i, p -> c.humanize(notes, p, 0, if (i % 2 == 0) json else String(json.toCharArray()))!! }
        val t1 = System.nanoTime()
        assertEquals("one parse of the composition for ${parts.size} parts", 1, c.performancesBuilt)
        // Identical to a Performance built for each part on its own.
        val alone = parts.map { p -> RustCoreBridge.load()!!.humanize(notes, p, 0, json)!! }
        println("humanize ${parts.size} parts: %d ms with one parse, %d ms with one per part".format((t1 - t0) / 1_000_000, (System.nanoTime() - t1) / 1_000_000))
        assertEquals(alone, shared)
        assertTrue("the composition shapes the result", shared.zip(parts.map { c.humanize(notes, it, 0, null)!! }).any { (a, b) -> a != b })
        // Another composition replaces the cached one.
        c.humanize(notes, "Solo Cornet", 0, json.replaceFirst("{", "{ "))
        assertEquals(2, c.performancesBuilt)
    }

    @Test
    fun partViewSpellsThroughTheCore() {
        val c = core()
        assumeTrue(File(golden, "composition.json").isFile)
        val comp = c.decodeComposition(File(golden, "composition.json").readText())
        val solo = comp.voices.first { it.role == VoiceRole.MELODY }
        val rust = PartView(comp, solo, Instrument.CORNET, "Solo Cornet", core = c)
        val kotlin = PartView(comp, solo, Instrument.CORNET, "Solo Cornet", core = KotlinCoreBridge)
        val differ = rust.events.zip(kotlin.events).count { (a, b) -> a.stop.event.written != b.stop.event.written }
        println("golden solo: ${rust.events.size} events, $differ spelled differently by ps13 than the key rule")
        assertNotNull(rust.events.firstOrNull { it.note != null }?.stop?.event?.written)
    }
}
