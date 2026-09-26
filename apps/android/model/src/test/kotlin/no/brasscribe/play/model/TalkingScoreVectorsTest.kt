package no.brasscribe.play.model

import kotlinx.serialization.Serializable
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/** Runs every case of docs/accessibility/talking-score-vectors.json (vendored in test resources). */
class TalkingScoreVectorsTest {
    @Serializable
    data class Case(
        val id: String,
        val settings: TsSettings,
        val context: TsContext,
        val part: TsPart? = null,
        val bar: TsBar? = null,
        val event: TsEvent,
        val expected: Map<String, String>,
    )

    @Serializable
    data class Vectors(val cases: List<Case>)

    private val vectors: Vectors by lazy {
        val text = File(System.getProperty("brasscribe.vectors")).readText()
        BrasscribeJson.decodeFromString(Vectors.serializer(), text)
    }

    @Test
    fun everyVectorMatchesInBothLanguages() {
        val failures = mutableListOf<String>()
        for (c in vectors.cases) {
            // The vectors are written for a B-flat cornet part in written D major unless the bar says otherwise.
            val stop = TsStop(c.event, c.bar, c.part, keyFifths = 2, totalBars = 128)
            for ((lang, key) in listOf(Lang.EN to "en", Lang.NB to "nb")) {
                val got = Announcer.announce(stop, c.context, c.settings, lang)
                val want = c.expected.getValue(key)
                if (got != want) failures += "${c.id} [$key]\n  want: $want\n  got:  $got"
            }
        }
        assertEquals("talking-score vectors failing:\n" + failures.joinToString("\n"), 0, failures.size)
    }

    @Test
    fun vectorFileHasCases() {
        assertEquals(25, vectors.cases.size)
    }
}
