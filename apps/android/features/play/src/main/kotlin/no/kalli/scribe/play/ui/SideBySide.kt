package no.kalli.scribe.play.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import no.kalli.scribe.design.ScribeSpace

/**
 * Two or three actions in one row where each has room for its words on one line, and otherwise the first above the
 * others (a narrow phone, large text, longer words in another language). In the row the first takes the width the
 * others leave; either way they are read, and reached by the keyboard, in their order.
 */
@Composable
fun SideBySideIfTheyFit(modifier: Modifier = Modifier, spacing: Dp = ScribeSpace.s3, content: @Composable () -> Unit) {
    Layout(content, modifier) { measurables, constraints ->
        require(measurables.size in 2..3) { "two or three actions, not ${measurables.size}" }
        val gap = spacing.roundToPx()
        val wide = constraints.maxWidth
        val first = measurables.first()
        val others = measurables.drop(1)
        val widths = others.map { it.maxIntrinsicWidth(Constraints.Infinity) }
        if (first.maxIntrinsicWidth(Constraints.Infinity) + widths.sum() + gap * others.size <= wide) {
            // One row: the first takes the width the others leave.
            val rest = others.mapIndexed { i, it -> it.measure(Constraints.fixedWidth(widths[i])) }
            val a = first.measure(Constraints.fixedWidth(wide - rest.sumOf { it.width } - gap * rest.size))
            val height = maxOf(a.height, rest.maxOf { it.height })
            layout(wide, height) {
                a.placeRelative(0, (height - a.height) / 2)
                var x = a.width + gap
                for (p in rest) { p.placeRelative(x, (height - p.height) / 2); x += p.width + gap }
            }
        } else {
            // The first on a row of its own. Two others share the row under it where each has its words on one line there
            // (the first of them as wide as its words, the last the rest); where they have not, each has a row.
            val a = first.measure(Constraints(maxWidth = wide))
            val pair = others.size == 2 && widths.sum() + gap <= wide
            val rest = if (pair) listOf(others[0].measure(Constraints.fixedWidth(widths[0])), others[1].measure(Constraints.fixedWidth(wide - gap - widths[0])))
                else others.map { it.measure(Constraints(maxWidth = wide)) }
            val height = a.height + if (pair) gap + rest.maxOf { it.height } else rest.sumOf { gap + it.height }
            layout(wide, height) {
                a.placeRelative(0, 0)
                var x = 0
                var y = a.height + gap
                for (p in rest) {
                    if (pair) { p.placeRelative(x, y + (rest.maxOf { it.height } - p.height) / 2); x += p.width + gap }
                    else { p.placeRelative(0, y); y += p.height + gap }
                }
            }
        }
    }
}
