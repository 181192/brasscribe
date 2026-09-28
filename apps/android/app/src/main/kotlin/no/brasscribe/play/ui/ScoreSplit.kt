package no.brasscribe.play.ui

/**
 * How a phone on its side shares its height between the score and the controls under it: the score
 * keeps at least [SCORE_SHARE] of the height inside the system bars (top bar included), and never less
 * than two staff systems while the controls keep one row. The controls scroll inside what is left.
 * All values in dp.
 */
object ScoreSplit {
    const val SCORE_SHARE = 0.55f
    /** One row of the compact controls: the 56 dp Play and its padding. */
    const val CONTROLS_ROW = 64f
    /** Below this height (dp) a landscape window counts as a phone on its side. */
    const val COMPACT_HEIGHT = 480

    fun compact(landscape: Boolean, screenHeightDp: Int): Boolean = landscape && screenHeightDp < COMPACT_HEIGHT

    /**
     * The most the controls may take of [content] (the height under the top bar), where [available] is
     * the height inside the system bars and [twoSystems] the height of two engraved systems (0 before the
     * first render).
     */
    fun controlsMax(available: Float, content: Float, twoSystems: Float): Float {
        val score = maxOf(available * SCORE_SHARE, minOf(twoSystems, content - CONTROLS_ROW))
        return (content - score).coerceAtLeast(CONTROLS_ROW)
    }
}
