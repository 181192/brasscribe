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
 */
class StandPages(
    val systems: List<StandSystem>,
    val viewport: Float,
    /** Height of the whole engraving: the window cannot start lower than this minus the viewport. */
    val content: Float = systems.lastOrNull()?.bottom ?: 0f,
) {
    val pages: List<StandPage> = paginate(systems, viewport)
    val count get() = pages.size

    /** The system that holds [bar], or null before the layout is known. */
    fun systemOf(bar: Int): Int? = systems.indexOfFirst { bar in it }.takeIf { it >= 0 }
        ?: systems.indexOfLast { it.firstBar <= bar }.takeIf { it >= 0 }

    /** The page whose top system holds [bar] ("page 4 of 33"), 0-based. */
    fun pageOf(bar: Int): Int {
        val s = systemOf(bar) ?: return 0
        return pages.indexOfLast { it.first <= s }.coerceAtLeast(0)
    }

    /** The bar at the top of page [page]: the stand keeps its place as a bar, so a new layout finds it again. */
    fun topBar(page: Int): Int = pages.getOrNull(page)?.let { systems[it.first].firstBar } ?: 1

    /** The bars page [page] shows, for "Page 4 of 33, bars 13 to 20." */
    fun bars(page: Int): IntRange = pages.getOrNull(page)?.let { systems[it.first].firstBar..systems[it.last].lastBar } ?: 1..1

    /**
     * Where playback takes the stand from [page] when the cursor is in [bar]: the page turns when the
     * cursor reaches the start of the last system on the page, or when it has left the page (a jump).
     */
    fun followPlayback(page: Int, bar: Int): Int {
        val p = pages.getOrNull(page) ?: return pageOf(bar)
        val s = systemOf(bar) ?: return page
        return when {
            s < p.first || s > p.last -> pageOf(bar)
            s == p.last && p.last > p.first && page + 1 < count -> page + 1
            else -> page
        }
    }

    /** The page that shows [bar] from [page]: the same page when the bar is on it, else the bar's page. */
    fun pageShowing(page: Int, bar: Int): Int {
        val p = pages.getOrNull(page) ?: return pageOf(bar)
        val s = systemOf(bar) ?: return page
        return if (s in p.first..p.last) page else pageOf(bar)
    }

    /**
     * The top of the visible window for [page] (§4.3, the obscured-area contract): normally the page's
     * top system, but when the current system ([bar]) would fall under the control layer ([obscured]
     * pixels at the bottom), the window moves down so that system sits above it. Nothing is engraved again.
     */
    fun windowTop(page: Int, bar: Int?, obscured: Float = 0f): Float {
        val p = pages.getOrNull(page) ?: return 0f
        var top = systems[p.first].top
        val s = bar?.let(::systemOf)?.takeIf { it in p.first..p.last } ?: return top.coerceAtMost(maxTop).coerceAtLeast(0f)
        val sys = systems[s]
        val clear = viewport - obscured
        if (sys.bottom - top > clear) top = minOf(sys.bottom - clear, sys.top)
        return top.coerceAtMost(maxTop).coerceAtLeast(0f)
    }

    private val maxTop get() = (content - viewport).coerceAtLeast(0f)

    /** Where the page ends in the window starting at [top]: below it the stand shows blank paper, not half a system. */
    fun pageBottom(page: Int, top: Float): Float = pages.getOrNull(page)?.let { systems[it.last].bottom - top } ?: viewport

    companion object {
        fun paginate(systems: List<StandSystem>, viewport: Float): List<StandPage> {
            if (systems.isEmpty()) return emptyList()
            val out = ArrayList<StandPage>()
            var start = 0
            while (true) {
                var end = start
                while (end + 1 < systems.size && systems[end + 1].bottom - systems[start].top <= viewport) end++
                out += StandPage(start, end)
                if (end >= systems.lastIndex) break
                start = if (end > start) end else start + 1
            }
            return out
        }
    }
}
