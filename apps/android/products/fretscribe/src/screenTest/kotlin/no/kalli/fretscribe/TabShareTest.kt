package no.kalli.fretscribe

import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenDevice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Share or print from the tab, on a fixture computer: the sheet lists what the tab can be shared as, a row makes its
 * file and hands it to the system's share sheet, Print lays the PDF out, and what only the computer writes says so
 * when the computer did not write it.
 */
@RunWith(AndroidJUnit4::class)
class TabShareTest : TabScreenTest() {
    override val shots = "fretscribe/share"

    private val exports get() = File(rule.activity.cacheDir, "exports")

    private fun share(row: String, file: String): File {
        rule.onNodeWithTag("fs-share-$row").performScrollTo().performClick()
        waitUntil(30_000) { exports.resolve(file).let { it.isFile && it.length() > 0 } }
        waitUntil(10_000) { rule.onAllNodesWithTag("fs-share-making").fetchSemanticsNodes().isEmpty() }
        ScreenDevice.closeSystemSheet(rule)
        return exports.resolve(file)
    }

    @Test
    fun theTabIsSharedAsEachKindOfFileAndPrinted() {
        computer("bass-line")
        showTheTab()
        exports.deleteRecursively()
        rule.onNodeWithContentDescription("Share or print").assertHeightIsAtLeast(48.dp).performClick()
        waitForTag("fs-share-print", 5_000)
        // The fixture computer wrote no PDF: the phone lays it out, and says so.
        rule.onNodeWithTag("fs-share-pdf-from").assertTextContains("The PDF is laid out on this phone.")
        rule.onNodeWithTag("fs-share-print").assertIsEnabled()
        for (row in listOf("pdf", "guitar_pro", "musicxml", "midi", "text", "instructions")) rule.onNodeWithTag("fs-share-$row").performScrollTo().assertIsEnabled()
        checkAccessibility()
        shot("share-or-print")

        assertEquals("PK", share("guitar_pro", "Bass line.gp").readBytes().decodeToString(0, 2))
        assertTrue(share("musicxml", "Bass line.musicxml").readText().contains("<score-partwise"))
        assertEquals("MThd", share("midi", "Bass line.mid").readBytes().decodeToString(0, 4))
        assertTrue(share("text", "Bass line.txt").readText().contains("Tuning: Standard (E A D G)"))
        assertTrue(share("instructions", "Bass line playing instructions.txt").readText().contains("Bar 1"))
        assertEquals("%PDF", share("pdf", "Bass line.pdf").readBytes().decodeToString(0, 4))
        // Print makes the PDF again and hands it to the system's print dialog.
        exports.resolve("Bass line.pdf").delete()
        rule.onNodeWithTag("fs-share-print").performScrollTo().performClick()
        waitUntil(30_000) { exports.resolve("Bass line.pdf").isFile }
        waitUntil(10_000) { rule.onAllNodesWithTag("fs-share-making").fetchSemanticsNodes().isEmpty() }
        ScreenDevice.closeSystemSheet(rule)
        assertEquals(0, rule.onAllNodesWithTag("fs-share-said").fetchSemanticsNodes().size)
    }

    @Test
    fun whatTheComputerDidNotWriteSaysSo() {
        // This computer wrote no text tab and no playing instructions for the song.
        computer("bass-line-marks")
        showTheTab()
        rule.onNodeWithTag("fs-tab-share").performClick()
        waitForTag("fs-share-print", 5_000)
        for (row in listOf("text", "instructions")) {
            rule.onNodeWithTag("fs-share-$row").performScrollTo().assertIsNotEnabled().assertTextContains("Your computer did not write this for the song.")
        }
        rule.onNodeWithTag("fs-share-guitar_pro").performScrollTo().assertIsEnabled()
        checkAccessibility()
    }
}
