package no.brasscribe.play

import android.graphics.Bitmap
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.text.font.FontWeight
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.design.BrasscribeDarkColors
import no.brasscribe.design.BrasscribeHighContrastColors
import no.brasscribe.design.BrasscribeLightColors
import no.brasscribe.design.brasscribeTypography
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Fretscribe wears its own brand: Home in light, dark and high contrast has Fretscribe's paper and its
 * blue-ink mark, and the titles are set in Atkinson Hyperlegible Next.
 */
@RunWith(AndroidJUnit4::class)
class FretscribeThemeTest : ScreenTest() {
    override val shots = "fretscribe/theme"

    private fun home(name: String): Bitmap {
        rule.runOnUiThread { vm.home() }
        waitUntil(5_000) { rule.onAllNodesWithText(Product.NAME).fetchSemanticsNodes().isNotEmpty() }
        settle()
        shot(name)
        return screen()
    }

    /** How many pixels of the screenshot have exactly this colour (anti-aliased edges don't count). */
    private fun Bitmap.count(colour: androidx.compose.ui.graphics.Color): Int {
        val want = android.graphics.Color.argb(255, (colour.red * 255 + 0.5f).toInt(), (colour.green * 255 + 0.5f).toInt(), (colour.blue * 255 + 0.5f).toInt())
        val pixels = IntArray(width * height).also { getPixels(it, 0, width, 0, 0, width, height) }
        return pixels.count { it == want }
    }

    private fun assertWears(shot: Bitmap, colours: no.brasscribe.design.BrasscribeColors, mode: String) {
        val all = shot.width * shot.height
        assertTrue("$mode: the ground is Fretscribe's paper", shot.count(colours.bg) > all / 3)
        // The mark beside the wordmark is drawn in the brand colour: blue ink, never brass.
        assertTrue("$mode: the mark is in blue ink", shot.count(colours.brass) > 200)
    }

    @Test
    fun homeWearsFretscribesColoursAndTitleFace() {
        assertEquals("Fretscribe", Product.NAME)
        // The display face is Atkinson Hyperlegible Next (its name is in the font file), set at 600.
        val font = rule.activity.resources.openRawResource(R.font.display).use { it.readBytes() }
        val name = "Atkinson Hyperlegible Next".toByteArray(Charsets.UTF_16BE)
        assertTrue("res/font/display is Atkinson Hyperlegible Next", font.asList().windowed(name.size).any { it == name.asList() })
        assertEquals(FontWeight.SemiBold, brasscribeTypography().displaySmall.fontWeight)
        // Blue ink in every palette, and no Pink: its palettes are the standard ones.
        assertEquals(androidx.compose.ui.graphics.Color(0xFF1F5FAD), BrasscribeLightColors.brass)
        assertEquals(androidx.compose.ui.graphics.Color(0xFF8AB8F2), BrasscribeDarkColors.brass)

        ScreenDevice.night(rule, false)
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        assertWears(home("home-light"), BrasscribeLightColors, "light")

        // Dark from the app's own Appearance setting, whatever the phone says.
        rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
        assertWears(home("home-dark"), BrasscribeDarkColors, "dark")

        // The phone's contrast setting (Android 14 and later) wins over both.
        assumeTrue("this device does not take the contrast setting", ScreenDevice.highContrast(rule, true))
        assertWears(home("home-high-contrast"), BrasscribeHighContrastColors, "high contrast")
    }
}
