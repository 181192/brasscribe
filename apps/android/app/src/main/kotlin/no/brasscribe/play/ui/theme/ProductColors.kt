package no.brasscribe.play.ui.theme

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp

/**
 * What the screens both apps are built with draw in a product's own colours. The design's neutral roles
 * (ScribeTheme.colors) are the same names in every product; these are not, so each product hands its own
 * in (Product.Theme, which [PlayTheme] calls): Brasscribe its score colours, Fretscribe what stands in for
 * them in the screens it has from Brasscribe.
 */
@Immutable
data class ProductColors(
    /** A very doubtful note's "?" and its box. */
    val veryUncertain: Color,
    /** Band behind bars played freely. */
    val adlibTint: Color,
    /** Band behind repeated bars. */
    val loopTint: Color,
    /** The playback cursor. */
    val cursor: Color,
    /** Selected notes, and the box around them. */
    val selectionTint: Color,
    val selectionEdge: Color,
    /** The focus ring around the score. */
    val focusWidth: Dp,
)

val LocalProductColors = staticCompositionLocalOf<ProductColors> { error("PlayTheme is not around this screen") }

/** The product's own colours for the shared screens, inside [PlayTheme]. */
val productColors: ProductColors
    @Composable @ReadOnlyComposable get() = LocalProductColors.current
