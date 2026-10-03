package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import java.io.File

/**
 * What Brasscribe says, in English and bokmål, is true and in the band room's words (design/brand/brand.md): no
 * developer command, no "transcribe", no "output", and nb «opptak» for a recording.
 */
class BrasscribeWordsTest {
    private val src = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("apps/android/app/src")

    private fun strings(dir: String): Map<String, String> =
        Regex("""<string name="([a-z0-9_]+)"[^>]*>(.*?)</string>""", RegexOption.DOT_MATCHES_ALL)
            .findAll(File(src, "main/res/$dir/strings.xml").readText())
            .associate { it.groupValues[1] to it.groupValues[2].replace("\\'", "'") }

    private val en by lazy { strings("values") }
    private val nb by lazy { strings("values-nb") }

    @Before
    fun sources() = assumeTrue("the app's sources are not in this checkout", src?.resolve("main/res/values/strings.xml")?.isFile == true)

    private fun matching(words: Map<String, String>, pattern: Regex) = words.filterValues { pattern.containsMatchIn(it) }.map { "${it.key}: ${it.value}" }

    @Test
    fun noDeveloperCommandAndNoTranscriberIsShown() {
        val wrong = Regex("pixi|serve-lan|transcrib|transkrib", RegexOption.IGNORE_CASE)
        assertEquals(emptyList<String>(), matching(en, wrong))
        assertEquals(emptyList<String>(), matching(nb, wrong))
        // The pairing screen's tech details still say where the address is.
        assertTrue(en.getValue("companion_tech_details").contains("Details for the band's tech person"))
        assertTrue(nb.getValue("companion_tech_details").contains("Detaljer for den tekniske i bandet"))
    }

    @Test
    fun theButtonAfterCheckingSaysWhatComesNext() {
        // Not "Choose output" / «Velg resultat»: the next screen asks for the band and the key.
        assertTrue(en.getValue("review_continue"), !Regex("output|choose", RegexOption.IGNORE_CASE).containsMatchIn(en.getValue("review_continue")))
        assertTrue(nb.getValue("review_continue"), !Regex("resultat|velg", RegexOption.IGNORE_CASE).containsMatchIn(nb.getValue("review_continue")))
        assertTrue(en.getValue("review_continue").contains("band"))
        assertTrue(nb.getValue("review_continue").contains("band"))
    }

    @Test
    fun bokmalRecordsAnOpptak() {
        // A recording is an «opptak» everywhere, as on the rest of the screens.
        assertEquals(emptyList<String>(), matching(nb, Regex("innspilling", RegexOption.IGNORE_CASE)))
        assertEquals("Opptaket er i gang", nb["record_started"])
        assertEquals("Stopp opptaket", nb["record_stop"])
    }

    @Test
    fun helpSaysWhatThePhoneMakesAndWhenThereIsPaper() {
        // A brass band can be made on the phone, as a draft; the full score is the computer's.
        assertTrue(en.getValue("help_5_text"), en.getValue("help_5_text").contains("draft"))
        assertTrue(nb.getValue("help_5_text"), nb.getValue("help_5_text").contains("utkast"))
        assertTrue(!en.getValue("help_5_title").contains("needs your computer"))
        assertTrue(!nb.getValue("help_5_title").contains("trenger datamaskinen"))
        // Print needs the computer's PDFs: the line says so.
        assertTrue(en.getValue("help_4_text"), en.getValue("help_4_text").contains("your computer"))
        assertTrue(nb.getValue("help_4_text"), nb.getValue("help_4_text").contains("datamaskinen"))
    }

    @Test
    fun notSureNamesBothAnswersByTheirCards() {
        // "Choose Brass band" alone is wrong for a take of yourself: every note of a draft is marked.
        for (words in listOf(en, nb)) {
            val line = words.getValue("profile_not_sure")
            assertTrue(line, line.contains(words.getValue("profile_brass_band")))
            assertTrue(line, line.contains(words.getValue("profile_solo")))
        }
    }
}
