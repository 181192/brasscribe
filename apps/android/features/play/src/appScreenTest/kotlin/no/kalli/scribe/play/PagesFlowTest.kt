package no.kalli.scribe.play

import no.kalli.scribe.play.screen.testedProduct

import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.kalli.scribe.engine.FixtureEngineApi
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.screen.PageFiles
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Printed music from a picture or a PDF, in both apps: the pages come in (chosen on the phone, or handed over by
 * another app), are looked over, and are read on the computer into the app's own kind of result. The phone's picker
 * and its camera app are not run here: what they hand back is given to the view model, as they give it.
 */
@RunWith(AndroidJUnit4::class)
class PagesFlowTest : ScreenTest() {
    private val tab get() = testedProduct.name == "Fretscribe"
    private val reads get() = if (tab) Profile.SHEET_TAB else Profile.SHEET

    /** The screen a finished reading opens on: the score, or Check the song before the tab. */
    private val result get() = if (tab) Screen.OUTPUT else Screen.SCORE

    /** The fixture computer's pace before a test made it slow. */
    private var pace = 0.0

    @After
    fun clean() {
        rule.runOnUiThread { vm.cancelTranscription(); vm.pages.value.toList().forEach(vm::removePage); vm.home() }
        container.fixtureSource = null
        if (pace > 0) container.fixtureStageSeconds = pace
        PageFiles.clear()
    }

    /** The computer: one that reads pages, or with [only], one that has just those profiles (a Bandroom from before the pages). */
    private fun theComputer(only: List<String>? = null, also: Map<String, String> = emptyMap()) = computer(if (tab) "guitar-line" else "old-hundredth") { name, bytes ->
        if (name == FixtureEngineApi.PROFILES_FILE && only != null) only.joinToString(",", "[", "]") { "\"$it\"" }.toByteArray()
        else also[name]?.toByteArray() ?: bytes
    }

    private fun png(name: String): Uri = PageFiles.handedOver(name, PageFiles.picture())

    private fun shows(id: Int, vararg args: Any) = rule.onAllNodesWithText(text(id, *args)).fetchSemanticsNodes().isNotEmpty()

    private fun names() = vm.pages.value.map { it.name }

