package no.brasscribe.play.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

class CompositionTest {
    private fun tiny(): Composition =
        CompositionJson.decode(javaClass.getResource("/tiny-composition.json")!!.readText())

    private val goldenDir = File(System.getProperty("brasscribe.golden") ?: "missing")

    @Test
    fun decodesAndIgnoresUnknownFields() {
        val c = tiny()
        assertEquals("Tiny solo", c.title)
        assertEquals(5, c.voices.single().notes.size)
        assertEquals(listOf(Articulation.STACCATO), c.voices[0].notes[2].articulations)
        assertEquals(c, CompositionJson.decode(CompositionJson.encode(c)))
    }

    @Test
    fun uncertaintyThresholds() {
        assertEquals(Uncertainty.CONFIDENT, Uncertainty.of(0.7))
        assertEquals(Uncertainty.UNCERTAIN, Uncertainty.of(0.69))
        assertEquals(Uncertainty.UNCERTAIN, Uncertainty.of(0.4))
        assertEquals(Uncertainty.VERY_UNCERTAIN, Uncertainty.of(0.39))
    }

    @Test
    fun tickMapBarsAndSeconds() {
        val m = TickMap(tiny())
        assertEquals(96, m.ticksPerBar(0))
        assertEquals(1, m.barOf(0))
        assertEquals(1, m.barOf(95))
        assertEquals(2, m.barOf(96))
        assertEquals(0, m.barOf(-1))
        assertEquals(96, m.barStart(2))
        assertEquals(4, m.totalBars)
        assertEquals(1.0, m.secondsAt(0), 1e-9)
        assertEquals(1.25, m.secondsAt(12), 1e-9)
        assertEquals(5.5, m.secondsAt(24 * 9), 1e-9) // past the last beat: extrapolated
        assertEquals(0.5, m.secondsAt(-24), 1e-9) // before the first beat: extrapolated
        assertEquals(36, m.tickAt(m.secondsAt(36)))
    }

    @Test
    fun goldenTickMapFollowsTheBeatList() {
        // Invariants only: the golden output is re-saved when the engine improves.
        assumeTrue("golden output not present", File(goldenDir, "composition.json").exists())
        val c = CompositionJson.decode(File(goldenDir, "composition.json").readText())
        assertTrue(c.voices.isNotEmpty())
        val m = TickMap(c)
        // Tick t sits at beat index t / tpb + first_downbeat of the beat list.
        for (i in listOf(0, 1, c.beatTimes.size / 2, c.beatTimes.size - 1)) {
            assertEquals(c.beatTimes[i], m.secondsAt((i - c.firstDownbeat) * c.ticksPerBeat), 1e-9)
        }
        // Every melody note maps to a time in order.
        val melody = c.voices.first { it.role == VoiceRole.MELODY }.notes
        val times = melody.map { m.secondsAt(it.start) }
        assertEquals(times.sorted(), times)
        c.freeRegions.forEach { r -> assertTrue(r.end > r.start && r.endS > r.startS) }
    }

    @Test
    fun negativeFirstDownbeatExtrapolatesBeforeTheFirstBeat() {
        // The recording starts four beats after tick 0 (the first Mikkel golden output had this shape).
        val c = tiny().copy(firstDownbeat = -4)
        val m = TickMap(c)
        assertEquals(c.beatTimes[0], m.secondsAt(96), 1e-9)
        assertEquals(c.beatTimes[4], m.secondsAt(192), 1e-9)
        assertEquals(c.beatTimes[0] - 0.5 * 0.5, m.secondsAt(84), 1e-9)
        assertEquals(84, m.tickAt(m.secondsAt(84)))
    }

