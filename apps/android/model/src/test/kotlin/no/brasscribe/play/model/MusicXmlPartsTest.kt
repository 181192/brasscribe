package no.brasscribe.play.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class MusicXmlPartsTest {
    private val golden = File(System.getProperty("brasscribe.golden") ?: "missing", "brass-band.musicxml")

    @Test
    fun namesAndOnePartOfTheGoldenScore() {
        assumeTrue("golden missing", golden.isFile)
        val xml = golden.readText()
        val names = MusicXmlParts.names(xml)
        assertEquals(18, names.size)
        assertEquals("Solo Cornet", names[1])
        val solo = MusicXmlParts.single(xml, 1)
        assertEquals(listOf("Solo Cornet"), MusicXmlParts.names(solo))
        assertEquals(1, Regex("<part id=").findAll(solo).count())
        // The part keeps every measure of the original.
        val id = Regex("""<score-part id="([^"]+)"""").find(solo)!!.groupValues[1]
        val measures = { s: String -> Regex("""<part id="$id">(.*?)</part>""", RegexOption.DOT_MATCHES_ALL).find(s)!!.groupValues[1] }
        assertEquals(measures(xml), measures(solo))
        assertTrue(solo.contains("<score-partwise"))
    }
}
