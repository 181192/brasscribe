package no.brasscribe.play

import android.graphics.Bitmap
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.engine.Profile
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * A band draft on the phone (design/system.md §3): with no computer paired, Brass band is made on the phone
 * and What is this? says it is a quick draft; a draft score says so above the music. Screenshots go to the
 * app's files, band-draft/.
 */
@RunWith(AndroidJUnit4::class)
class BandDraftScreensTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]
    private val container get() = (rule.activity.application as PlayApplication).container
    private val dir by lazy { File(rule.activity.getExternalFilesDir(null), "band-draft").apply { mkdirs() } }

    private fun shot(name: String) {
        rule.waitForIdle()
        Thread.sleep(700)
        instrumentation.uiAutomation.takeScreenshot()?.let { b -> File(dir, "$name.png").outputStream().use { b.compress(Bitmap.CompressFormat.PNG, 100, it) } }
    }

    private fun fixture(name: String) = instrumentation.context.assets.open("old-hundredth/$name").use { String(it.readBytes()) }

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
        rule.waitUntil(5_000) { rule.onAllNodesWithText(title).fetchSemanticsNodes().isNotEmpty() }
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
        rule.waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true }
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("draft-notice").fetchSemanticsNodes().isNotEmpty() ||
            rule.onAllNodesWithText(rule.activity.getString(R.string.draft_notice_short)).fetchSemanticsNodes().isNotEmpty() }
        shot("score-draft-notice")
    }
}
