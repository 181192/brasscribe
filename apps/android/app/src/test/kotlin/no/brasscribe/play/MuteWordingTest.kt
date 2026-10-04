package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Mute is «Demp» in Norwegian: «Lyd av min stemme» read as "the sound of my part". */
class MuteWordingTest {
    private val nb = File("src/main/res/values-nb/strings.xml").readText()

    private fun nb(name: String) = Regex("""<string name="$name">([^<]*)</string>""").find(nb)?.groupValues?.get(1)

    @Test
    fun muteSaysDemp() {
        assertEquals("Demp stemmen min", nb("mute_my_part"))
        assertEquals("Demp", nb("mute"))
        assertEquals("Demp %1\$s", nb("mute_part"))
        assertFalse(nb.contains("Lyd av"))
        assertFalse(nb.contains("slår av lyden"))
    }

    /** The design's glossary, component spec and icon labels say what the app says. */
    @Test
    fun theDesignSaysDempToo() {
        val design = File("../../../design")
        val glossary = File(design, "brand/brand.md").readText()
        assertTrue(glossary.contains("| Silence one part | Mute | ${nb("mute")} |"))
        assertTrue(glossary.contains("| Mute my part (headphones icon) | ${nb("mute_my_part")} |"))
        val icons = File(design, "tokens/icons.json").readText()
        assertTrue(Regex(""""mute":\s*\{"en": "Mute",\s*"nb": "${nb("mute")}"""").containsMatchIn(icons))
        assertTrue(Regex(""""play-along":\s*\{"en": "Mute my part",\s*"nb": "${nb("mute_my_part")}"""").containsMatchIn(icons))
        for (doc in listOf("brand/brand.md", "system.md", "README.md")) {
            val text = File(design, doc).readText()
            assertFalse(doc, Regex("""(?i)never[^.|]*\bDemp\b""").containsMatchIn(text))
            assertFalse(doc, text.contains("**Lyd av** / **Bare denne**"))
        }
    }
}
