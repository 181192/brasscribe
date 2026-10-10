package no.brasscribe.play

import android.graphics.Bitmap
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
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
 * The hidden Pink palette end to end: hidden in Appearance, five activations of the version on About
 * unlock it with a confirmation, then Pink light and Pink dark are chosen and the app turns pink.
 */
@RunWith(AndroidJUnit4::class)
class PinkThemeTest : ScreenTest() {
    override val shots = "brasscribe/pink"

    @After
    fun tearDown() {
        rule.runOnUiThread { container.forgetPink() }
    }

    private fun fixture(name: String) = String(checkNotNull(ScreenDevice.fixture("old-hundredth/$name")) { name })

    private fun openSettingsDialog() {
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
        waitUntil(5_000) { rule.onAllNodesWithTag("setting-appearance").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("setting-appearance").performScrollTo().performClick()
        waitUntil(5_000) { rule.onAllNodesWithTag("appearance-system").fetchSemanticsNodes().isNotEmpty() }
    }

    private fun openScore() {
        val composition = container.core.decodeComposition(fixture("composition.json"))
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth", SourceKind.SCORE, 0.0))
            vm.result.value = TranscriptionResult(composition, fixture("brass-band.musicxml"), Profile.BRASS_BAND, onDevice = true,
                compositionJson = fixture("composition.json"))
            vm.navigate(Screen.SCORE)
        }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
    }

    @Test
    fun unlockFromAboutThenChoosePinkLightAndDark() {
        ScreenDevice.night(rule, false)
        rule.runOnUiThread { container.forgetPink(); container.updateAppearance(Appearance.LIGHT) }

        // Hidden until unlocked.
        openSettingsDialog()
        assertTrue(rule.onAllNodesWithTag("appearance-pink-light").fetchSemanticsNodes().isEmpty())
        assertTrue(rule.onAllNodesWithTag("appearance-pink-dark").fetchSemanticsNodes().isEmpty())
        rule.onNodeWithTag("appearance-light").performClick()

        // The version is a button (TalkBack and keyboards reach it); five presses unlock Pink once.
        rule.runOnUiThread { vm.navigate(Screen.ABOUT) }
        waitUntil(5_000) { rule.onAllNodesWithTag("about-version").fetchSemanticsNodes().isNotEmpty() }
        val version = rule.onNodeWithTag("about-version").performScrollTo()
        assertEquals(Role.Button, version.fetchSemanticsNode().config.getOrNull(SemanticsProperties.Role))
        // It is the app's own version (only the screen catalogue shows a fixed one in its place).
        assertEquals(rule.activity.getString(R.string.about_version, BuildConfig.VERSION_NAME),
            version.fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text)?.joinToString("") { it.text })
        repeat(4) { version.performClick() }
        assertTrue(!container.pinkUnlocked)
        version.performClick()
        assertTrue(container.pinkUnlocked)
        val confirmation = rule.activity.getString(R.string.pink_unlocked)
        waitUntil(5_000) { rule.onAllNodesWithText(confirmation).fetchSemanticsNodes().isNotEmpty() }
        shot("about-unlocked-pink")

        // Now listed as Pink light and Pink dark, each a radio row named by its label.
        openSettingsDialog()
        shot("settings-dialog-light")
        for ((tag, label) in listOf("appearance-pink-light" to R.string.appearance_pink_light, "appearance-pink-dark" to R.string.appearance_pink_dark)) {
            val row = rule.onNodeWithTag(tag).fetchSemanticsNode()
            assertEquals(Role.RadioButton, row.config.getOrNull(SemanticsProperties.Role))
            assertEquals(rule.activity.getString(label), row.config.getOrNull(SemanticsProperties.Text)?.joinToString { it.text })
        }
        rule.onNodeWithTag("appearance-pink-light").performClick()
        assertEquals(Appearance.PINK_LIGHT, container.appearance)
        shot("settings-pink")
        openScore()
        shot("score-pink")

        // Pink dark is dark whatever the phone says.
        openSettingsDialog()
        rule.onNodeWithTag("appearance-pink-dark").performClick()
        assertEquals(Appearance.PINK_DARK, container.appearance)
        shot("settings-pink-dark")
        openScore()
        shot("score-pink-dark")

        // Switching it off is choosing another option; Pink stays listed.
        openSettingsDialog()
        rule.onNodeWithTag("appearance-system").performClick()
        assertEquals(Appearance.SYSTEM, container.appearance)
        assertTrue(container.pinkUnlocked)
    }
}
