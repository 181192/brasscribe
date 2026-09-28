package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
}
