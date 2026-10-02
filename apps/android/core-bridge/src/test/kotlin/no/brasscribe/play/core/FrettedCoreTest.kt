package no.brasscribe.play.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import uniffi.brasscribe_ffi.CoreException
import uniffi.brasscribe_ffi.frettedFingeringJson
import uniffi.brasscribe_ffi.frettedPlayingInstructionsJson
import uniffi.brasscribe_ffi.frettedTabJson
import uniffi.brasscribe_ffi.frettedTabTextJson

/** Tab fingering through the core: target-fretted's JSON request in, its JSON answer or its text out. Skips without the host library. */
class FrettedCoreTest {
    private fun requireCore() = assumeTrue("host build of the Rust core not found", RustCoreBridge.load() != null)

    // A bass line down to D1, which a 4-string bass in standard tuning cannot play.
    private fun request(pinString: Int) = """
        {"instrument": {"preset": "bass-4-standard"},
         "notes": [{"pitch": 26, "start": 0, "dur": 24}, {"pitch": 33, "start": 24, "dur": 24},
                   {"pitch": 38, "start": 48, "dur": 12}, {"pitch": 40, "start": 60, "dur": 36, "techniques": ["hammer-on"]}],
         "options": {"style": "open-position", "pins": [{"note": 2, "string": $pinString}]}}
    """.trimIndent()

    private fun parse(json: String): JsonObject = Json.parseToJsonElement(json).jsonObject
    private fun JsonObject.int(key: String) = getValue(key).jsonPrimitive.int

    @Test
    fun aFingeringRequestComesBackWithAPlaceForEveryNote() {
        requireCore()
        val answer = parse(frettedFingeringJson(request(pinString = 3)))
        val notes = answer.getValue("fingering").jsonObject.getValue("notes").jsonArray.map { it.jsonObject }
        assertEquals(4, notes.size)
        assertTrue(notes[0].getValue("out_of_range").jsonPrimitive.boolean)
        assertEquals(JsonNull, notes[0].getValue("string"))
        // With D2 pinned at the fifth fret, A1 is played beside it and not on the open string.
        assertEquals(4 to 5, notes[1].int("string") to notes[1].int("fret"))
        // The pin puts D2 on the third string, and the hammer-on follows it there.
        assertEquals(3 to 5, notes[2].int("string") to notes[2].int("fret"))
        assertTrue(notes[2].getValue("pinned").jsonPrimitive.boolean)
        assertEquals(3, notes[3].int("string"))
        assertTrue(answer.getValue("violations").jsonArray.isEmpty())
        assertEquals("bass-4-drop-d", answer.getValue("tuning_suggestions").jsonArray[0].jsonObject.getValue("preset").jsonPrimitive.content)

        // The same request as tablature, and the fingering of the answer written as it is.
        val tab = parse(frettedTabJson(request(pinString = 3)))
        assertEquals(0, tab.int("adjusted_notes"))
        val xml = tab.getValue("musicxml").jsonPrimitive.content
        assertTrue(xml.contains("<sign>TAB</sign>") && xml.contains("<staff-lines>4</staff-lines>"))
        val again = JsonObject(parse(request(pinString = 3)) + ("fingering" to answer.getValue("fingering")))
        assertEquals(xml, parse(frettedTabJson(again.toString())).getValue("musicxml").jsonPrimitive.content)
    }

    @Test
    fun theSameRequestComesBackAsATextTabAndAsPlayingInstructions() {
        requireCore()
        val text = frettedTabTextJson(request(pinString = 3))
        assertTrue(text, text.startsWith("Bass\nTuning: Standard (E A D G), bottom line to top\n"))
        // D1 has no string; the hammer-on is an h before the fret it leads to.
        assertTrue(text, text.contains("\n   !\nG|----------------||\nD|----------------||\nA|---------5h7----||\nE|-----5----------||\n"))
        assertTrue(text, text.contains("bar 1: D1"))

        val en = frettedPlayingInstructionsJson(request(pinString = 3))
        assertTrue(en, en.contains("\nBar 1\n  Beat 1. D 1, no string to play it on. Quarter note.\n  Beat 2. String 4, fret 5. Quarter note.\n"))
        val inNorwegian = JsonObject(parse(request(pinString = 3)) + ("text" to parse("""{"lang": "nb"}""")))
        val nb = frettedPlayingInstructionsJson(inNorwegian.toString())
        assertTrue(nb, nb.contains("\nTakt 1\n  Slag 1. D 1, ingen streng å spille den på. Fjerdedelsnote.\n  Slag 2. Streng 4, bånd 5. Fjerdedelsnote.\n"))
        assertEquals(en.lines().size, nb.lines().size)

        assertThrows(CoreException.Invalid::class.java) { frettedTabTextJson("{") }
        val german = JsonObject(parse(request(pinString = 3)) + ("text" to parse("""{"lang": "de"}""")))
        val refused = assertThrows(CoreException.Invalid::class.java) { frettedPlayingInstructionsJson(german.toString()) }
        assertTrue(refused.reason, refused.reason.contains("en or nb"))
    }

    @Test
    fun aRequestTheCoreCannotReadIsInvalidInput() {
        requireCore()
        assertThrows(CoreException.Invalid::class.java) { frettedFingeringJson("{") }
        assertThrows(CoreException.Invalid::class.java) { frettedTabJson("{") }
        // A pin on a string the instrument does not have is refused; one the string cannot sound is reported.
        val refused = assertThrows(CoreException.Invalid::class.java) { frettedFingeringJson(request(pinString = 9)) }
        assertEquals("a pin names string 9 of 4", refused.reason)
        val reported = parse(frettedFingeringJson(request(pinString = 1))).getValue("violations").jsonArray
        assertEquals("pin-not-honoured", reported[0].jsonObject.getValue("kind").jsonPrimitive.content)
    }
}
