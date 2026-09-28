package no.brasscribe.play.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.R

/**
 * Instrument Serif, the brand's display face: only for screen titles of 28 sp and up and the wordmark
 * (MaterialTheme.typography.displaySmall). Everything else is Roboto. The italic is synthesised from
 * the regular, as the design folder ships only that file.
 */
val InstrumentSerif = FontFamily(
    Font(R.font.instrument_serif, FontWeight.Normal, FontStyle.Normal),
)

/**
 * The app's one theme entry point: the generated Brasscribe theme (design/dist/android, colour scheme,
 * type ramp, shapes) with the display face. Colours come from [BrasscribeTheme.colors]; the score
 * palette (uncertain, very uncertain, loop, cursor) is for the notation only. [dark] is the resolved
 * Settings › Display › Appearance: the score and every dialog take their colours from here, never from
 * the phone's night mode directly. The phone's high contrast still wins over it.
 */
@Composable
fun PlayTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    BrasscribeTheme(dark = dark, display = InstrumentSerif, content = content)
}
