package no.brasscribe.play.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import no.brasscribe.play.model.Uncertainty
import no.brasscribe.play.ui.theme.LocalPlayTokens

/**
 * A notehead drawn with the uncertainty shape encoding from docs/accessibility/visual-design-tokens.md §2:
 * - confident: plain notehead in ink
 * - uncertain: notehead in the "uncertain" colour plus an open ring beside it
 * - very uncertain: parenthesised notehead in the "very uncertain" colour plus a filled ring
 * - checked: plain notehead with a tick
 * The shapes carry the level, so it survives greyscale and every colour-vision type.
 */
@Composable
fun NoteGlyph(level: Uncertainty, checked: Boolean, modifier: Modifier = Modifier, size: Dp = 32.dp) {
    val t = LocalPlayTokens.current
    val color = when {
        checked -> t.ink
        level == Uncertainty.UNCERTAIN -> t.uncertain
        level == Uncertainty.VERY_UNCERTAIN -> t.veryUncertain
        else -> t.ink
    }
    Canvas(modifier.size(size)) {
        val w = this.size.width
        val h = this.size.height
        val head = Size(w * 0.42f, h * 0.30f)
        val center = Offset(w * 0.45f, h * 0.55f)
        rotate(-20f, center) {
            drawOval(color, topLeft = Offset(center.x - head.width / 2, center.y - head.height / 2), size = head)
        }
        // Stem.
        drawLine(color, Offset(center.x + head.width / 2 - 1f, center.y), Offset(center.x + head.width / 2 - 1f, h * 0.08f), strokeWidth = w * 0.05f)
        if (checked) {
            drawLine(t.ink, Offset(w * 0.70f, h * 0.80f), Offset(w * 0.80f, h * 0.92f), strokeWidth = w * 0.07f)
            drawLine(t.ink, Offset(w * 0.80f, h * 0.92f), Offset(w * 0.98f, h * 0.62f), strokeWidth = w * 0.07f)
            return@Canvas
        }
        when (level) {
            Uncertainty.CONFIDENT -> Unit
            Uncertainty.UNCERTAIN ->
                drawCircle(color, radius = w * 0.09f, center = Offset(w * 0.12f, h * 0.55f), style = Stroke(width = w * 0.045f))
            Uncertainty.VERY_UNCERTAIN -> {
                // Parentheses around the head, filled ring beside it.
                val arc = Size(w * 0.18f, h * 0.44f)
                drawArc(color, 110f, 140f, false, Offset(center.x - head.width / 2 - w * 0.10f, center.y - arc.height / 2), arc, style = Stroke(w * 0.05f))
                drawArc(color, -70f, 140f, false, Offset(center.x + head.width / 2 - w * 0.08f, center.y - arc.height / 2), arc, style = Stroke(w * 0.05f))
                drawCircle(color, radius = w * 0.09f, center = Offset(w * 0.90f, h * 0.85f))
            }
        }
    }
}
