package no.brasscribe.play

import android.app.UiAutomation
import android.graphics.Bitmap
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.engine.Profile
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File

/**
 * "What do you play?" end to end, with screenshots of its screens in English and bokmål, light and dark:
 * the first run empty, with an instrument and chosen, Settings, the score with its source label and
 * mapping notice, and Review with "Your part is arranged". The first run also at 200 % text and on its side.
 */
@RunWith(AndroidJUnit4::class)
class MyInstrumentScreensTest : ScreenTest() {
    override val shots = "brasscribe/my-instrument"

    @After
    fun tearDown() {
        rule.runOnUiThread {
            container.updateSeat(SeatChoice.NotSet)
            container.firstRunDone = true
        }
    }

    private fun startFirstRun() {
        rule.runOnUiThread {
            container.updateSeat(SeatChoice.NotSet)
            container.firstRunDone = false
            vm.finishFirstRun()
        }
        waitUntil(5_000) { rule.onAllNodesWithTag("seat-continue").fetchSemanticsNodes().isNotEmpty() }
    }

    private fun fixture(name: String) = String(checkNotNull(ScreenDevice.fixture("old-hundredth/$name")) { name })

    private fun openResult(r: TranscriptionResult, screen: Screen) {
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth", SourceKind.SCORE, 0.0))
            vm.result.value = r
            vm.navigate(screen)
        }
    }

    @Test
    fun screensInEnglishAndBokmalLightAndDark() {
        for (lang in listOf("en-GB", "nb-NO")) {
            language(lang)
            for (appearance in listOf(Appearance.LIGHT, Appearance.DARK)) {
                rule.runOnUiThread { container.updateAppearance(appearance) }
                val tag = "${lang.take(2)}-${appearance.key}"
                startFirstRun()
                // Nothing is chosen, and Continue says why it waits.
                rule.onNodeWithTag("seat-continue").assertIsNotEnabled()
                shot("first-run-empty-$tag")
                rule.onNodeWithTag("instrument-baritone").performClick()
                rule.onNodeWithTag("seat-continue").assertIsNotEnabled()
                rule.onNodeWithTag("seat-part-1st-baritone").performScrollTo()
                shot("first-run-part-$tag")
                rule.onNodeWithTag("seat-part-1st-baritone").performClick()
                rule.onNodeWithTag("seat-continue").assertIsEnabled()
                shot("first-run-chosen-$tag")
                rule.onNodeWithTag("seat-continue").performClick()
                rule.waitForIdle()
                assertEquals(SeatChoice.Player("1st-baritone", "treble"), container.seat)
                assertTrue(container.firstRunDone)

                rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
                waitUntil(5_000) { rule.onAllNodesWithTag("setting-seat").fetchSemanticsNodes().isNotEmpty() }
                shot("settings-$tag")

                // The small band has no 1st Baritone: the score opens on Euphonium and says so.
                val composition = container.core.decodeComposition(fixture("composition.json"))
                val small = composition.arrangedFor(Lineup.MINIMAL, "faithful")
                val xml = container.core.arrangeMusicXmlWith(composition, no.brasscribe.play.model.ArrangeOptions(lineup = "minimal"))!!
                openResult(TranscriptionResult(small, xml, Profile.BRASS_BAND, onDevice = true, compositionJson = container.core.encodeComposition(small)), Screen.SCORE)
                waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
                waitUntil(10_000) { rule.onAllNodesWithTag("mapped-notice").fetchSemanticsNodes().isNotEmpty() }
                shot("score-$tag")

                // A 2nd Cornet in the full band: an arranged part, so Review says so instead of an empty list.
                rule.runOnUiThread { container.updateSeat(SeatChoice.Player("2nd-cornet")) }
                openResult(TranscriptionResult(composition, fixture("brass-band.musicxml"), Profile.BRASS_BAND, onDevice = true,
                    compositionJson = fixture("composition.json")), Screen.REVIEW)
                waitUntil(10_000) { rule.onAllNodesWithTag("review-arranged").fetchSemanticsNodes().isNotEmpty() }
                shot("review-arranged-$tag")
            }
        }
    }

    @Test
    fun firstRunAtLargeTextAndOnItsSide() {
        language("en-GB")
        textSize(2.0f)
        startFirstRun()
        rule.onNodeWithTag("instrument-baritone").performClick()
        shot("first-run-200")
        // At 200 % the tiles are one column and Which part? a vertical radio list: every choice is a radio.
        val radios = rule.onAllNodesWithTag("seat-part-1st-baritone").fetchSemanticsNodes() +
            rule.onAllNodesWithTag("instrument-bb-cornet").fetchSemanticsNodes()
        assertTrue(radios.all { it.config.getOrNull(SemanticsProperties.Role) == Role.RadioButton })
        textSize(1.0f)
        ScreenDevice.turn(rule, sideways = true)
        waitUntil(5_000) { rule.onAllNodesWithTag("seat-continue").fetchSemanticsNodes().isNotEmpty() }
        shot("first-run-landscape")
        // "Not now" sets nothing and is not asked again.
        rule.onNodeWithTag("seat-skip").performClick()
        rule.waitForIdle()
        assertEquals(SeatChoice.NotSet, container.seat)
        assertTrue(container.firstRunDone)
        assertTrue(rule.onAllNodesWithText("What do you play?").fetchSemanticsNodes().isEmpty())
    }
}
