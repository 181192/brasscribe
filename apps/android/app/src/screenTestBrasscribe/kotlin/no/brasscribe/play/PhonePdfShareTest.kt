package no.brasscribe.play

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.export.PdfJoin
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * A score with no PDF from the computer (here opened from its MusicXML, as one made on the phone has none) has a PDF in
 * Share or print all the same: the phone lays it out. PDF is the default and Print the primary, and the PDF says it was
 * laid out on this phone. Every part makes a file per player and one file of them all, for one print job.
 */
@RunWith(AndroidJUnit4::class)
class PhonePdfShareTest : ScreenTest() {
    @Before
    fun setUp() {
        container.firstRunDone = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
    }

    @Test
    fun aScoreWithoutTheComputersPdfPrintsThePhonesAndEveryPartIsOneFile() {
        val xml = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(xml) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(20_000) { rule.onAllNodesWithTag("stand-enter").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithContentDescription("Share or print").performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.EXPORT }

        val pdfBox = rule.onNode(hasText("PDF") and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Checkbox))
        pdfBox.assertIsEnabled()
        assertEquals(ToggleableState.On, pdfBox.fetchSemanticsNode().config[SemanticsProperties.ToggleableState])
        rule.onNodeWithText(text(R.string.export_pdf_phone)).assertExists()
        rule.onNodeWithTag("print").assertIsEnabled()
        checkAccessibility()
        shot("share-or-print-phone-pdf")

        val every = rule.onNode(hasText(text(R.string.export_scope_every_part)) and SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton))
        every.performClick()
        every.assertIsSelected()
        val exports = rule.activity.cacheDir.resolve("exports").apply { deleteRecursively() }
        rule.onNodeWithTag("share").performClick()
        val parts = no.brasscribe.play.model.MusicXmlParts.names(xml.decodeToString()).size
        waitUntil(30_000) { exports.listFiles().orEmpty().count { it.name.endsWith(".pdf") && !it.name.endsWith(".parts.pdf") } == parts }
        waitUntil(10_000) { exports.listFiles().orEmpty().any { it.name.endsWith(".parts.pdf") } }
        ScreenDevice.closeSystemSheet(rule)
        val joined = exports.listFiles()!!.single { it.name.endsWith(".parts.pdf") }
        assertTrue((PdfJoin.pageCount(joined.readBytes()) ?: 0) >= parts)
        assertTrue(exports.listFiles()!!.any { it.name.endsWith(" - Solo Cornet.pdf") })
    }
}
