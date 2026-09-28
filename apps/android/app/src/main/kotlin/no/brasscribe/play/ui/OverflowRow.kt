package no.brasscribe.play.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.Placeable
import androidx.compose.ui.layout.SubcomposeLayout
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp

/** Which items an [OverflowRow] left out of the row, for its sheet: from [firstHidden] to the end. */
class OverflowRowState {
    var firstHidden: Int = Int.MAX_VALUE
        internal set
}

/**
 * One line of controls that never clips (system.md §7: "rows wrap, or move into a sheet"): [lead]
 * always shows, then [items] in order while they fit. What does not fit gives way to [more], which
 * opens a sheet showing the rest (the items from [OverflowRowState.firstHidden], drawn with inSheet =
 * true). With [flexibleMin] set, the last item takes the rest of the row when it has at least that
 * width, and otherwise goes to the sheet. Items are centred on the row's height.
 */
@Composable
fun OverflowRow(
    state: OverflowRowState,
    spacing: Dp,
    lead: @Composable () -> Unit,
    items: List<@Composable (inSheet: Boolean) -> Unit>,
    more: @Composable () -> Unit,
    modifier: Modifier = Modifier,
    flexibleMin: Dp? = null,
) {
    SubcomposeLayout(modifier) { c ->
        val gap = spacing.roundToPx()
        val loose = c.copy(minWidth = 0, minHeight = 0)
        val max = c.maxWidth
        val leadP = subcompose("lead", lead).map { it.measure(loose) }
        val leadW = leadP.maxOfOrNull { it.width } ?: 0
        val flexMin = flexibleMin?.roundToPx()
        val fixedCount = if (flexMin != null && items.isNotEmpty()) items.size - 1 else items.size
        val fixed = (0 until fixedCount).map { i -> subcompose(i) { items[i](false) }.map { it.measure(loose) } }
        val widths = fixed.map { ps -> ps.maxOfOrNull { it.width } ?: 0 }
        val fixedEnd = leadW + widths.sumOf { gap + it }
        val placed = ArrayList<List<Placeable>>()
        placed += leadP
        val shown: Int
        if (fixedEnd <= max && (flexMin == null || items.size == fixedCount || max - fixedEnd - gap >= flexMin)) {
            placed += fixed
            if (flexMin != null && items.size > fixedCount) {
                val w = max - fixedEnd - gap
                placed += subcompose(fixedCount) { items[fixedCount](false) }.map { it.measure(Constraints(minWidth = w, maxWidth = w, maxHeight = c.maxHeight)) }
            }
            shown = items.size
        } else {
            val moreP = subcompose("more", more).map { it.measure(loose) }
            val budget = max - gap - (moreP.maxOfOrNull { it.width } ?: 0)
            var end = leadW
            var k = 0
            while (k < fixedCount && end + gap + widths[k] <= budget) { end += gap + widths[k]; placed += fixed[k]; k++ }
            placed += moreP
            shown = k
        }
        state.firstHidden = if (shown >= items.size) Int.MAX_VALUE else shown
        val height = placed.flatten().maxOfOrNull { it.height } ?: 0
        layout(max, height) {
            var x = 0
            for (group in placed) {
                val w = group.maxOfOrNull { it.width } ?: 0
                for (p in group) p.placeRelative(x, (height - p.height) / 2)
                x += w + gap
            }
        }
    }
}
