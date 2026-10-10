package no.brasscribe.play

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasText
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Sheet music as another app hands it over: a file, and the intent the share sheet or "Open with" starts the app with. */
object SheetMusicFiles {
    private val context: Context get() = ApplicationProvider.getApplicationContext()

    /** A tab as MusicXML (the fixture computer's). */
    fun musicXml(): ByteArray = checkNotNull(ScreenDevice.fixture("bass-line/tab.musicxml"))

    /** [bytes] as a file named [name], and the address another app would hand over for it. */
    fun handedOver(name: String, bytes: ByteArray = musicXml()): Uri {
        return Uri.fromFile(File(context.cacheDir, name).apply { writeBytes(bytes) })
    }

    /** "Open with" on [uri], from Files. */
    fun openWith(uri: Uri): Intent = Intent(Intent.ACTION_VIEW, uri, context, MainActivity::class.java)

    /** [uri] shared to the app from the share sheet. */
    fun shared(uri: Uri): Intent = Intent(Intent.ACTION_SEND, null, context, MainActivity::class.java)
        .setType("application/vnd.recordare.musicxml+xml").putExtra(Intent.EXTRA_STREAM, uri)
}

/**
 * Fretscribe opens no sheet music yet, and says so on a screen of its own however the file arrives: what it says
 * must still be there when the first screen is drawn after the file, which a line on Home was not.
 */
@RunWith(AndroidJUnit4::class)
class FretscribeSheetMusicTest : ScreenTest() {
    /** The screen says it in [title] and [body] (to a screen reader at once), with the two ways forward. */
    private fun assertRefused(title: String, body: String, open: String, record: String) {
        waitUntil(10_000) { shown().contains(title) }
        val shown = shown()
        assertEquals(listOf(Screen.HOME, Screen.PROBLEM), vm.screen.value)
        assertTrue(shown, shown.contains(body) && shown.contains(open) && shown.contains(record))
        assertEquals(1, rule.onAllNodes(hasText(title) and SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Assertive)).fetchSemanticsNodes().size)
        assertFalse(vm.busy.value)
    }

    private fun arrives(intent: Intent) {
        rule.runOnUiThread { vm.home(); vm.navigate(Screen.SETTINGS) }
        rule.waitForIdle()
        assertEquals(listOf(Screen.HOME, Screen.SETTINGS), vm.screen.value)
        rule.runOnUiThread { InstrumentationRegistry.getInstrumentation().callActivityOnNewIntent(rule.activity, intent) }
    }

    @Test
    fun sharedWhileOnAnotherScreen() {
        arrives(SheetMusicFiles.shared(SheetMusicFiles.handedOver("A tab.musicxml")))
        assertRefused("Fretscribe can't open sheet music yet", "It makes tabs from recordings.", "Open a recording", "Record with the microphone")
    }

    @Test
    fun openedWithWhileOnAnotherScreenInBokmal() {
        language("nb")
        arrives(SheetMusicFiles.openWith(SheetMusicFiles.handedOver("A tab.mxl")))
        assertRefused("Fretscribe kan ikke åpne noter ennå", "Den lager tabber fra opptak.", "Åpne et opptak", "Spill inn med mikrofonen")
    }

    /** Chosen with Open a recording: a name that says nothing, and MusicXML inside. */
    @Test
    fun sheetMusicWithoutItsNameIsRefused() {
        openFromHome(File(SheetMusicFiles.handedOver("A tab").path!!))
        assertRefused("Fretscribe can't open sheet music yet", "It makes tabs from recordings.", "Open a recording", "Record with the microphone")
    }

    /** An .xml file that is no MusicXML is a file that could not be read, not sheet music. */
    @Test
    fun otherXmlIsNotCalledSheetMusic() {
        openFromHome(File(SheetMusicFiles.handedOver("Settings.xml", "<?xml version=\"1.0\"?>\n<settings><volume>3</volume></settings>".toByteArray()).path!!))
        waitUntil(10_000) { vm.screen.value.last() == Screen.PROBLEM }
        assertTrue(vm.problem.value.toString(), vm.problem.value != Problem.SHEET_MUSIC)
        assertFalse(shown(), shown().contains("sheet music"))
    }
}

/** The app started by the file, from "Open with": the file is there before the first screen is drawn. */
@RunWith(AndroidJUnit4::class)
class FretscribeOpenedWithSheetMusicTest : ScreenTest(SheetMusicFiles.openWith(SheetMusicFiles.handedOver("A tab.musicxml"))) {
    @Test
    fun theAppStartsOnWhatItCannotOpen() {
        waitUntil(10_000) { shown().contains("Fretscribe can't open sheet music yet") }
        assertEquals(listOf(Screen.HOME, Screen.PROBLEM), vm.screen.value)
        assertTrue(shown(), shown().contains("It makes tabs from recordings.") && shown().contains("Open a recording") && shown().contains("Record with the microphone"))
        assertEquals(1, rule.onAllNodes(hasText("Fretscribe can't open sheet music yet") and
            SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Assertive)).fetchSemanticsNodes().size)
        // In Bokmål the screen is still there: the phone's language draws the app again.
        language("nb")
        waitUntil(10_000) { shown().contains("Fretscribe kan ikke åpne noter ennå") }
        assertTrue(shown(), shown().contains("Den lager tabber fra opptak.") && shown().contains("Åpne et opptak") && shown().contains("Spill inn med mikrofonen"))
    }
}
