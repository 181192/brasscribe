package no.brasscribe.play

import android.content.Context
import androidx.compose.ui.graphics.toArgb
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.scribe.design.scribeColors
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** The window behind Compose is the ground of the palette the app draws in, with the phone's high contrast too. */
@RunWith(AndroidJUnit4::class)
class WindowColorTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test
    fun theWindowIsThePalettesGroundInEveryAppearance() {
        for (dark in listOf(false, true)) for (highContrast in listOf(false, true)) {
            assertEquals(
                "dark $dark, high contrast $highContrast",
                scribeColors(dark, highContrast).bg.toArgb(),
                context.getColor(windowColor(dark, pink = false, highContrast = highContrast)),
            )
        }
    }

    @Test
    fun highContrastWinsOverPinkAsInTheTheme() {
        for (dark in listOf(false, true)) {
            assertEquals(windowColor(dark, pink = false, highContrast = true), windowColor(dark, pink = true, highContrast = true))
        }
        assertEquals(R.color.window_pink, windowColor(dark = false, pink = true, highContrast = false))
        assertEquals(R.color.window_pink_dark, windowColor(dark = true, pink = true, highContrast = false))
    }
}
