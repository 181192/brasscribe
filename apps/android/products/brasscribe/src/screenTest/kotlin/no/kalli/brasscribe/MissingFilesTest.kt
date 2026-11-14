package no.kalli.brasscribe

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasAnyDescendant
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.FixtureEngineApi
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.Screen
import no.kalli.scribe.play.Source
import no.kalli.scribe.play.SourceKind
import no.kalli.scribe.play.Where
import no.kalli.scribe.play.export.ExportFormat
import no.kalli.scribe.play.export.Exporter
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * A score whose job on the computer finished without some of its files (a computer without MuseScore makes no PDF, no
 * MIDI and no recording of the band): Share or print says which, why, and what to do on the computer, in the app's own
 * words. The PDF is the phone's own then, and says so.
 */
@RunWith(AndroidJUnit4::class)
class MissingFilesTest : ScreenTest() {
    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    private val lacking = setOf("brass-band.pdf", "brass-band.mid", "brass-band.mp3")

    private fun shareOrPrint(reason: String) {
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth") { name, bytes ->
            when {
                name == FixtureEngineApi.MISSING_FILE ->
                    lacking.joinToString(",", "[", "]") { """{"name":"$it","reason":"$reason","message":"$it was not made: the engine's own English."}""" }.toByteArray()
                name in lacking || (name.startsWith("parts/") && name.endsWith(".pdf")) -> null
                else -> bytes
            }
        }
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        rule.runOnUiThread { vm.navigate(Screen.SCORE) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.runOnUiThread { vm.navigate(Screen.EXPORT) }
        waitForTag("share", 10_000)
        rest()
    }

    private fun shows(words: String) = rule.onAllNodesWithText(words, substring = true).fetchSemanticsNodes().isNotEmpty()

    /** The note above the formats: the reason and what to do, said once however many files lack it. */
    private fun note(): String = rule.onAllNodes(androidx.compose.ui.test.hasAnyAncestor(androidx.compose.ui.test.hasTestTag("export-missing")), useUnmergedTree = true)
        .fetchSemanticsNodes().flatMap { it.config.getOrElseNullable(androidx.compose.ui.semantics.SemanticsProperties.Text) { null }.orEmpty() }.joinToString("") { it.text }

    @Test
    fun shareOrPrintSaysWhatTheComputerDidNotMakeAndWhatToDo() {
        shareOrPrint("musescore-not-installed")
        val r = vm.result.value!!
        assertEquals(lacking, r.engineMissing.map { it.name }.toSet())
        val why = text(no.kalli.scribe.play.R.string.export_missing_not_installed)
        // Why and what to do, once, above the formats.
        assertEquals(why, note())
        assertEquals("the reason is said once", 1, rule.onAllNodesWithText(why, substring = true, useUnmergedTree = true).fetchSemanticsNodes().size)
        // The PDF is the phone's own, and its row says so.
        assertTrue(shows(text(no.kalli.scribe.play.R.string.export_pdf_phone_missing)))
        // The recording of the band is not there: its row is off and says it was not made, not "Needs Bandroom".
        rule.onNodeWithText(text(no.kalli.scribe.play.R.string.export_missing)).performScrollTo()
        shot("share-or-print-missing")
        assertFalse("it does not say the computer is needed: the computer was there", shows(text(no.kalli.scribe.play.R.string.export_needs_engine)))
        // The engine's English is not what is shown.
        assertFalse(shows("the engine's own English"))
        // Without the score's own MIDI the computer's is the only one, and it is not there.
        val exporter = Exporter(rule.activity, container.core, container.product.phonePdf)
        assertFalse(exporter.available(r, ExportFormat.MIDI, midiFromScore = false))
        assertTrue(exporter.available(r, ExportFormat.MIDI, midiFromScore = true))
        assertTrue(exporter.available(r.copy(engineMissing = emptyList()), ExportFormat.MIDI, midiFromScore = false))
        checkAccessibility()
    }

    @Test
    fun inBokmalWithLargerTextOnASmallPhoneAndForAMuseScoreThatDidNotStart() {
        org.junit.Assume.assumeTrue("this device keeps its own size", no.kalli.scribe.play.screen.ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        shareOrPrint("musescore-not-starting")
        val why = text(no.kalli.scribe.play.R.string.export_missing_not_starting)
        assertTrue(why, why.startsWith("MuseScore kom ikke i gang"))
        assertEquals(why, note())
        assertTrue(shows(text(no.kalli.scribe.play.R.string.export_pdf_phone_missing)))
        rule.onNodeWithText(text(no.kalli.scribe.play.R.string.export_missing)).performScrollTo()
        shot("share-or-print-missing-small-nb-130")
        assertNoTextIsClipped()
    }

    @Test
    fun aReasonTheAppDoesNotKnowNamesNoCause() {
        shareOrPrint("a-reason-from-a-newer-engine")
        assertEquals(text(no.kalli.scribe.play.R.string.export_missing_unknown), note())
        assertFalse("no MuseScore named for a cause the app does not know", note().contains("MuseScore"))
    }
}