    @Test
    fun spelling() {
        assertEquals(SpelledPitch("B", -1, 4), SpelledPitch.spell(70, -2))
        assertEquals(SpelledPitch("F", 1, 4), SpelledPitch.spell(66, 2))
        assertEquals(SpelledPitch("E", -1, 5), SpelledPitch.spell(75, 0))
        // B-flat cornet: concert B-flat 4 is written C 5; concert B-flat major is written C major.
        assertEquals(SpelledPitch("C", 0, 5), Instrument.CORNET.spellWritten(70, -2))
        assertEquals(0, Instrument.CORNET.writtenFifths(-2))
        assertEquals(3, Instrument.TENOR_HORN.writtenFifths(0))
        assertEquals(3, Instrument.EB_BASS.writtenFifths(0))
        assertEquals(60, SpelledPitch("C", 0, 4).midi)
        assertEquals(59, SpelledPitch("C", -1, 4).midi)
        assertEquals(SpelledPitch("C", -1, 4), SpelledPitch("C", -1, 4).let { SpelledPitch(it.step, it.alter, it.octave) })
    }

    @Test
    fun partViewAnnouncesTinySolo() {
        val c = tiny()
        val view = PartView(c, c.voices[0], Instrument.CORNET, "Solo Cornet", "Solokornett")
        val first = view.announce(0, null, TsSettings(), Lang.EN, KotlinCoreBridge)
        assertEquals("Solo Cornet. bar 1, no sharps or flats, beat 1: C 5, eighth note, uncertain", first)
        val second = view.announce(1, view.events[0], TsSettings(), Lang.EN, KotlinCoreBridge)
        assertEquals("beat 1 and: D 5, eighth note", second)
        val third = view.announce(2, view.events[1], TsSettings(), Lang.NB, KotlinCoreBridge)
        assertEquals("slag 2: E 5, halvnote, staccato, svært usikker", third)
        // The note at tick 84 (beat 4 and) is a dotted quarter crossing into bar 2.
        val fourth = view.announce(3, view.events[2], TsSettings(), Lang.EN, KotlinCoreBridge)
        assertEquals("beat 4 and: F 5, eighth note, tied to quarter note in bar 2", fourth)
        // Bar 3 is empty: a bar-rest event sits between bar 2 and bar 4.
        val rest = view.events[4]
        assertEquals("bar-rest", rest.stop.event.kind)
        assertEquals("bar 3: rest, whole bar", view.announce(4, view.events[3], TsSettings(), Lang.EN, KotlinCoreBridge))
    }

    @Test
    fun aPartRestingThroughThePickupRestsFromThePickupOn() {
        val c = tiny()
        val solo = c.voices[0]
        // The solo starts half a beat before bar 1; the other part comes in where the solo's last note is.
        val lead = solo.copy(notes = listOf(solo.notes[0].copy(start = -12, dur = 12)) + solo.notes)
        val late = solo.copy(notes = listOf(solo.notes.last()))
        val withPickup = c.copy(voices = listOf(lead, late))
        val entry = PartView(withPickup, late, Instrument.CORNET, "2nd Cornet").tickMap.barOf(solo.notes.last().start)

        val first = PartView(withPickup, lead, Instrument.CORNET, "Solo Cornet")
        assertEquals(PICKUP_BAR, first.events[0].bar)
        assertTrue(first.announce(0, null, TsSettings(), Lang.EN, KotlinCoreBridge).contains("pickup, no sharps or flats, beat 4 and: "))

        val resting = PartView(withPickup, late, Instrument.CORNET, "2nd Cornet")
        val rest = resting.events[0]
        assertEquals("bar-rest", rest.stop.event.kind)
        assertEquals(PICKUP_BAR, rest.bar)
        assertEquals(entry, rest.stop.event.bars) // the pickup and every bar before the entry
        val said = resting.announce(0, null, TsSettings(), Lang.EN, KotlinCoreBridge)
        assertTrue(said, said.endsWith("pickup and bars 1 to ${entry - 1}: rest, ${entry - 1} bars"))
        assertTrue(resting.announce(0, null, TsSettings(), Lang.NB, KotlinCoreBridge).endsWith("opptakt og takt 1 til ${entry - 1}: pause, ${entry - 1} takter"))
        assertEquals(entry, resting.events[1].bar)

        // Without a pickup in the piece the rest starts at bar 1, as before.
        val plain = PartView(c.copy(voices = listOf(solo, late)), late, Instrument.CORNET, "2nd Cornet")
        assertEquals(1, plain.events[0].bar)
        assertEquals(entry - 1, plain.events[0].stop.event.bars)
    }

