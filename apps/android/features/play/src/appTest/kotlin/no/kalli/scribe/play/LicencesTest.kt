package no.kalli.scribe.play

import no.kalli.scribe.play.ui.LicencePart
import no.kalli.scribe.play.ui.licenceParagraphs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** The file of third-party licences the app ships (licences/dist, written by scripts/licences.py), as About shows it. */
class LicencesTest {
    @Test
    fun aFileIsShownAsHeadingsParagraphsAndDividers() {
        val rule = "=".repeat(40)
        val file = "Third-party licences: An app\n\nWhat this is.\n\nContents\n\n- A font (OFL-1.1)\n\n" +
            "$rule\n\nA font\nhttps://example.org/font\nLicence: OFL-1.1\n\nCopyright someone.\n\n" +
            "$rule\n\nLicence text: OFL-1.1\n\nFirst paragraph.\n\nSecond paragraph.\n"
        assertEquals(
            listOf(
                LicencePart("What this is.", false), LicencePart("Contents", true), LicencePart("- A font (OFL-1.1)", false),
                LicencePart(null, false), LicencePart("A font", true), LicencePart("https://example.org/font\nLicence: OFL-1.1", false),
                LicencePart("Copyright someone.", false),
                LicencePart(null, false), LicencePart("Licence text: OFL-1.1", true),
                LicencePart("First paragraph.", false), LicencePart("Second paragraph.", false),
            ),
            licenceParagraphs(file),
        )
    }

    @Test
    fun aLineOfEqualsInsideANoticeIsNotADivider() {
        assertEquals(listOf(LicencePart("========", false), LicencePart("A notice.", false)), licenceParagraphs("Title\n\n========\n\nA notice.\n"))
    }

    /** Both apps' own files: each names what it ships, and carries the text of every licence it names. */
    @Test
    fun theShippedFilesNameTheirPartsAndCarryTheTexts() {
        val dist = generateSequence(File("").absoluteFile) { it.parentFile }.map { File(it, "licences/dist") }.first { it.isDirectory }
        for (app in listOf("brasscribe-android", "fretscribe-android")) {
            val parts = licenceParagraphs(File(dist, "$app.txt").readText())
            val headings = parts.filter { it.heading }.mapNotNull { it.text }
            assertTrue(app, "alphaTab" in headings && "Licence text: MPL-2.0" in headings && "Licence text: Apache-2.0" in headings)
            assertTrue(app, parts.any { it.text?.startsWith("Mozilla Public License Version 2.0") == true })
        }
    }
}
