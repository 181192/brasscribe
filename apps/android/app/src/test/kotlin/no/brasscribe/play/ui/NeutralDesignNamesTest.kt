package no.brasscribe.play.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeDarkColors
import no.brasscribe.design.BrasscribeHighContrastColors
import no.brasscribe.design.BrasscribeHighContrastLightColors
import no.brasscribe.design.BrasscribeLightColors
import no.brasscribe.design.BrasscribeMotion
import no.brasscribe.design.BrasscribeNumericStyle
import no.brasscribe.design.BrasscribeShapes
import no.brasscribe.design.BrasscribeSize
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.LocalBrasscribeColors
import no.brasscribe.design.LocalScribeColors
import no.brasscribe.design.ScribeButtonShape
import no.brasscribe.design.ScribeColors
import no.brasscribe.design.ScribeDarkColors
import no.brasscribe.design.ScribeHighContrastColors
import no.brasscribe.design.ScribeHighContrastLightColors
import no.brasscribe.design.ScribeLightColors
import no.brasscribe.design.ScribeMotion
import no.brasscribe.design.ScribeNumericStyle
import no.brasscribe.design.ScribeShapes
import no.brasscribe.design.ScribeSize
import no.brasscribe.design.ScribeSpace
import no.brasscribe.design.ScribeTheme
import no.brasscribe.design.accent
import no.brasscribe.design.brand
import no.brasscribe.design.brandText
import no.brasscribe.design.brandTint
import no.brasscribe.design.brasscribeTypography
import no.brasscribe.design.line
import no.brasscribe.design.scribeTypography
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

/**
 * The design system's neutral names (design/tokens/README.md) are the same in every product's generated
 * theme. This is compiled for each product, so a neutral name that one of them lacks fails its build, and it
 * checks that each name reads the product's own theme.
 */
class NeutralDesignNamesTest {
    @Test fun theNeutralColoursAreTheProductsOwn() {
        val modes = listOf(
            ScribeLightColors to BrasscribeLightColors,
            ScribeDarkColors to BrasscribeDarkColors,
            ScribeHighContrastColors to BrasscribeHighContrastColors,
            ScribeHighContrastLightColors to BrasscribeHighContrastLightColors,
        )
        for ((neutral, own) in modes) {
            assertSame(own, neutral)
            assertEquals(own.brass, neutral.brand)
            assertEquals(own.brassText, neutral.brandText)
            assertEquals(own.brassText, neutral.accent)
            assertEquals(own.brassTint, neutral.brandTint)
            assertEquals(own.staff, neutral.line)
            // The roles with one name in both: surfaces, text, edges, fills, status, focus, ink and doubt.
            val shared: List<Color> = listOf(
                neutral.bg, neutral.surface, neutral.surfaceRaised, neutral.text, neutral.textMuted, neutral.border,
                neutral.borderStrong, neutral.primary, neutral.onPrimary, neutral.secondary, neutral.onSecondary,
                neutral.success, neutral.warning, neutral.error, neutral.focus, neutral.scrim, neutral.ink, neutral.uncertain,
            )
            assertEquals(18, shared.size)
        }
        assertSame(LocalBrasscribeColors, LocalScribeColors)
    }

    @Test fun theNeutralScalesAreTheProductsOwn() {
        assertEquals(BrasscribeSpace.s4, ScribeSpace.s4)
        assertEquals(BrasscribeSize.touchMin, ScribeSize.touchMin)
        assertEquals(BrasscribeMotion.base, ScribeMotion.base)
        assertSame(BrasscribeMotion.standardEasing, ScribeMotion.standardEasing)
        assertSame(BrasscribeShapes, ScribeShapes)
        assertSame(BrasscribeButtonShape, ScribeButtonShape)
        assertSame(BrasscribeNumericStyle, ScribeNumericStyle)
        assertEquals(brasscribeTypography().bodyLarge, scribeTypography().bodyLarge)
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
