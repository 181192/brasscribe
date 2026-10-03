package no.brasscribe.play

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** Fretscribe on your computer, the pairing screen: every word on it is Fretscribe's, in both languages. */
class PairingWordsTest {
    private val src = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("apps/android/app/src")

    private fun strings(file: File): Map<String, String> =
        Regex("""<string name="([a-z0-9_]+)"[^>]*>(.*?)</string>""", RegexOption.DOT_MATCHES_ALL).findAll(file.readText())
            .associate { it.groupValues[1] to it.groupValues[2].replace("\\'", "'") }

    @Test
    fun thePairingScreenNamesFretscribeAndNeverBrasscribeOrBandroom() {
        val screen = src?.resolve("main/kotlin/no/brasscribe/play/ui/CompanionScreen.kt")
        assumeTrue("the app's sources are not in this checkout", screen?.isFile == true)
        // What the pairing screen itself shows (About lives in the same file, and is not part of it), and what the
        // pairing says through the status line while the screen is open.
        val shown = Regex("""R\.string\.([a-z0-9_]+)""").findAll(screen!!.readText().substringBefore("fun AboutScreen"))
            .map { it.groupValues[1] }.toSet()
        val said = setOf("companion_failed_plain", "pair_needs_update", "pair_link_invalid", "server_name_format")
        val names = shown + said
        assertTrue("the screen's words are found", names.containsAll(setOf("companion_explain", "companion_searching", "companion_tech_details", "pair_link_address_by_name")))
        for (dir in listOf("values", "values-nb")) {
            val words = strings(File(src, "main/res/$dir/strings.xml")) + strings(File(src, "fretscribe/res/$dir/strings.xml"))
            val wrong = names.mapNotNull { name -> words[name]?.takeIf { Regex("Brasscribe|Bandroom").containsMatchIn(it) }?.let { "$name: $it" } }
            assertEquals(dir, emptyList<String>(), wrong)
        }
        assertEquals("Update the Fretscribe app on this phone to connect to this computer.", strings(File(src, "fretscribe/res/values/strings.xml"))["pair_needs_update"])
        assertEquals("Open Fretscribe on your computer and choose Pair a phone. Type the six digits it shows.",
            strings(File(src, "fretscribe/res/values/strings.xml"))["companion_explain"])
        assertEquals("Åpne Fretscribe på datamaskinen og velg Koble til en telefon. Skriv inn de seks sifrene som vises.",
            strings(File(src, "fretscribe/res/values-nb/strings.xml"))["companion_explain"])
    }

    /**
     * About credits what the Fretscribe app carries, as THIRD_PARTY_NOTICES.md lists it: the notation and playback
     * libraries for Android or for every app with the Rust core, the fonts of Fretscribe, and the Android
     * dependencies with code of their own in the app (Oboe's and ONNX Runtime's native libraries).
     */
    @Test
    fun aboutNamesEverythingTheAppCarries() {
        val notices = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("THIRD_PARTY_NOTICES.md")
        assumeTrue("the notices are not in this checkout", notices?.isFile == true)
        fun section(title: String) = notices!!.readText().substringAfter("## $title\n").substringBefore("\n## ")
        fun component(row: String): String {
            val cell = row.removePrefix("|").substringBefore("|").trim()
            val name = Regex("""^\[([^\]]+)]""").find(cell)?.groupValues?.get(1) ?: cell.substringBefore(" (").substringBefore(",")
            return name.removeSuffix(" font").trim()
        }
        fun rows(title: String, carried: (String) -> Boolean) =
            section(title).lines().filter { it.startsWith("| ") && !it.startsWith("| Component") && !it.startsWith("| Font") && carried(it) }.map(::component)
        val libraries = rows("Notation and playback libraries") { row ->
            val where = row.split("|").getOrNull(3).orEmpty()
            where.contains("Android") || where.contains("Rust core")
        }
        val fonts = rows("Fonts") { it.contains("Fretscribe") }
        val carried = libraries + fonts + listOf("Oboe", "ONNX Runtime")
        assertTrue(carried.toString(), carried.containsAll(listOf("alphaTab", "Bravura", "Sonivox SoundFont", "alphaSkia", "AndroidX Media3", "UniFFI",
            "Atkinson Hyperlegible Next", "Fretscribe Tab")))
        for (dir in listOf("values", "values-nb")) {
            val words = strings(File(src, "fretscribe/res/$dir/strings.xml"))
            val about = words["about_text"].orEmpty() + " " + words["about_font"].orEmpty()
            assertEquals(dir, emptyList<String>(), carried.filterNot { about.contains(it) })
        }
    }

    /** The R.string names used in [function] of [file], up to the next top-level function. */
    private fun used(file: String, function: String): Set<String> {
        val text = File(src, "main/kotlin/no/brasscribe/play/ui/$file").readText().substringAfter("fun $function(")
        val body = Regex("""\n(?:private |internal )?fun """).split(text, limit = 2).first()
        return Regex("""R\.string\.([a-z0-9_]+)""").findAll(body).map { it.groupValues[1] }.toSet()
    }

    @Test
    fun helpAboutAndTheProblemsAFretscribePlayerCanMeetAreFretscribesWords() {
        val screen = src?.resolve("main/kotlin/no/brasscribe/play/ui/ProblemScreen.kt")
        assumeTrue("the app's sources are not in this checkout", screen?.isFile == true)
        val help = used("ProblemScreen.kt", "HelpScreen")
        val about = used("CompanionScreen.kt", "AboutScreen")
        assertTrue(help.containsAll(setOf("help_1_text", "help_2_text", "help_5_text")))
        // The problems of every app, not the drafts made on the phone: Fretscribe makes none there.
        val reachable = listOf("FILE_UNREADABLE", "NO_SOUND_TRACK", "NOTHING_HEARD", "RECORDING_FAILED", "SCORE_FAILED", "TOO_LARGE")
        val problems = screen!!.readLines().filter { line -> reachable.any { line.trimStart().startsWith("Problem.$it to") } }
            .flatMap { Regex("""R\.string\.([a-z0-9_]+)""").findAll(it).map { m -> m.groupValues[1] } }.toSet() + "details_show"
        assertTrue(problems.containsAll(setOf("problem_file_body", "problem_record_body")))
        for (dir in listOf("values", "values-nb")) {
            val words = strings(File(src, "main/res/$dir/strings.xml")) + strings(File(src, "fretscribe/res/$dir/strings.xml"))
            val wrong = (help + about + problems).mapNotNull { name ->
                words[name]?.takeIf { Regex("Brasscribe|Bandroom|brass ?band|brassband|band|partitur|score", RegexOption.IGNORE_CASE).containsMatchIn(it) }?.let { "$name: $it" }
            }
            assertEquals(dir, emptyList<String>(), wrong)
        }
    }
}
