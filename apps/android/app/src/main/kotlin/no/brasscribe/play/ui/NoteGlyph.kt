package no.brasscribe.play.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.model.Uncertainty

/**
 * A note drawn with the uncertainty encoding of docs/accessibility/visual-design-tokens.md §2, as in
 * the score: a "?" above an uncertain note and a boxed "?" above a very uncertain one, both in the
 * note's colour; confident and checked notes are plain ink. The mark carries the level, so it
 * survives greyscale and every colour-vision type.
 */
@Composable
fun NoteGlyph(level: Uncertainty, checked: Boolean, modifier: Modifier = Modifier, size: Dp = 32.dp) {
    val t = BrasscribeTheme.colors
    val shown = if (checked) Uncertainty.CONFIDENT else level
    val color = when (shown) {
        Uncertainty.UNCERTAIN -> t.uncertain
        Uncertainty.VERY_UNCERTAIN -> t.veryUncertain
        else -> t.ink
    }
    Column(modifier.width(size), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Box(Modifier.height(size * 0.62f), contentAlignment = Alignment.BottomCenter) {
            if (shown != Uncertainty.CONFIDENT) UncertainMark(shown == Uncertainty.VERY_UNCERTAIN, fontSize = (size.value * 0.36f).sp)
        }
        Canvas(Modifier.size(size)) {
            val w = this.size.width
            val h = this.size.height
            val head = Size(w * 0.42f, h * 0.30f)
            val center = Offset(w * 0.45f, h * 0.78f)
            rotate(-20f, center) {
                drawOval(color, topLeft = Offset(center.x - head.width / 2, center.y - head.height / 2), size = head)
            }
            drawLine(color, Offset(center.x + head.width / 2 - 1f, center.y), Offset(center.x + head.width / 2 - 1f, h * 0.05f), strokeWidth = w * 0.05f)
        }
    }
}
