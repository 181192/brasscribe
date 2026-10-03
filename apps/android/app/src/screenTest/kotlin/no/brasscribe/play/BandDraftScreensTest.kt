package no.brasscribe.play

import android.graphics.Bitmap
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.Profile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File

/**
 * A band draft on the phone (design/system.md §3): with no computer paired, Brass band is made on the phone
 * and What is this? says it is a quick draft; a draft score says so above the music.
 */
@RunWith(AndroidJUnit4::class)
class BandDraftScreensTest : ScreenTest() {
    override val shots = "brasscribe/band-draft"

    private fun fixture(name: String) = String(checkNotNull(ScreenDevice.fixture("old-hundredth/$name")) { name })

    @Test
    fun aBrassBandWithoutTheComputerIsADraftOnThePhone() {
        assumeTrue("no computer may be paired for this test", container.engine() == null && container.hasBandModels)
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Band practice.wav", SourceKind.FILE, 30.0, audio = PcmAudio(FloatArray(22_050 * 30), 22_050)))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.BRASS_BAND)
        }
        assertEquals(Where.DEVICE, vm.where.value)
        val title = rule.activity.getString(R.string.where_device_draft)
        waitUntil(5_000) { rule.onAllNodesWithText(title).fetchSemanticsNodes().isNotEmpty() }
        shot("what-is-this-band-draft")
    }

    @Test
    fun aDraftScoreSaysSo() {
        val composition = container.core.decodeComposition(fixture("composition.json"))
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth", SourceKind.SCORE, 0.0))
            vm.result.value = TranscriptionResult(composition, fixture("brass-band.musicxml"), Profile.BRASS_BAND, onDevice = true,
                compositionJson = fixture("composition.json"), draft = true)
            vm.navigate(Screen.SCORE)
        }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        waitUntil(5_000) { rule.onAllNodesWithTag("draft-notice").fetchSemanticsNodes().isNotEmpty() ||
            rule.onAllNodesWithText(rule.activity.getString(R.string.draft_notice_short)).fetchSemanticsNodes().isNotEmpty() }
        shot("score-draft-notice")
    }

    private fun shows(id: Int) = rule.onAllNodesWithText(text(id)).fetchSemanticsNodes().isNotEmpty()
    private fun oldHundredth() = FixtureSource { name -> ScreenDevice.fixture("old-hundredth/$name") }
    private fun draftIsOnScreen() = vm.screen.value.last() == Screen.SCORE && vm.result.value?.draft == true

    /** Coming back from "Make the full score" before it is ready, by Cancel or from a problem, shows the draft again. */
    @Test
    fun theDraftIsStillThereWhenTheFullScoreIsNotMade() {
        val take = File(rule.activity.cacheDir, "band-draft-take.wav").apply { writeBytes(ByteArray(64)) }
        val saved = container.scoreLibrary.save(null, "Old Hundredth", Profile.BRASS_BAND.id, fixture("brass-band.musicxml"),
            fixture("composition.json"), draft = true, recording = take)
        try {
            rule.runOnUiThread { vm.home(); vm.openSavedScore(saved) }
            waitUntil(10_000) { draftIsOnScreen() }

            // Cancel while the computer is making it.
            container.fixtureSource = oldHundredth()
            rule.runOnUiThread { vm.makeFullScore() }
            waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE }
            rule.runOnUiThread { vm.cancelTranscription(); vm.back() }
            waitUntil(10_000) { draftIsOnScreen() }
            waitUntil(30_000) { rule.onAllNodesWithTag("draft-notice").fetchSemanticsNodes().isNotEmpty() || shows(R.string.draft_notice_short) }

            // Back from the problem screen when the computer is gone.
            container.fixtureSource = null
            rule.runOnUiThread { vm.makeFullScore() }
            waitUntil(10_000) { vm.screen.value.last() == Screen.PROBLEM }
            rule.runOnUiThread { vm.back() }
            waitUntil(10_000) { draftIsOnScreen() }
        } finally {
            container.fixtureSource = null
            rule.runOnUiThread { vm.home() }
            container.scoreLibrary.delete(saved.id)
            take.delete()
        }
    }

    private fun showTooLong() = rule.runOnUiThread {
        vm.home()
        vm.setSource(Source("Band practice.wav", SourceKind.FILE, 900.0))
        vm.navigate(Screen.PROFILE)
        vm.chooseProfile(Profile.BRASS_BAND)
        vm.showProblem(Problem.DRAFT_TOO_LONG)
    }

    /** The phone refused the draft: try again later, or the computer when it is there; the recording stays. */
    @Test
    fun aDraftThePhoneRefusesSaysWhatToDo() {
        fun refuse() = rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Band practice.wav", SourceKind.FILE, 60.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.BRASS_BAND)
            vm.navigate(Screen.TRANSCRIBE)
            vm.draftRefused()
        }
        try {
            container.fixtureSource = null
            refuse()
            waitUntil(5_000) { shows(R.string.draft_refused_title) }
            assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.PROBLEM), vm.screen.value)
            assertTrue(shows(R.string.draft_refused_body_away) && shows(R.string.retry) && shows(R.string.draft_too_long_kept))
            assertTrue(!shows(R.string.draft_make_on_computer))
            rule.onNodeWithText(text(R.string.back)).performClick()
            waitUntil(5_000) { vm.screen.value.last() == Screen.PROFILE }
            assertEquals("Band practice.wav", vm.source.value?.name)

            rule.runOnUiThread { vm.home() }
            waitUntil(5_000) { !shows(R.string.draft_refused_title) }
            container.fixtureSource = oldHundredth()
            refuse()
            waitUntil(5_000) { shows(R.string.draft_make_on_computer) }
            assertTrue(shows(R.string.draft_refused_body) && shows(R.string.retry))
        } finally {
            rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
            container.fixtureSource = null
        }
    }

    /** A take too long for a draft: the way forward is the computer, and going back keeps the recording. */
    @Test
    fun aTakeTooLongForADraftGoesToTheComputer() {
        try {
            // No computer: the words say to open Brasscribe there; no button promises what can't be done.
            container.fixtureSource = null
            showTooLong()
            waitUntil(5_000) { shows(R.string.draft_too_long_title) }
            // nothing is paired: the words say to pair first
            assertTrue(shows(R.string.draft_too_long_body_unpaired) && shows(R.string.draft_too_long_kept) && shows(R.string.problem_choose_another_recording))
            assertTrue(!shows(R.string.draft_make_on_computer) && !shows(R.string.problem_choose_another))
            shot("too-long-no-computer")
            rule.onNodeWithText(text(R.string.back)).performClick()
            waitUntil(5_000) { vm.screen.value.last() == Screen.PROFILE }
            assertEquals("Band practice.wav", vm.source.value?.name)

            // The computer is there: the primary makes the score there, from the same recording.
            rule.runOnUiThread { vm.home() }
            waitUntil(5_000) { !shows(R.string.draft_too_long_title) }
            container.fixtureSource = oldHundredth()
            showTooLong()
            waitUntil(5_000) { shows(R.string.draft_make_on_computer) }
            assertTrue(shows(R.string.draft_too_long_body) && shows(R.string.draft_too_long_kept))
            shot("too-long-computer-there")
            rule.onNodeWithText(text(R.string.draft_make_on_computer)).performClick()
            waitUntil(5_000) { vm.screen.value.last() == Screen.TRANSCRIBE }
            assertEquals(Where.COMPANION, vm.where.value)
            assertEquals("Band practice.wav", vm.source.value?.name)
        } finally {
            rule.runOnUiThread { vm.cancelTranscription(); vm.home() }
            container.fixtureSource = null
        }
    }
}
