package no.brasscribe.play.ui.theme

import android.app.UiModeManager
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

/**
 * Colour tokens from docs/accessibility/design-tokens.json (checked for WCAG contrast and colour-vision
 * separation by qa/tools/contrast.py). Uncertainty is never colour alone: see NoteGlyph for the shapes.
 */
@Immutable
data class PlayTokens(
    val bg: Color,
    val surface: Color,
    val text: Color,
    val textMuted: Color,
    val ink: Color,
    val staff: Color,
    val uncertain: Color,
    val veryUncertain: Color,
    val adlibTint: Color,
    val loopTint: Color,
    val loopEdge: Color,
    val cursor: Color,
    val focus: Color,
    val error: Color,
    val highContrast: Boolean = false,
)

val LightTokens = PlayTokens(
    bg = Color(0xFFFFFFFF), surface = Color(0xFFF4F4F2), text = Color(0xFF1A1A1A), textMuted = Color(0xFF595959),
    ink = Color(0xFF000000), staff = Color(0xFF4D4D4D), uncertain = Color(0xFF0063A6), veryUncertain = Color(0xFFB04A00),
    adlibTint = Color(0xFFEEF3F8), loopTint = Color(0xFFFFF3D6), loopEdge = Color(0xFF8A5A00), cursor = Color(0xFF6B3FA0),
    focus = Color(0xFF0050B3), error = Color(0xFFB3261E),
)

val DarkTokens = PlayTokens(
    bg = Color(0xFF121212), surface = Color(0xFF1E1E1E), text = Color(0xFFEDEDED), textMuted = Color(0xFFB3B3B3),
    ink = Color(0xFFF2F2F2), staff = Color(0xFFA6A6A6), uncertain = Color(0xFF56B4E9), veryUncertain = Color(0xFFF0A04B),
    adlibTint = Color(0xFF1B2530), loopTint = Color(0xFF33290F), loopEdge = Color(0xFFE0B65C), cursor = Color(0xFFC9A7F0),
    focus = Color(0xFF8AB4F8), error = Color(0xFFF2B8B5),
)

val HighContrastTokens = PlayTokens(
    bg = Color(0xFF000000), surface = Color(0xFF000000), text = Color(0xFFFFFFFF), textMuted = Color(0xFFFFFFFF),
    ink = Color(0xFFFFFFFF), staff = Color(0xFFFFFFFF), uncertain = Color(0xFF00FFFF), veryUncertain = Color(0xFFFFFF00),
    adlibTint = Color(0xFF000000), loopTint = Color(0xFF000000), loopEdge = Color(0xFFFFFF00), cursor = Color(0xFFFF80FF),
    focus = Color(0xFFFFFF00), error = Color(0xFFFF8080), highContrast = true,
)

val LocalPlayTokens = staticCompositionLocalOf { LightTokens }

/** Android 14+ reports the system contrast level; above 0.5 is "high". */
@Composable
private fun systemHighContrast(): Boolean {
    val context = LocalContext.current
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return false
    val ui = context.getSystemService(UiModeManager::class.java) ?: return false
    return ui.contrast >= 0.5f
}

@Composable
fun PlayTheme(
    dark: Boolean = isSystemInDarkTheme(),
    highContrast: Boolean = systemHighContrast(),
    content: @Composable () -> Unit,
) {
    val t = when {
        highContrast -> HighContrastTokens
        dark -> DarkTokens
        else -> LightTokens
    }
    val scheme = if (dark || highContrast) {
        darkColorScheme(
            primary = t.cursor, onPrimary = Color.Black, background = t.bg, onBackground = t.text, surface = t.bg,
            onSurface = t.text, surfaceVariant = t.surface, onSurfaceVariant = t.textMuted, error = t.error,
            outline = t.staff, secondary = t.focus, onSecondary = Color.Black,
        )
    } else {
        lightColorScheme(
            primary = t.cursor, onPrimary = Color.White, background = t.bg, onBackground = t.text, surface = t.bg,
            onSurface = t.text, surfaceVariant = t.surface, onSurfaceVariant = t.textMuted, error = t.error,
            outline = t.staff, secondary = t.focus, onSecondary = Color.White,
        )
    }
    CompositionLocalProvider(LocalPlayTokens provides t) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
