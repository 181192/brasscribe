package no.kalli.scribe.tab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Full screen for the tab: what shows when, without a screen. */
class TabFocusTest {
    @Test
    fun startsOutsideTheModeWithNothingToHide() {
        val focus = TabFocus()
        assertFalse(focus.on)
        assertFalse(focus.controlsShown(assistive = false))
        assertFalse(focus.minimal(assistive = false))
    }

    @Test
    fun enteringHidesTheControlsLeavingBringsEverythingBack() {
        val inside = TabFocus().enter()
        assertTrue(inside.on)
        assertTrue(inside.minimal(assistive = false))
        assertFalse(inside.controlsShown(assistive = false))
        assertEquals(TabFocus(), inside.tapped().leave())
    }

    @Test
    fun aTapShowsTheControlsAndASecondOneHidesThem() {
        val shown = TabFocus().enter().tapped()
        assertTrue(shown.controlsShown(assistive = false))
        assertFalse(shown.minimal(assistive = false))
        assertFalse(shown.tapped().controlsShown(assistive = false))
    }

    @Test
    fun aTapOutsideTheModeDoesNothing() {
        assertEquals(TabFocus(), TabFocus().tapped())
    }

    @Test
    fun theControlsHideByThemselvesOnlyWhilePlayingAndWithoutAScreenReader() {
        val shown = TabFocus().enter().tapped()
        assertTrue(shown.autoHides(playing = true, assistive = false))
        assertFalse(shown.autoHides(playing = false, assistive = false))
        assertFalse(shown.autoHides(playing = true, assistive = true))
        assertFalse(TabFocus().enter().autoHides(playing = true, assistive = false))
        assertFalse(TabFocus().autoHides(playing = true, assistive = false))
    }

    @Test
    fun withAScreenReaderTheControlsStayUp() {
        val inside = TabFocus().enter()
        assertTrue(inside.controlsShown(assistive = true))
        assertFalse(inside.minimal(assistive = true))
    }
}