    @Test
    fun freeTimeRegionIsAnnouncedOnEntryAndExit() {
        val c = tiny().copy(freeRegions = listOf(FreeRegion(0, 96, 1.0, 3.0, 60.0)))
        val view = PartView(c, c.voices[0], Instrument.CORNET, "Solo Cornet")
        val said = view.events.indices.map { i -> view.announce(i, view.events.getOrNull(i - 1), TsSettings(), Lang.EN, KotlinCoreBridge) }
        assertEquals("Ad lib, free time, bars 1 to 1, about 2 seconds. Solo Cornet. bar 1, no sharps or flats, at 1 seconds: C 5, eighth note, uncertain", said[0])
        assertEquals("at 1 seconds: D 5, eighth note", said[1])
        assertTrue(said.drop(1).count { it.contains("Ad lib") } == 0)
        assertEquals("A tempo, 120 beats per minute. bar 3: rest, whole bar", said[4])
    }

    @Test
    fun checkedNotesStopAnnouncingUncertainty() {
        val c = tiny()
        val view = PartView(c, c.voices[0], Instrument.CORNET, "Solo Cornet", checked = setOf(0))
        assertEquals("Solo Cornet. bar 1, no sharps or flats, beat 1: C 5, eighth note",
            view.announce(0, null, TsSettings(), Lang.EN, KotlinCoreBridge))
    }

    @Test
    fun musicXmlIsWellFormedAndTransposes() {
        val c = tiny()
        val xml = MusicXmlWriter.write(c, listOf(PartSpec("solo", "Solo Cornet", Instrument.CORNET)))
        val doc = DocumentBuilderFactory.newInstance().apply { isValidating = false; setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false) }
            .newDocumentBuilder().parse(xml.byteInputStream())
        val measures = doc.getElementsByTagName("measure")
        assertEquals(4, measures.length)
        assertEquals("-2", doc.getElementsByTagName("chromatic").item(0).textContent)
        // Every measure adds up to a full 4/4 bar of 96 ticks.
        for (i in 0 until measures.length) {
            val notes = (measures.item(i) as org.w3c.dom.Element).getElementsByTagName("duration")
            val sum = (0 until notes.length).sumOf { notes.item(it).textContent.toInt() }
            assertEquals("measure ${i + 1}", 96, sum)
        }
        assertTrue("very uncertain note is parenthesised", xml.contains("""parentheses="yes""""))
        assertTrue("uncertain note is coloured", xml.contains("#0063A6"))
        assertTrue(xml.contains("""<tie type="start"/>"""))
    }

    @Test
    fun quantizesSoloAndEstimatesKeyAndTempo() {
        // A B-flat major scale fragment at 120 bpm, eighth notes, slightly off the grid.
        val scale = listOf(70, 72, 74, 75, 77, 79, 81, 82)
        val notes = scale.mapIndexed { i, p ->
            TimedNote(2.0 + i * 0.25 + if (i % 2 == 0) 0.01 else -0.01, 2.0 + i * 0.25 + 0.22, p, 0.9, listOf("swiftf0"))
        }
        val c = KotlinCoreBridge.quantizeSolo(notes, 120.0, "Scale")
        val placed = c.voices[0].notes
        assertEquals((0 until 8).map { it * 12 }, placed.map { it.start })
        assertTrue(placed.all { it.dur == 12 })
        assertEquals(-2, c.keys[0].fifths)
        assertEquals(120.0, TempoEstimator.estimate(notes.map { it.onsetS } + notes.map { it.onsetS + 2.0 }), 8.0)
    }
}
