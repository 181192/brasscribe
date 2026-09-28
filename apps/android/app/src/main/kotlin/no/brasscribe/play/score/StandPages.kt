package no.brasscribe.play.score

/** One engraved system on the stand, in view pixels, with the bars it holds (1-based, inclusive). */
data class StandSystem(val top: Float, val bottom: Float, val firstBar: Int, val lastBar: Int) {
    operator fun contains(bar: Int) = bar in firstBar..lastBar
}

/** A page of the stand: systems [first]..[last] (indexes into the system list). */
data class StandPage(val first: Int, val last: Int)

/**
 * The music stand's pages (design/music-stand.md §3): a page is whatever fits the screen, in whole
 * systems, and the next page starts with the last system of this one, so the line being read stays in
 * view across a turn. On a phone on its side (two systems a page) that turns one system at a time.
 * A tablet on its side shows one full-width page too (see ui/MusicStand.kt).
 */
class StandPages(
    val systems: List<StandSystem>,
    val viewport: Float,
    /** Height of the whole engraving: the window cannot start lower than this minus the viewport. */
    val content: Float = systems.lastOrNull()?.bottom ?: 0f,
) {
    val pages: List<StandPage> = paginate(systems, viewport)
    val count get() = pages.size

    fun clamp(page: Int) = page.coerceIn(0, (count - 1).coerceAtLeast(0))

    /** The system that holds [bar], or null before the layout is known. */
    fun systemOf(bar: Int): Int? = systems.indexOfFirst { bar in it }.takeIf { it >= 0 }
        ?: systems.indexOfLast { it.firstBar <= bar }.takeIf { it >= 0 }

    /** The page whose top system holds [bar] ("page 4 of 33"), 0-based. */
    fun pageOf(bar: Int): Int {
        val s = systemOf(bar) ?: return 0
        return clamp(pages.indexOfLast { it.first <= s }.coerceAtLeast(0))
    }

    /** The bar at the top of page [page]: the stand keeps its place as a bar, so a new layout finds it again. */
    fun topBar(page: Int): Int = pages.getOrNull(page)?.let { systems[it.first].firstBar } ?: 1

    /** The bars page [page] shows, for "Page 4 of 33, bars 13 to 20." */
    fun bars(page: Int): IntRange = pages.getOrNull(page)?.let { systems[it.first].firstBar..systems[it.last].lastBar } ?: 1..1

    private fun inView(page: Int, system: Int): Boolean = pages.getOrNull(page)?.let { system in it.first..it.last } == true

    /**
     * Where playback takes the stand from [page] when the cursor is in [bar]: the page turns when the
     * cursor reaches the start of the last system on the page, or when it has left the page (a jump).
     */
    fun followPlayback(page: Int, bar: Int): Int {
        val p = pages.getOrNull(page) ?: return pageOf(bar)
        val s = systemOf(bar) ?: return page
        if (!inView(page, s)) return pageOf(bar)
        return if (s == p.last && p.last > p.first && page + 1 < count) page + 1 else page
    }

    /** The page that shows [bar] from [page]: the same view when the bar is in it, else the bar's page. */
    fun pageShowing(page: Int, bar: Int): Int {
        if (pages.getOrNull(page) == null) return pageOf(bar)
        val s = systemOf(bar) ?: return page
        return if (inView(page, s)) page else pageOf(bar)
    }

    /**
     * The top of the visible window for page [page] (§4.3, the obscured-area contract): normally the
     * page's top system, but when the current system ([bar]) would fall under the control layer
     * ([obscured] pixels at the bottom), the window moves down so that system sits above it. Nothing
     * is engraved again, and the window moves to a system top, so nothing above is cut in half.
     */
    fun windowTop(page: Int, bar: Int?, obscured: Float = 0f): Float =
        wantedTop(page, bar, obscured).coerceAtMost(maxTop).coerceAtLeast(0f)

    /**
     * Where the window should start, before the end of the engraving stops it: a short score cannot
     * scroll that far, so what lies between the two is covered with paper ([visible]).
     */
    fun wantedTop(page: Int, bar: Int?, obscured: Float = 0f): Float {
        val p = pages.getOrNull(page) ?: return 0f
        var top = pageTop(page)
        val s = bar?.let(::systemOf)?.takeIf { it in p.first..p.last }
        if (s != null) {
            val sys = systems[s]
            val clear = viewport - obscured
            if (sys.bottom - top > clear) {
                // Down to the first system top that clears the layer, so nothing above is cut in half.
                val needed = sys.bottom - clear
                top = (p.first..s).map { systems[it].top }.firstOrNull { it >= needed } ?: minOf(needed, sys.top)
            }
        }
        return top.coerceAtLeast(0f)
    }

    /** The first page starts at the top of the engraving, with the title; the others at their top system. */
    fun pageTop(page: Int): Float = if (page == 0) 0f else systems[pages[page].first].top

    private val maxTop get() = (content - viewport).coerceAtLeast(0f)

    /**
     * What of the window from [top] belongs to page [page]: paper covers the rest, so a page after the
     * first never shows the title block (or the end of the page before), and no page shows half a system.
     */
    fun visible(page: Int, top: Float, wanted: Float = top): ClosedFloatingPointRange<Float> {
        val p = pages.getOrNull(page) ?: return 0f..viewport
        val from = maxOf(if (page == 0) 0f else systems[p.first].top - top, wanted - top).coerceIn(0f, viewport)
        return from..(systems[p.last].bottom - top).coerceIn(from, viewport)
    }

    /** Where the page ends in the window starting at [top]: below it the stand shows blank paper. */
    fun pageBottom(page: Int, top: Float): Float = visible(page, top).endInclusive

    companion object {
        fun paginate(systems: List<StandSystem>, viewport: Float): List<StandPage> {
            if (systems.isEmpty()) return emptyList()
            val out = ArrayList<StandPage>()
            var start = 0
            while (true) {
                var end = start
                val origin = if (start == 0) 0f else systems[start].top
                while (end + 1 < systems.size && systems[end + 1].bottom - origin <= viewport) end++
                out += StandPage(start, end)
                if (end >= systems.lastIndex) break
                start = if (end > start) end else start + 1
            }
            return out
        }
    }
}
