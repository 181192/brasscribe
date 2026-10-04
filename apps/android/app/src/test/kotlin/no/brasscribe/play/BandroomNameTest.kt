package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The program on the computer is Brasscribe Bandroom (Bandroom for short) in both apps, as the list of programs on a
 * Mac and on Windows calls it: never "Brasscribe on your computer" or "Fretscribe on your computer".
 */
class BandroomNameTest {
    private val old = Regex(
        """(Brasscribe|Fretscribe) (on|på) (your |the |a |en )?(computer|datamaskin)|""" +
            """(Open|Åpne|Connect|Koble til) (Brasscribe|Fretscribe)(?! Bandroom)|(Brasscribe|Fretscribe) (there|der)\b""",
    )

    @Test
    fun noStringNamesTheProgramByTheApp() {
        val files = listOf("main", "brasscribe", "fretscribe").flatMap { flavour ->
            File("src/$flavour/res").listFiles { f -> f.name.startsWith("values") }.orEmpty()
                .flatMap { dir -> dir.listFiles { f -> f.extension == "xml" }.orEmpty().toList() }
        }
        assertTrue("the string files are found", files.any { it.path.endsWith("fretscribe/res/values-nb/strings.xml") })
        val found = files.flatMap { file ->
            Regex("""<string name="([a-z0-9_]+)"[^>]*>(.*?)</string>""", RegexOption.DOT_MATCHES_ALL).findAll(file.readText())
                .filter { old.containsMatchIn(it.groupValues[2]) }.map { "${file.path} ${it.groupValues[1]}: ${it.groupValues[2]}" }.toList()
        }
        assertEquals(emptyList<String>(), found)
    }
}
