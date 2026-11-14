package no.kalli.fretscribe

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
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
import org.junit.Before
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

    /**
     * FileProvider keeps the folders it shares from in a static map, by authority, from the first share on: on the JVM
     * every test has a data folder of its own, so a share after another test's would look in the last one's.
     */
    @Before
    fun freshFileProvider() {
        @Suppress("UNCHECKED_CAST")
        (androidx.core.content.FileProvider::class.java.getDeclaredField("sCache").apply { isAccessible = true }.get(null) as MutableMap<String, *>).clear()
    }

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

    /**
     * A computer that is paired but does not answer is not there: the rows of what only it writes are off and say so,
     * and the PDF it once wrote is laid out on the phone instead.
     */
    @Test
    fun aPairedComputerThatDoesNotAnswerIsNotThere() {
        // This computer wrote a PDF of its own for the song, and the text tab and playing instructions.
        container.fixtureSource = no.kalli.scribe.engine.FixtureSource { name ->
            if (name == TabExports.TAB_PDF) "%PDF-1.4 the computer's".toByteArray() else ScreenDevice.fixture("bass-line/$name")
        }
        showTheTab()
        rule.onNodeWithTag("fs-tab-share").performClick()
        waitForTag("fs-share-print", 5_000)
        rule.onNodeWithTag("fs-share-pdf-from").assertTextContains("The PDF comes from Bandroom on your computer.")

        // With the sheet open, the same computer, paired, goes out of reach: what the connection says once it has looked
        // for it and given up. The sheet follows.
        rule.runOnUiThread {
            vm.connection.stop()
            container.fixtureSource = null
            container.settings.url = "http://127.0.0.1:9"
            container.settings.serverId = no.kalli.scribe.play.screen.StubEngine.SERVER_ID
            container.settings.serverName = "Bandroom on Studio"
            container.settings.paired = true
            @Suppress("UNCHECKED_CAST")
            (no.kalli.scribe.connection.ConnectionMonitor::class.java.getDeclaredField("_state").apply { isAccessible = true }.get(vm.connection)
                as kotlinx.coroutines.flow.MutableStateFlow<no.kalli.scribe.connection.ConnectionState>).value =
                no.kalli.scribe.connection.ConnectionState.Offline(paired = true)
        }
        assertEquals(no.kalli.scribe.connection.ConnectionState.Offline(paired = true), vm.connection.state.value)
        assertTrue("the paired computer has an engine all the same", rule.runOnUiThread<Boolean> { container.engine() != null })
        exports.deleteRecursively()
        waitUntil(5_000) {
            rule.onAllNodesWithTag("fs-share-pdf-from").fetchSemanticsNodes().singleOrNull()
                ?.config?.getOrNull(SemanticsProperties.Text)?.joinToString()?.contains("this phone") == true
        }
        rule.onNodeWithTag("fs-share-pdf-from").assertTextContains("The PDF is laid out on this phone.")
        for (row in listOf("text", "instructions")) {
            rule.onNodeWithTag("fs-share-$row").performScrollTo().assertIsNotEnabled().assertTextContains("Your computer writes this. Connect to it first.")
        }
        for (row in listOf("pdf", "guitar_pro", "musicxml", "midi")) rule.onNodeWithTag("fs-share-$row").performScrollTo().assertIsEnabled()
        checkAccessibility()
        shot("share-or-print-computer-out-of-reach")
        val pdf = share("pdf", "Bass line.pdf").readBytes()
        assertEquals("%PDF", pdf.decodeToString(0, 4))
        assertTrue("the phone laid the pages out", (no.kalli.scribe.score.export.PdfJoin.pageCount(pdf) ?: 0) >= 1)
        assertEquals(0, rule.onAllNodesWithTag("fs-share-said").fetchSemanticsNodes().size)
    }
}
