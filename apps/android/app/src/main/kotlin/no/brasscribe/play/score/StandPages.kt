package no.brasscribe.play.score

/** One engraved system on the stand, in view pixels, with the bars it holds (1-based, inclusive). */
data class StandSystem(val top: Float, val bottom: Float, val firstBar: Int, val lastBar: Int) {
    operator fun contains(bar: Int) = bar in firstBar..lastBar
}

/** A page of the stand: systems [first]..[last] (indexes into the system list). */
data class StandPage(val first: Int, val last: Int)

/**
 * The music stand's pages (design/music-stand.md §3). A page is whatever fits the screen, in whole
 * systems.
 * - One page at a time: the next page starts with the last system of this one, so the line being read
 *   stays in view across a turn. On a phone on its side (two systems a page) that turns one system at
 *   a time.
 * - Two pages side by side ([spread], a tablet on its side): pages follow on without overlap, and a
 *   turn moves the right page to the left, so the next line is always in view. [page] is then the
 *   left-hand page, and the last view is the last two pages.
 */
class StandPages(
    val systems: List<StandSystem>,
    val viewport: Float,
    /** Height of the whole engraving: the window cannot start lower than this minus the viewport. */
    val content: Float = systems.lastOrNull()?.bottom ?: 0f,
    val spread: Boolean = false,
) {
    val pages: List<StandPage> = paginate(systems, viewport, spread)
    val count get() = pages.size

    /** The highest page that can be on the left (the only page without a spread). */
    val lastLeft get() = if (spread) (count - 2).coerceAtLeast(0) else (count - 1).coerceAtLeast(0)

    fun clamp(page: Int) = page.coerceIn(0, lastLeft)

    /** The last page in view with [page] on the left: the right-hand page of a spread. */
    fun lastInView(page: Int) = if (spread && page + 1 < count) page + 1 else page

    /** The system that holds [bar], or null before the layout is known. */
    fun systemOf(bar: Int): Int? = systems.indexOfFirst { bar in it }.takeIf { it >= 0 }
        ?: systems.indexOfLast { it.firstBar <= bar }.takeIf { it >= 0 }

    /** The page whose top system holds [bar] ("page 4 of 33"), 0-based, as a left-hand page. */
    fun pageOf(bar: Int): Int {
        val s = systemOf(bar) ?: return 0
        return clamp(pages.indexOfLast { it.first <= s }.coerceAtLeast(0))
    }

    /** The bar at the top of page [page]: the stand keeps its place as a bar, so a new layout finds it again. */
    fun topBar(page: Int): Int = pages.getOrNull(page)?.let { systems[it.first].firstBar } ?: 1

    /** The bars in view with [page] on the left, for "Page 4 of 33, bars 13 to 20." */
    fun bars(page: Int): IntRange {
        val p = pages.getOrNull(page) ?: return 1..1
        return systems[p.first].firstBar..systems[pages[lastInView(page)].last].lastBar
    }

    private fun inView(page: Int, system: Int): Boolean {
        val p = pages.getOrNull(page) ?: return false
        return system in p.first..pages[lastInView(page)].last
    }

    /**
     * Where playback takes the stand from [page] when the cursor is in [bar]: the view turns when the
     * cursor reaches the start of the last system on a single page, or the right-hand page of a spread,
     * or when it has left the view (a jump).
     */
    fun followPlayback(page: Int, bar: Int): Int {
        val p = pages.getOrNull(page) ?: return pageOf(bar)
        val s = systemOf(bar) ?: return page
        if (!inView(page, s)) return pageOf(bar)
        if (spread) return if (s > p.last) clamp(page + 1) else page
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
     * is engraved again. The left (or only) page cannot scroll past the engraving; the right-hand page of
     * a spread is drawn from anywhere ([scrollable] false).
     */
    fun windowTop(page: Int, bar: Int?, obscured: Float = 0f, scrollable: Boolean = true): Float {
        val p = pages.getOrNull(page) ?: return 0f
        var top = pageTop(page)
        val s = bar?.let(::systemOf)?.takeIf { it in p.first..p.last }
        if (s != null) {
            val sys = systems[s]
            val clear = viewport - obscured
            if (sys.bottom - top > clear) top = minOf(sys.bottom - clear, sys.top)
        }
        return (if (scrollable) top.coerceAtMost(maxTop) else top).coerceAtLeast(0f)
    }

    /** The first page starts at the top of the engraving, with the title; the others at their top system. */
    fun pageTop(page: Int): Float = if (page == 0) 0f else systems[pages[page].first].top

    private val maxTop get() = (content - viewport).coerceAtLeast(0f)

    /**
     * What of the window from [top] belongs to page [page]: paper covers the rest, so a page after the
     * first never shows the title block (or the end of the page before), and no page shows half a system.
     */
    fun visible(page: Int, top: Float): ClosedFloatingPointRange<Float> {
        val p = pages.getOrNull(page) ?: return 0f..viewport
        val from = if (page == 0) 0f else (systems[p.first].top - top).coerceAtLeast(0f)
        return from..(systems[p.last].bottom - top).coerceIn(from, viewport)
    }

    /** Where the page ends in the window starting at [top]: below it the stand shows blank paper. */
    fun pageBottom(page: Int, top: Float): Float = visible(page, top).endInclusive

    companion object {
        fun paginate(systems: List<StandSystem>, viewport: Float, spread: Boolean = false): List<StandPage> {
            if (systems.isEmpty()) return emptyList()
            val out = ArrayList<StandPage>()
            var start = 0
            while (true) {
                var end = start
                val origin = if (start == 0) 0f else systems[start].top
                while (end + 1 < systems.size && systems[end + 1].bottom - origin <= viewport) end++
                out += StandPage(start, end)
                if (end >= systems.lastIndex) break
                // A single page keeps its last system as the next page's first; a spread follows on.
                start = if (!spread && end > start) end else end + 1
            }
            return out
        }
    }
}
