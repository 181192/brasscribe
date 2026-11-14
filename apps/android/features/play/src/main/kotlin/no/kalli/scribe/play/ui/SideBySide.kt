package no.kalli.scribe.play.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import no.kalli.scribe.design.ScribeSpace

/**
 * Two actions in one row where each has room for its words on one line, and one above the other where they have
 * not (a narrow phone, large text, longer words in another language). In the row the first takes the width the
 * second leaves; either way they are read, and reached by the keyboard, first then second.
 */
@Composable
fun SideBySideIfTheyFit(modifier: Modifier = Modifier, spacing: Dp = ScribeSpace.s3, content: @Composable () -> Unit) {
    Layout(content, modifier) { measurables, constraints ->
        require(measurables.size == 2) { "two actions, not ${measurables.size}" }
        val gap = spacing.roundToPx()
        val (first, second) = measurables
        val wide = constraints.maxWidth
        val firstWidth = first.maxIntrinsicWidth(Constraints.Infinity)
        val secondWidth = second.maxIntrinsicWidth(Constraints.Infinity)
        if (firstWidth + secondWidth + gap <= wide) {
            val b = second.measure(Constraints(minWidth = secondWidth, maxWidth = secondWidth))
            val a = first.measure(Constraints.fixedWidth(wide - gap - b.width))
            val height = maxOf(a.height, b.height)
            layout(wide, height) {
                a.placeRelative(0, (height - a.height) / 2)
                b.placeRelative(a.width + gap, (height - b.height) / 2)
            }
        } else {
            val a = first.measure(Constraints(maxWidth = wide))
            val b = second.measure(Constraints(maxWidth = wide))
            layout(wide, a.height + gap + b.height) {
                a.placeRelative(0, 0)
                b.placeRelative(0, a.height + gap)
            }
        }
    }
}
