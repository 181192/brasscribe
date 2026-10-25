package no.kalli.scribe.tab

/**
 * The tab in full screen: the system bars, the top bar, the header and the player step aside and the tab has the whole
 * screen. A tap on the tab brings the controls back over it ([controls]); while the recording plays they step aside again
 * by themselves. Leaving the mode brings everything back.
 *
 * With a screen reader that is explored by touch the controls stay up: there is no tap on the tab to bring them back.
 */
data class TabFocus(val on: Boolean = false, val controls: Boolean = false) {
    fun enter() = TabFocus(on = true)

    fun leave() = TabFocus()

    /** A tap on the tab shows the controls, and a second one hides them. Outside the mode it does nothing. */
    fun tapped() = if (on) copy(controls = !controls) else this

    /** The controls over the tab (the player, zoom and Leave full screen) are on screen. */
    fun controlsShown(assistive: Boolean) = on && (controls || assistive)

    /** Only the small buttons are on screen: Play or Pause, and Leave full screen. */
    fun minimal(assistive: Boolean) = on && !controlsShown(assistive)

    /** The controls hide by themselves [HIDE_AFTER_MS] after the last touch, only while the recording plays. */
    fun autoHides(playing: Boolean, assistive: Boolean) = on && controls && playing && !assistive

    companion object {
        const val HIDE_AFTER_MS = 4_000L
    }
}
