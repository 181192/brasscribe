package no.brasscribe.play

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.test.Smoke
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Brasscribe on a device, briefly: the app starts, a recording becomes a score on the fixture computer
 * ("Old Hundredth"), the score has notation on the screen, and it still has it on its side.
 */
@RunWith(AndroidJUnit4::class)
@Smoke
class BrasscribeSmokeTest : ScreenTest() {
    /** Share of the score view's pixels that differ clearly from its paper. */
    private fun ink(): Double {
        val bmp: Bitmap = rule.onNodeWithTag("score-view").captureToImage().asAndroidBitmap()
        fun lum(p: Int) = (android.graphics.Color.red(p) * 299 + android.graphics.Color.green(p) * 587 + android.graphics.Color.blue(p) * 114) / 1000
        val base = lum(bmp.getPixel(1, 1))
        var ink = 0
        var n = 0
        for (y in 0 until bmp.height step 2) for (x in 0 until bmp.width step 2) {
            n++
            if (kotlin.math.abs(lum(bmp.getPixel(x, y)) - base) > 80) ink++
        }
        return ink.toDouble() / n
    }

    @Test
    fun aRecordingBecomesAScoreWithNotationOnTheScreenUprightAndOnItsSide() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        rule.runOnUiThread { vm.navigate(Screen.SCORE) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        waitUntil(10_000) { ink() > 0.005 }
        assertTrue("the score has notation upright", ink() > 0.005)
        ScreenDevice.turn(rule, sideways = true)
        waitUntil(30_000) { (vm.scoreController?.renders?.value ?: 0) > 0 }
        settle()
        waitUntil(10_000) { ink() > 0.005 }
        assertTrue("the score has notation on its side", ink() > 0.005)
        ScreenDevice.turn(rule, sideways = false)
        waitUntil(10_000) { ink() > 0.005 }
    }
}
