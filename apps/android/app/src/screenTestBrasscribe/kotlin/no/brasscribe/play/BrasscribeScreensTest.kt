package no.brasscribe.play

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenCatalogue
import no.brasscribe.play.screen.ScreenDevice
import org.junit.After
import org.junit.Before
import org.junit.runner.RunWith
import java.io.File

/** Brasscribe's screens (see [ScreenCatalogue]), on the fixture computer that serves "Old Hundredth". */
@RunWith(AndroidJUnit4::class)
class BrasscribeScreensTest : ScreenCatalogue() {
    override val shots = "brasscribe"

    @Before
    fun aStandThatHasBeenSeen() {
        container.standHintShown = true
        rule.runOnUiThread { vm.keptRecordings.value.forEach(vm::deleteKept) }
    }

    @After
    fun asItWas() {
        rule.runOnUiThread {
            vm.keptRecordings.value.forEach(vm::deleteKept)
            container.updateSeat(SeatChoice.NotSet)
            container.firstRunDone = true
        }
    }

    private fun go(vararg to: Screen) = rule.runOnUiThread { to.forEach(vm::navigate) }

    /** A recording in hand, on What is this?. */
    private fun whatIsThis() {
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
        }
    }

    /** The notes written down by the computer: Check the notes is next. */
    private fun checkTheNotes() {
        whatIsThis()
        rule.runOnUiThread { vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
    }

    /** The hymn opened as a score, engraved. */
    private fun theScore() {
        val file = File(rule.activity.cacheDir, "Old Hundredth.musicxml").apply { writeBytes(checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))) }
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        // (The player loads its sounds on a thread of its own, and puts the page at its cursor when it has them.)
        runCatching { waitUntil(20_000) { vm.scoreController?.view?.api?.isReadyForPlayback == true } }
        rest()
    }

    /** A recording sent to a computer that is not there: its score is not made, and the recording is kept in Your scores. */
    private fun aRecordingWithoutItsScore() {
        val file = recording("Band practice.wav")
        rule.runOnUiThread { container.fixtureSource = null; vm.importUri(android.net.Uri.fromFile(file)) }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        rule.runOnUiThread { vm.chooseProfile(Profile.BRASS_BAND); vm.where.value = Where.COMPANION; vm.startTranscription() }
        waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM && vm.keptRecordings.value.isNotEmpty() }
    }

    private fun more() {
        rule.onNodeWithTag("top-more").performClick()
        waitForTag("performance", 5_000)
    }

    override val screens = listOf(
        Entry("first-run") { rule.runOnUiThread { container.firstRunDone = false; vm.navigate(Screen.FIRST_RUN) } },
        Entry("what-do-you-play") {
            rule.runOnUiThread { container.updateSeat(SeatChoice.NotSet); container.firstRunDone = false; vm.finishFirstRun() }
            waitForTag("seat-continue", 5_000)
        },
        Entry("home") { },
        Entry("home-with-a-score") { theScore(); rule.runOnUiThread { vm.home() }; rest() },
        Entry("record") { go(Screen.RECORD) },
        Entry("what-is-this") { whatIsThis() },
        Entry("transcribing", steady = false) {
            whatIsThis()
            rule.runOnUiThread { vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST); vm.where.value = Where.COMPANION; vm.startTranscription() }
            waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE }
        },
        Entry("check-the-notes", ownOrder = "the notes of the part are a list of their own, which the keyboard goes through as they are played",
            notReached = setOf(Control("Solo Cornet (4)", Role.RadioButton)) /* issue 174 */) { checkTheNotes(); rest() },
        Entry("how-should-the-score-be") { checkTheNotes(); go(Screen.OUTPUT) },
        Entry("score", notReached = setOf(Control("Solo Cornet (you)", Role.Button), Control("Music stand", Role.Button)) /* issue 174 */) { theScore() },
        Entry("score-more") { theScore(); more(); rest() },
        Entry("music-stand", ownOrder = "the stand's controls are three groups side by side, and the keyboard takes the transport first") {
            theScore()
            // (From the sheet of what the row has no room for: it always has the stand.)
            more()
            rule.onNodeWithTag("performance").performScrollTo().performClick()
            waitForTag("stand-score", 20_000)
            rest()
        },
        Entry("share-or-print") { checkTheNotes(); go(Screen.SCORE); waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }; go(Screen.EXPORT); rest() },
        Entry("settings") { go(Screen.SETTINGS) },
        Entry("computer") { go(Screen.SETTINGS, Screen.COMPANION) },
        Entry("computer-scanner") { pairingScanner(); waitForTag("pair-camera", 5_000) },
        Entry("about") { go(Screen.SETTINGS, Screen.ABOUT) },
        Entry("help") { go(Screen.HELP) },
        Entry("problem") { rule.runOnUiThread { vm.showProblem(Problem.FILE_UNREADABLE) } },
        Entry("problem-recording-kept") { aRecordingWithoutItsScore() },
        Entry("home-with-a-kept-recording") { aRecordingWithoutItsScore(); rule.runOnUiThread { vm.home() }; rest() },
        Entry("problem-no-notes") { whatIsThis(); rule.runOnUiThread { vm.showProblem(Problem.NO_NOTES) } },
    )
}
