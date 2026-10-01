package no.brasscribe.play.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.design.brasscribeTypography
import no.brasscribe.play.R

/**
 * The brand's display face (res/font/display: Instrument Serif in Brasscribe, Atkinson Hyperlegible Next
 * in Fretscribe): only for screen titles of 28 sp and up and the wordmark
 * (MaterialTheme.typography.displaySmall). Everything else is Roboto. The font is declared at the weight
 * the generated type ramp sets titles in. Brasscribe's is a static regular. Fretscribe's is a variable
 * font set in 600: its weight axis is named on its own, since the default settings also name an italic
 * axis the font lacks, and then Android applies none of them. The italic is synthesised from the upright,
 * as the design folder ships only that file.
 */
private val DisplayWeight = brasscribeTypography().displaySmall.fontWeight ?: FontWeight.Normal
val DisplayFace = FontFamily(
    if (DisplayWeight == FontWeight.Normal) {
        Font(R.font.display, FontWeight.Normal, FontStyle.Normal)
    } else {
        Font(R.font.display, DisplayWeight, FontStyle.Normal,
            variationSettings = FontVariation.Settings(FontVariation.weight(DisplayWeight.weight)))
    },
)

/**
 * The app's one theme entry point: the product's generated theme (design/dist/android or
 * design/fretscribe/dist/android: colour scheme,
 * type ramp, shapes) with the display face. Colours come from [BrasscribeTheme.colors]; the score
 * palette (uncertain, very uncertain, loop, cursor) is for the notation only. [dark] is the resolved
 * Settings › Display › Appearance: the score and every dialog take their colours from here, never from
 * the phone's night mode directly. [pink] is the hidden Pink palette (light or dark by [dark]). The
 * phone's high contrast still wins over both.
 */
@Composable
fun PlayTheme(dark: Boolean = isSystemInDarkTheme(), pink: Boolean = false, content: @Composable () -> Unit) {
    BrasscribeTheme(dark = dark, pink = pink, display = DisplayFace, content = content)
}
