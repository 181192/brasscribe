package no.brasscribe.play.core

import no.brasscribe.play.model.CompositionJson
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * Re-arranging an edited Composition through the core: the golden Composition must give the golden
 * score back, part for part, so a changed note changes only that note.
 */
class RearrangeTest {
    private val golden = File(System.getProperty("brasscribe.golden") ?: "missing")

    private fun parts(xml: String) = Regex("""<score-part id="([^"]+)">\s*<part-name>([^<]*)""").findAll(xml).map { it.groupValues[2] }.toList()
    private fun pitches(xml: String, part: Int): List<String> {
        val id = Regex("""<score-part id="([^"]+)">""").findAll(xml).map { it.groupValues[1] }.toList()[part]
        val body = Regex("""<part id="$id">(.*?)</part>""", RegexOption.DOT_MATCHES_ALL).find(xml)!!.groupValues[1]
        return Regex("""<step>(\w)</step>(?:\s*<alter>(-?\d)</alter>)?\s*<octave>(\d)</octave>""").findAll(body)
            .map { it.groupValues.drop(1).joinToString("") }.toList()
    }

    @Test
    fun normalizeKeepsTheReviewGroups() {
        val core = RustCoreBridge.load()
        assumeTrue("host core missing", core != null)
        val comp = File(golden, "composition.json")
        assumeTrue("golden missing", comp.isFile)
        val want = no.brasscribe.play.model.CompositionJson.decode(comp.readText()).review
        assumeTrue("golden has no review groups", !want.isNullOrEmpty())
        assertEquals(want, core!!.decodeComposition(comp.readText()).review)
    }

    @Test
    fun goldenCompositionGivesTheGoldenScore() {
        val core = RustCoreBridge.load()
        assumeTrue("host core missing", core != null)
        val comp = File(golden, "composition.json")
        assumeTrue("golden missing", comp.isFile)
        val c = core!!.decodeComposition(comp.readText())
        val want = File(golden, "brass-band.musicxml").readText()
        for (arranger in listOf("auto", "layers")) {
            val got = core.arrangeMusicXml(c, arranger)!!
            val same = parts(want).indices.count { i -> runCatching { pitches(got, i) == pitches(want, i) }.getOrDefault(false) }
            println("arranger $arranger: parts ${parts(got).size} vs ${parts(want).size}; parts with identical pitches $same; solo ${pitches(got, 1).size} vs ${pitches(want, 1).size}")
        }
        val got = core.arrangeMusicXml(c, "auto")!!
        assertEquals(parts(want), parts(got))
        assertEquals(pitches(want, 1), pitches(got, 1))
    }
}
