package no.brasscribe.play.score

import no.brasscribe.play.audio.PcmAudio
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * A percussion part's <midi-program> picks the kit: 2 (program 1) the pop kit, anything else the band
 * kit. alphaTab resets a percussion track to program 0, so the kit is read from the MusicXML
 * ([PercussionKit]). "Listen to this bar" plays it from the phone SoundFont's subset exactly as from the
 * whole file. Needs data/sounds/band/brasscribe-band-mobile.sf2 for the renders.
 */
class PopKitTest {
    private val sounds = File(System.getProperty("brasscribe.sounds") ?: "../../../sounds")
    private val sf2 = File(System.getProperty("brasscribe.bandSounds") ?: File(sounds.parentFile, "data/sounds/band").path, "brasscribe-band-mobile.sf2")
    private val map = BandSoundMap.parse(File(sounds, "mapping.json").readText())

    private fun drums(program: Int?): String {
        val prog = program?.let { "<midi-program>$it</midi-program>" } ?: ""
        fun mi(id: Int) = "<midi-instrument id=\"P2-I$id\"><midi-channel>10</midi-channel>$prog<midi-unpitched>${id + 1}</midi-unpitched></midi-instrument>"
        fun hit(id: Int, step: String, oct: Int) =
            "<note><unpitched><display-step>$step</display-step><display-octave>$oct</display-octave></unpitched><duration>1</duration><instrument id=\"P2-I$id\"/><type>quarter</type></note>"
        return """<?xml version="1.0" encoding="UTF-8"?>
            <score-partwise version="4.0"><part-list>
            <score-part id="P1"><part-name>Solo Cornet</part-name><score-instrument id="P1-I1"><instrument-name>Cornet</instrument-name></score-instrument>
            <midi-instrument id="P1-I1"><midi-channel>1</midi-channel><midi-program>57</midi-program></midi-instrument></score-part>
            <score-part id="P2"><part-name>Percussion</part-name>
            <score-instrument id="P2-I36"><instrument-name>Bass Drum</instrument-name></score-instrument>
            <score-instrument id="P2-I38"><instrument-name>Snare</instrument-name></score-instrument>${mi(36)}${mi(38)}</score-part>
            </part-list>
            <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
            <clef><sign>G</sign><line>2</line></clef></attributes><note><rest/><duration>4</duration></note></measure></part>
            <part id="P2"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
            <clef><sign>percussion</sign></clef></attributes>${hit(36, "F", 4)}${hit(38, "C", 5)}${hit(36, "F", 4)}${hit(38, "C", 5)}</measure></part>
            </score-partwise>"""
    }

    @Test
    fun kitProgramsAreReadPerScorePart() {
        assertEquals(listOf(56, 1), PercussionKit.programs(drums(2)))
        assertEquals(listOf(56, null), PercussionKit.programs(drums(null)))
        assertEquals(emptyList<Int?>(), PercussionKit.programs("PK\u0003\u0004 not xml"))
    }

    @Test
    fun theMapPicksTheKitFromTheProgram() {
        assertEquals(1, map.resolve("Percussion", null, 1)!!.program)
        assertEquals(0, map.resolve("Percussion", null, 0)!!.program)
        assertEquals(0, map.resolve("Percussion", null, 25)!!.program)
        assertEquals(0, map.resolve("Percussion")!!.program)
        assertTrue(map.resolve("Percussion", null, 1)!!.percussion)
    }

    private fun render(program: Int?, whole: Boolean): PcmAudio =
        BarAudio.render(drums(program), 1, 1, map, sf2, whole) { error("the band SoundFont plays") }!!

    private fun rms(x: FloatArray) = sqrt(x.sumOf { it.toDouble() * it } / x.size)

    @Test
    fun popKitPlaysAndDiffersFromTheBandKit() {
        assumeTrue("no band SoundFont in data/sounds/band", sf2.isFile)
        val band = render(1, whole = false)
        val pop = render(2, whole = false)
        val popWhole = render(2, whole = true)
        val n = minOf(band.samples.size, pop.samples.size)
        val diff = sqrt((0 until n).sumOf { val d = (band.samples[it] - pop.samples[it]).toDouble(); d * d } / n)
        println("band kit rms %.5f, pop kit rms %.5f, difference rms %.5f".format(rms(band.samples), rms(pop.samples), diff))
        assertTrue("the band kit is silent", rms(band.samples) > 1e-4)
        assertTrue("the pop kit is silent", rms(pop.samples) > 1e-4)
        assertTrue("the pop kit plays the band kit's samples", diff > 0.3 * rms(band.samples))
        assertEquals(popWhole.samples.size, pop.samples.size)
        val most = pop.samples.indices.maxOf { abs(pop.samples[it] - popWhole.samples[it]) }
        assertEquals("the subset plays the pop kit as the whole file does", 0f, most, 1e-6f)
    }
}