    /** The pages' screen with what is in hand, as it is once a first page has come in. */
    private fun fromHome() {
        rule.runOnUiThread { vm.home(); vm.showPages() }
        waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME, Screen.PAGES) }
        rule.waitForIdle()
    }

    /** What the phone's picker hands back: the files chosen, in their order. */
    private fun chosen(vararg uris: Uri) {
        val before = vm.pages.value.size
        rule.runOnUiThread { vm.addPages(uris.toList()) }
        waitUntil(20_000) { !vm.busy.value && vm.pages.value.size >= before }
        rule.waitForIdle()
    }

    private fun readEnabled(): Boolean = rule.onNodeWithTag("pages-read").fetchSemanticsNode().config.getOrNull(SemanticsProperties.Disabled) == null

    private fun arrives(intent: Intent) {
        rule.runOnUiThread { InstrumentationRegistry.getInstrumentation().callActivityOnNewIntent(rule.activity, intent) }
    }

    private fun waitForTheResult() {
        waitUntil(60_000) { vm.result.value != null && vm.screen.value.last() == result }
        if (!tab) waitForEngravedScore()
    }

    /**
     * Home's row Open sheet music asks what is opened: a score file (in the app that opens them), pictures or a PDF, or
     * a photo taken now. The button over it still opens a recording in one tap. The pictures chosen there (the picker's
     * answer) arrive on the pages' screen.
     */
    @Test
    fun homesSheetMusicRowAsksWhatIsOpenedAndPrintedMusicGoesToThePages() {
        theComputer()
        assertTrue(shown(), shows(R.string.home_import) && shows(R.string.home_open_score))
        rule.onNodeWithTag("home-open").performScrollTo().performClick()
        waitForTag("open-pages", 5_000)
        rule.waitForIdle()
        assertTrue(shown(), listOf(R.string.open_title, R.string.pages_choose, R.string.pages_photo).all { shows(it) })
        // A score file is a choice only where one is opened: Fretscribe opens none, and does not offer it.
        assertEquals(if (tab) 0 else 1, rule.onAllNodesWithTag("open-score").fetchSemanticsNodes().size)
        // A photo of a page is two taps from Home.
        assertEquals(1, rule.onAllNodesWithTag("open-photo").fetchSemanticsNodes().size)
        checkAccessibility()
        // Back closes the choice and leaves Home as it was.
        key(android.view.KeyEvent.KEYCODE_BACK)
        waitUntil(5_000) { rule.onAllNodesWithTag("open-pages").fetchSemanticsNodes().isEmpty() }
        assertEquals(listOf(Screen.HOME), vm.screen.value)

        chosen(png("Hymn 1.png"), png("Hymn 2.png"))
        waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME, Screen.PAGES) }
        assertEquals(listOf("Hymn 1.png", "Hymn 2.png"), names())
        rule.waitForIdle()
        assertTrue(readEnabled())
    }

    @Test
    fun pagesChosenOnThePhoneAreReadIntoTheAppsResult() {
        theComputer()
        fromHome()
        // Nothing to read yet, and the button says why.
        assertTrue(shows(R.string.pages_add_first) && shows(R.string.pages_choose) && shows(R.string.pages_photo))
        assertFalse(readEnabled())
        checkAccessibility()

        // Several pages, in the order they were chosen: a picture and a PDF, as they are.
        chosen(png("Hymn 1.png"), PageFiles.handedOver("Hymn 2.pdf", PageFiles.pdf()), png("Hymn 3.png"))
        assertEquals(listOf("Hymn 1.png", "Hymn 2.pdf", "Hymn 3.png"), names())
        assertTrue(shown(), listOf(text(R.string.pages_page, 1), text(R.string.pages_page, 3), "Hymn 2.pdf", text(R.string.pages_choose_more)).all { shown().contains(it) })
        assertTrue(readEnabled())
        checkAccessibility()

        // One is taken out, and another added after the rest: a picture the computer does not read goes as a JPEG.
        rule.onNodeWithTag("pages-remove-1").performScrollTo().performClick()
        waitUntil(5_000) { vm.pages.value.size == 2 }
        assertTrue(shows(R.string.pages_removed, 2))
        chosen(PageFiles.handedOver("Hymn 4.gif", PageFiles.gif()))
        assertEquals(listOf("Hymn 1.png", "Hymn 3.png", "Hymn 4.jpg"), names())
        assertEquals(Pages.Kind.JPEG, Pages.kindOf(vm.pages.value.last().file.readBytes().copyOf(Pages.HEAD_BYTES), null))

        rule.onNodeWithTag("pages-read").performClick()
        waitForTheResult()
        val made = vm.result.value!!
        assertEquals(reads, made.profile)
        assertFalse("read on the computer", made.onDevice)
        // Sent as pages and read, in those words; nothing is listened to.
        assertEquals(listOf(Step.UPLOAD_PAGES, Step.READ), vm.transcribe.value.steps.take(2))
        assertEquals(if (tab) listOf(Step.QUANTIZE, Step.ARRANGE, Step.EXPORT) else listOf(Step.WRITE, Step.EXPORT), vm.transcribe.value.steps.drop(2))
        // The result is where a recording's would be, with no question about a band in between; the pages are done with.
        assertEquals(listOf(Screen.HOME, result), vm.screen.value)
        assertEquals(emptyList<Page>(), vm.pages.value)
        // It is kept like any other, named after its first page where the computer gave it no title.
        waitUntil(10_000) { vm.savedScores.value.any { it.profile == reads.id && it.jobId == made.jobId } }
        // (At the end of the test: the accessibility checks on the score, or on Check the song.)
    }

    @Test
    fun theWritingDownScreenSaysThePagesAreRead() {
        // A computer that takes its time: each step a minute.
        theComputer()
        if (pace == 0.0) pace = container.fixtureStageSeconds
        container.fixtureStageSeconds = 60.0
        fromHome()
        chosen(png("A march.png"))
        rule.onNodeWithTag("pages-read").performClick()
        waitUntil(20_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.step == Step.READ }
        rule.waitForIdle()
        assertTrue(shown(), listOf("A march", text(R.string.stage_upload_pages), text(R.string.stage_read)).all { shown().contains(it) })
        // Nothing here is heard: none of a recording's steps is named.
        assertFalse(shown(), listOf(R.string.stage_upload, R.string.stage_beats, R.string.stage_stems, R.string.stage_transcribe).any { shown().contains(text(it)) })
        checkAccessibility()

        // Stopped: the pages are still in hand on their screen.
        rule.runOnUiThread { vm.cancelTranscription(); vm.back() }
        waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME, Screen.PAGES) }
        assertEquals(listOf("A march.png"), names())
    }

    @Test
    fun musicHandedOverByAnotherAppArrivesOnThePages() {
        theComputer()
        rule.runOnUiThread { vm.home(); vm.navigate(Screen.SETTINGS) }
        rule.waitForIdle()
        // A screenshot from the share sheet. Its name says nothing of what it is: its type and how it starts do.
        arrives(PageFiles.shared(PageFiles.handedOver("take-3.mp3", PageFiles.picture())))
        waitUntil(20_000) { vm.pages.value.size == 1 && !vm.busy.value }
        assertEquals(listOf(Screen.HOME, Screen.PAGES), vm.screen.value)
        assertEquals(listOf("take-3.png"), names())
        rule.waitForIdle()
        assertTrue(readEnabled())

        // Several shared at once are the pages of one piece, in their order, in the place of what was there.
        arrives(PageFiles.sharedTogether(listOf(png("B 1.png"), PageFiles.handedOver("B 2.jpg", PageFiles.picture(Bitmap.CompressFormat.JPEG)), png("B 3.png"))))
        waitUntil(20_000) { vm.pages.value.size == 3 && !vm.busy.value }
        assertEquals(listOf("B 1.png", "B 2.jpg", "B 3.png"), names())
        assertEquals(listOf(Screen.HOME, Screen.PAGES), vm.screen.value)

        // A PDF, which came without a name's ending.
        arrives(PageFiles.shared(PageFiles.handedOver("Parts", PageFiles.pdf()), "application/pdf"))
        waitUntil(20_000) { names() == listOf("Parts.pdf") && !vm.busy.value }
        checkAccessibility()

        // A recording still goes where recordings go.
        val take = recording("A take.wav")
        arrives(PageFiles.shared(Uri.fromFile(take), "audio/wav"))
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        assertEquals("A take.wav", vm.source.value?.name)
    }

    @Test
    fun whatIsNoPictureAndNoPdfIsLeftOutOrSaidSo() {
        theComputer()
        fromHome()
        // Among pages chosen on their screen it is left out, and the screen says so.
        chosen(png("Page.png"), PageFiles.handedOver("Notes.txt", "do re mi".toByteArray()))
        assertEquals(listOf("Page.png"), names())
        assertTrue(shown(), shows(R.string.pages_title) && shown().contains(rule.activity.resources.getQuantityString(R.plurals.pages_left_out, 1, 1)))

        // Handed over by another app with nothing in it that is a page: its own screen, with the way to choose a picture.
        rule.runOnUiThread { vm.removePage(vm.pages.value.single()); vm.home() }
        arrives(PageFiles.sharedTogether(listOf(PageFiles.handedOver("a.txt", "one".toByteArray()), PageFiles.handedOver("b.txt", "two".toByteArray()))))
        waitUntil(20_000) { vm.screen.value == listOf(Screen.HOME, Screen.PROBLEM) }
        assertEquals(Problem.NOT_A_PAGE, vm.problem.value)
        rule.waitForIdle()
        assertTrue(shown(), shows(R.string.problem_not_a_page_title) && shows(R.string.problem_not_a_page_body) && shows(R.string.pages_choose) && shows(R.string.back_home))
        assertFalse(vm.busy.value)
    }

    @Test
    fun withoutTheComputerThePagesWaitForIt() {
        container.fixtureSource = null
        container.settings.paired = false
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
        fromHome()
        chosen(png("Later.png"))
        // The pages are in hand, and nothing can be sent: the screen says what is needed, with the way to connect.
        assertTrue(shows(R.string.pages_needs_computer))
        assertFalse(readEnabled())
        checkAccessibility()
        // The way to connect is in the band over the button, beside the reason: in view however long the list is.
        rule.onNode(hasClickAction() and hasAnyAncestor(hasTestTag("pages-connect"))).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.COMPANION }

        // Connected from there (here the fixture computer comes): back on the pages, which are still there, and they are read.
        theComputer()
        rule.runOnUiThread { vm.back() }
        waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME, Screen.PAGES) }
        rule.waitForIdle()
        assertEquals(listOf("Later.png"), names())
        assertFalse(shows(R.string.pages_needs_computer))
        assertTrue(readEnabled())
        rule.onNodeWithTag("pages-read").performClick()
        waitForTheResult()
        assertEquals(reads, vm.result.value?.profile)
    }

    @Test
    fun aBandroomFromBeforeThePagesIsToBeUpdated() {
        // A computer whose Bandroom writes from recordings only.
        theComputer(only = listOf("solo", "brass-band", "orchestra-with-soloist", "pop-rock", "tab", "bass-tab"))
        fromHome()
        chosen(png("Old.png"), png("Old 2.png"))
        rule.onNodeWithTag("pages-read").performClick()
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM }
        assertEquals(Problem.PAGES_FAILED, vm.problem.value)
        rule.waitForIdle()
        // Said in the app's words, and nothing of "something went wrong, try again" alone.
        assertTrue(shown(), shows(R.string.problem_pages_title) && shows(R.string.error_pages_not_read) && shows(R.string.problem_pages_kept))
        assertEquals(1, rule.onAllNodesWithTag("problem-why").fetchSemanticsNodes().size)
        checkAccessibility()

        // The pages are kept: once Bandroom is updated (here: another computer), they are read from their screen.
        rule.onNodeWithText(text(R.string.problem_pages_change)).performClick()
        waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME, Screen.PAGES) }
        assertEquals(listOf("Old.png", "Old 2.png"), names())
        theComputer()
        rule.onNodeWithTag("pages-read").performClick()
        waitForTheResult()
        assertEquals(reads, vm.result.value?.profile)
    }

    /** A computer whose Bandroom is up to date and has no reader of printed music: its list has no profile for pages either. */
    @Test
    fun aComputerWithoutTheReaderIsSaidInWordsThatHoldForBoth() {
        theComputer(also = mapOf(FixtureEngineApi.NO_READER_FILE to ""))
        fromHome()
        chosen(png("Hymn.png"))
        rule.onNodeWithTag("pages-read").performClick()
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM }
        assertEquals(Problem.PAGES_FAILED, vm.problem.value)
        rule.waitForIdle()
        assertTrue(shown(), shows(R.string.error_pages_not_read))
        assertEquals(listOf("Hymn.png"), names())
    }

    /** What a job that read nothing says, in the engine's fixed words, and what the app makes of each. */
    @Test
    fun aJobThatReadNothingSaysWhyInTheAppsWords() {
        fun failsWith(said: String): Problem? {
            theComputer(also = mapOf(FixtureEngineApi.JOB_ERROR_FILE to said))
            rule.runOnUiThread { vm.home() }
            rule.waitForIdle()
            fromHome()
            if (vm.pages.value.isEmpty()) chosen(png("Hymn.png"))
            rule.waitForIdle()
            rule.onNodeWithTag("pages-read").performClick()
            waitUntil(30_000) { vm.screen.value.last() == Screen.PROBLEM && !vm.transcribe.value.running }
            rule.waitForIdle()
            // Whatever it was, the pages are still in hand.
            assertEquals(said, listOf("Hymn.png"), names())
            return vm.problem.value
        }
        fun why() = rule.onAllNodesWithTag("problem-why").fetchSemanticsNodes().size

        assertEquals(Problem.NO_NOTES_ON_PAGE, failsWith("no notes were found on the page"))
        assertTrue(shown(), shows(R.string.problem_no_notes_on_page_title) && shows(R.string.problem_no_notes_on_page_picture) && shows(R.string.problem_pages_change))
        assertEquals("the screen says it all", 0, why())
        checkAccessibility()

        assertEquals(Problem.NO_NOTES_ON_PAGE, failsWith("no staff of notes was found on the page: a tab staff is not read"))
        assertTrue(shown(), shows(R.string.problem_no_notes_on_page_title) && shows(R.string.error_only_tab_on_page))

        assertEquals(Problem.PAGES_FAILED, failsWith("there are more than 40 pages"))
        assertTrue(shown(), shows(R.string.problem_pages_title) && shows(R.string.error_too_many_pages))

        assertEquals(Problem.PAGES_FAILED, failsWith("a page is too large to read"))
        assertTrue(shown(), shows(R.string.error_page_too_large))
        checkAccessibility()

        // The general failure: no reason of its own, and trying again is the way on.
        assertEquals(Problem.PAGES_FAILED, failsWith("the pages could not be read"))
        assertTrue(shown(), shows(R.string.problem_pages_title) && shows(R.string.error_engine_failed) && shows(R.string.retry))
        assertFalse(shown(), shows(R.string.error_page_too_large) || shows(R.string.error_too_many_pages))
    }

    /** A PDF larger than the computer reads (50 MB) is refused on the phone at once: it is neither copied nor sent. */
    @Test
    fun aPdfTooLargeForTheComputerIsSaidSoBeforeItIsCopied() {
        theComputer()
        fromHome()
        val big = java.io.File(rule.activity.cacheDir, "Whole book.pdf")
        java.io.RandomAccessFile(big, "rw").use { it.write(PageFiles.pdf()); it.setLength(Pages.MAX_BYTES + 1) }
        try {
            chosen(png("Hymn.png"), Uri.fromFile(big))
            // The page that fits is in hand; the other is said in the words the computer's refusal has.
            assertEquals(listOf("Hymn.png"), names())
            assertTrue(shown(), shows(R.string.error_page_too_large))
            val kept = java.io.File(rule.activity.cacheDir, PlayViewModel.PAGES_DIR).listFiles().orEmpty()
            assertEquals("nothing of it was copied", listOf(vm.pages.value.single().file), kept.toList())
            // Alone, it leaves the pages' screen with nothing in hand and the same words: there is no problem screen for it.
            rule.runOnUiThread { vm.removePage(vm.pages.value.single()) }
            chosen(Uri.fromFile(big))
            assertEquals(emptyList<String>(), names())
            assertEquals(listOf(Screen.HOME, Screen.PAGES), vm.screen.value)
            assertTrue(shown(), shows(R.string.error_page_too_large))
        } finally {
            big.delete()
        }
    }

    @Test
    fun pagesInHandComeBackWithTheAppsState() {
        theComputer()
        fromHome()
        chosen(png("Kept.png"))
        // What a new process is given back: the pages by their files, and the screen they are on.
        val state = androidx.lifecycle.SavedStateHandle(mapOf(
            "stack" to arrayListOf(Screen.HOME.name, Screen.PAGES.name, Screen.TRANSCRIBE.name),
            "pages" to arrayListOf("${vm.pages.value.single().file.path}\nKept.png", "${rule.activity.cacheDir}/pages/gone.png\nGone.png"),
        ))
        lateinit var restored: PlayViewModel
        rule.runOnUiThread { restored = PlayViewModel(rule.activity.application, state) }
        assertEquals(listOf(Screen.HOME, Screen.PAGES), restored.screen.value)
        assertEquals(listOf("Kept.png"), restored.pages.value.map { it.name })
        // What nothing refers to any more is cleared away at a start: the page in hand is not one of those.
        pass(500)
        rule.waitForIdle()
        assertTrue(restored.pages.value.single().file.isFile)
    }
}
