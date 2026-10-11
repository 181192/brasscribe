package no.brasscribe.play.score

import alphaTab.midi.AlphaSynthMidiFileHandler
import alphaTab.midi.MidiFile
import alphaTab.midi.MidiFileGenerator
import alphaTab.midi.NoteEvent
import alphaTab.midi.NoteOnEvent
import alphaTab.midi.TempoChangeEvent
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * alphaTab's MusicXML fixes ([AlphaTabMusicXml]): ties in transposing parts sound once, a note whose tie start
 * comes before its stop loads, and trills alternate with the written auxiliary. The fixture is
 * apps/fixtures/ties-and-trills.musicxml (make-ties-and-trills.py), at 60 bpm, a quarter a second.
 */
class AlphaTabMusicXmlTest {
    private val repo = File(System.getProperty("brasscribe.sounds") ?: "../../../sounds").absoluteFile.parentFile
    private val fixture = File(repo, "apps/fixtures/ties-and-trills.musicxml")
    private val golden = File(repo, "data/golden/mikkel-arranged-band/brass-band.musicxml")

    data class Played(val track: Int, val start: Double, val end: Double, val key: Int)

    private fun played(xml: ByteArray): List<Played> {
        val settings = alphaTab.Settings()
        val score = AlphaTabMusicXml.parse(xml, settings)
        val midi = MidiFile()
        MidiFileGenerator(score, settings, AlphaSynthMidiFileHandler(midi, false)).generate()
        val events = (0 until midi.events.length.toInt()).map { midi.events[it] }
        val tempos = events.filterIsInstance<TempoChangeEvent>().sortedBy { it.tick }
        fun seconds(tick: Double): Double {
            var sec = 0.0; var at = 0.0; var us = 500000.0
            for (t in tempos) {
                if (t.tick > tick) break
                sec += (t.tick - at) / midi.division * us / 1e6; at = t.tick; us = t.microSecondsPerQuarterNote
            }
            return sec + (tick - at) / midi.division * us / 1e6
        }
        val trackOf = HashMap<Int, Int>()
        for (t in score.tracks) {
            trackOf[t.playbackInfo.primaryChannel.toInt()] = t.index.toInt()
            trackOf[t.playbackInfo.secondaryChannel.toInt()] = t.index.toInt()
        }
        val open = HashMap<Pair<Int, Int>, ArrayDeque<Double>>()
        val out = ArrayList<Played>()
        val notes = events.filterIsInstance<NoteEvent>().sortedWith(compareBy({ it.tick }, { if (it is NoteOnEvent && it.noteVelocity > 0) 1 else 0 }))
        for (e in notes) {
            val key = e.channel.toInt() to e.noteKey.toInt()
            if (e is NoteOnEvent && e.noteVelocity > 0) open.getOrPut(key) { ArrayDeque() }.addLast(e.tick)
            else open[key]?.removeFirstOrNull()?.let { out += Played(trackOf[key.first] ?: -1, seconds(it), seconds(e.tick), key.second) }
        }
        return out.sortedWith(compareBy({ it.track }, { it.start }))
    }

    @Test
    fun tiesSoundOnceInTransposingAndConcertParts() {
        assumeTrue("no fixture", fixture.isFile)
        val notes = played(fixture.readBytes())
        fun bars(track: Int) = notes.filter { it.track == track && it.start < 12 }.map { Triple(it.start, it.end, it.key) }
        assertEquals(listOf(Triple(0.0, 3.0, 72), Triple(3.0, 4.0, 74), Triple(4.0, 5.0, 70), Triple(5.0, 6.0, 65), Triple(6.0, 11.0, 67)), bars(0))
        assertEquals(listOf(Triple(0.0, 4.0, 70)), bars(1))
        assertEquals(listOf(Triple(0.0, 3.0, 50), Triple(3.0, 4.0, 52), Triple(4.0, 5.0, 48), Triple(5.0, 6.0, 43), Triple(6.0, 11.0, 45)), bars(2))
    }

    @Test
    fun trillsAlternateWithTheWrittenAuxiliary() {
        assumeTrue("no fixture", fixture.isFile)
        val notes = played(fixture.readBytes())
        // track, start, end, main key, auxiliary key (sounding)
        val trills = listOf(
            listOf(0, 12, 16, 74, 75), listOf(0, 16, 20, 72, 74), listOf(0, 20, 24, 74, 76), listOf(0, 24, 28, 67, 68), listOf(0, 28, 34, 65, 67),
            listOf(1, 12, 16, 67, 68),
            listOf(2, 12, 16, 52, 53), listOf(2, 16, 20, 50, 52), listOf(2, 20, 24, 52, 54), listOf(2, 24, 28, 45, 46), listOf(2, 28, 34, 43, 45),
        )
        for ((track, start, end, main, aux) in trills) {
            val t = notes.filter { it.track == track && it.start >= start && it.start < end }
            assertEquals("track $track at $start s", listOf(main, aux), t.map { it.key }.distinct().sorted())
            assertEquals(main, t.first().key)
            assertEquals(end.toDouble(), t.last().end, 1e-3)
            assertEquals(0.125, t[1].start - t[0].start, 1e-3)
        }
    }

    @Test
    fun tiesAreNumberedStopFirstAndNumbersKept() {
        fun part(vararg notes: String) = "<part id=\"P1\">" + notes.joinToString("") + "</part>"
        fun note(step: String, vararg tied: String) = "<note><pitch><step>$step</step><octave>5</octave></pitch><notations>${tied.joinToString("")}</notations></note>"
        val out = AlphaTabMusicXml.numberTies(part(
            note("D", "<tied type=\"start\" />"),
            note("D", "<tied type=\"start\" />", "<tied type=\"stop\" />"),
            note("D", "<tied type=\"stop\" />"),
            note("E", "<tied type=\"start\" number=\"3\" />"),
            note("E", "<tied type=\"stop\" number=\"3\" />")))
        assertEquals(part(
            note("D", "<tied number=\"1\" type=\"start\" />"),
            note("D", "<tied number=\"1\" type=\"stop\" />", "<tied number=\"1\" type=\"start\" />"),
            note("D", "<tied number=\"1\" type=\"stop\" />"),
            note("E", "<tied type=\"start\" number=\"3\" />"),
            note("E", "<tied type=\"stop\" number=\"3\" />")), out)
    }

    /** The golden: every pitched part sounds each tie chain once (the fixture keeps unnumbered ties covered). */
    @Test
    fun goldenPlaysEachTieChainOnce() {
        assumeTrue("no golden arrangement in data/golden", golden.isFile)
        val xml = golden.readBytes()
        val played = played(xml)
        val text = xml.toString(Charsets.UTF_8)
        Regex("<part\\b.*?</part>", RegexOption.DOT_MATCHES_ALL).findAll(text).forEachIndexed { track, part ->
            val notes = Regex("<note\\b.*?</note>", RegexOption.DOT_MATCHES_ALL).findAll(part.value).map { it.value }
                .filter { "<pitch>" in it && "<grace" !in it }.toList()
            if (notes.isEmpty()) return@forEachIndexed
            val chains = notes.count { "<tie type=\"stop\"" !in it }
            assertEquals("part ${track + 1}", chains, played.count { it.track == track })
        }
    }
}
