package no.brasscribe.play.fret

import android.graphics.Bitmap
import android.graphics.Rect
import android.net.Uri
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.design.BrasscribeLightColors
import no.brasscribe.play.Appearance
import no.brasscribe.play.Screen
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.test.Smoke
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Fretscribe on a device, briefly: the app starts, a recording the phone decodes itself becomes a tab
 * on the fixture computer, the tab's page has ink on the screen, and it has ink again on its side.
 */
@RunWith(AndroidJUnit4::class)
@Smoke
class FretscribeSmokeTest : ScreenTest() {
    @After
    fun forget() = TabPlaces.forget()

    /** Pixels of the tab's area that are in the ink colour. */
    private fun ink(): Int {
        val image: Bitmap = screen()
        val area = rule.onNodeWithTag("fs-tab").fetchSemanticsNode().boundsInWindow.let { Rect(it.left.toInt(), it.top.toInt(), it.right.toInt(), it.bottom.toInt()) }
        val ink = BrasscribeLightColors.ink.toArgb()
        var n = 0
        for (y in maxOf(0, area.top) until minOf(image.height, area.bottom) step 2) for (x in maxOf(0, area.left) until minOf(image.width, area.right) step 2) {
            val p = image.getPixel(x, y)
            if (Math.abs((p shr 16 and 0xFF) - (ink shr 16 and 0xFF)) < 40 && Math.abs((p shr 8 and 0xFF) - (ink shr 8 and 0xFF)) < 40 && Math.abs((p and 0xFF) - (ink and 0xFF)) < 40) n++
        }
        return n
    }

    private fun engraved() {
        waitForTag("fs-tab", 30_000)
        waitUntil(30_000) { TabScreenProbe.view?.let { it.engraving.value != null && it.scale == TabScreenProbe.wanted } == true }
        settle()
    }

    @Test
    fun aRecordingBecomesATabWithInkOnTheScreenUprightAndOnItsSide() {
        yourInstrumentStore(rule.activity).save(YourInstrument(no.brasscribe.play.engine.FrettedInstrument.BASS_4))
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        computer("bass-line")
        val file = recording()
        rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(file)) }
        waitForTag("fs-what-continue", 20_000)
        waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-instrument"))).performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        rule.onNodeWithTag("fs-show-tab").performClick()
        engraved()
        assertEquals(Screen.SCORE, vm.screen.value.last())
        assertTrue("the tab has ink upright", ink() > 2_000)
        ScreenDevice.turn(rule, sideways = true)
        engraved()
        assertTrue("the tab has ink on its side", ink() > 2_000)
        ScreenDevice.turn(rule, sideways = false)
    }
}
