package no.brasscribe.play.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import no.kalli.scribe.design.ScribeButtonShape
import no.kalli.scribe.design.ScribeColors
import no.kalli.scribe.design.ScribeDarkColors
import no.kalli.scribe.design.ScribeHighContrastColors
import no.kalli.scribe.design.ScribeHighContrastLightColors
import no.kalli.scribe.design.ScribeLightColors
import no.kalli.scribe.design.ScribeMotion
import no.kalli.scribe.design.ScribeNumericStyle
import no.kalli.scribe.design.ScribeShapes
import no.kalli.scribe.design.ScribeSize
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.design.scribeColors
import no.kalli.scribe.design.scribeTypography
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The design system's neutral names (design/tokens/README.md) are the same in every product's generated
 * theme. This is compiled for each product, so a neutral name that one of them lacks fails its build.
 */
class NeutralDesignNamesTest {
    @Test fun everyProductHasTheNeutralRolesInEveryMode() {
        for (colours in listOf(ScribeLightColors, ScribeDarkColors, ScribeHighContrastColors, ScribeHighContrastLightColors)) {
            val roles: List<Color> = listOf(
                colours.bg, colours.surface, colours.surfaceRaised, colours.text, colours.textMuted, colours.border,
                colours.borderStrong, colours.primary, colours.onPrimary, colours.secondary, colours.onSecondary,
                colours.accent, colours.brand, colours.brandText, colours.brandTint, colours.success, colours.warning,
                colours.error, colours.focus, colours.scrim, colours.ink, colours.line, colours.uncertain,
            )
            assertEquals(23, roles.size)
            assertNotEquals(colours.bg, colours.text)
        }
        assertTrue(ScribeHighContrastColors.isHighContrast && ScribeHighContrastLightColors.isHighContrast)
        assertTrue(!ScribeLightColors.isHighContrast && !ScribeDarkColors.isHighContrast)
    }

    @Test fun thePaletteFollowsDarkAndTheSystemsContrast() {
        assertSame(ScribeLightColors, scribeColors(dark = false, highContrast = false))
        assertSame(ScribeDarkColors, scribeColors(dark = true, highContrast = false))
        // More contrast keeps light or dark: a light ground with dark ink, or the other way round.
        assertSame(ScribeHighContrastLightColors, scribeColors(dark = false, highContrast = true))
        assertSame(ScribeHighContrastColors, scribeColors(dark = true, highContrast = true))
        assertTrue(ScribeHighContrastLightColors.bg.luminance() > 0.8f && ScribeHighContrastLightColors.text.luminance() < 0.05f)
        assertTrue(ScribeHighContrastColors.bg.luminance() < 0.05f && ScribeHighContrastColors.text.luminance() > 0.8f)
    }

    @Test fun everyProductHasTheNeutralScales() {
        assertTrue(ScribeSpace.s4 > ScribeSpace.s2)
        assertTrue(ScribeSize.touchMin >= ScribeSize.iconLarge)
        assertTrue(ScribeMotion.base > ScribeMotion.fast)
        assertEquals(ScribeShapes.medium, ScribeButtonShape)
        assertEquals("tnum", ScribeNumericStyle.fontFeatureSettings)
        assertTrue(scribeTypography().displaySmall.fontSize.value > scribeTypography().bodyLarge.fontSize.value)
    }
}

/** Never shown: it is here so the theme and its colours are compiled where they are used. */
@Suppress("unused")
@Composable
private fun NeutralTheme() {
    ScribeTheme {
        val colors: ScribeColors = ScribeTheme.colors
        colors.brand
    }
}
