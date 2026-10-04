package no.brasscribe.play.ui

import android.accessibilityservice.AccessibilityServiceInfo
import android.view.KeyEvent
import no.brasscribe.play.Lineup
import no.brasscribe.play.score.StandPages
import no.brasscribe.play.score.StandSystem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MusicStandTest {
    /** [n] systems of [bars] bars, each [h] pixels tall, from the top. */
    private fun systems(n: Int, bars: Int = 3, h: Float = 100f) =
        (0 until n).map { i -> StandSystem(i * h, (i + 1) * h, i * bars + 1, (i + 1) * bars) }

    @Test
    fun aPageIsWholeSystemsAndTheNextStartsWithItsLastSystem() {
        // Upright: seven systems fit; the next page starts with the seventh.
        val p = StandPages(systems(20), viewport = 720f)
        assertEquals(listOf(0 to 6, 6 to 12, 12 to 18, 18 to 19), p.pages.map { it.first to it.last })
        assertEquals(4, p.count)
        assertEquals(1..21, p.bars(0))
        assertEquals(19..39, p.bars(1))
    }

    @Test
    fun onItsSideTwoSystemsTurnOneAtATime() {
        val p = StandPages(systems(5, bars = 4), viewport = 230f)
        assertEquals(listOf(0 to 1, 1 to 2, 2 to 3, 3 to 4), p.pages.map { it.first to it.last })
    }

    @Test
    fun aSystemTallerThanTheScreenIsAPageOfItsOwn() {
        val p = StandPages(systems(3, h = 500f), viewport = 300f)
        assertEquals(listOf(0 to 0, 1 to 1, 2 to 2), p.pages.map { it.first to it.last })
        assertTrue(StandPages(emptyList(), 300f).pages.isEmpty())
    }

    @Test
    fun thePageNumberIsThePageWhoseTopSystemHoldsTheBar() {
        val p = StandPages(systems(20), viewport = 720f)
        assertEquals(0, p.pageOf(1))
        assertEquals(0, p.pageOf(18))
        // Bar 19 is in system 6: the last system of page 1 and the top of page 2.
        assertEquals(1, p.pageOf(19))
        assertEquals(3, p.pageOf(60))
        // The place is kept as a bar: the top bar of a page finds that page again.
        for (i in 0 until p.count) assertEquals(i, p.pageOf(p.topBar(i)))
    }

    @Test
    fun playbackTurnsWhenTheCursorReachesTheLastSystem() {
        val p = StandPages(systems(20), viewport = 720f)
        assertEquals(0, p.followPlayback(0, 18))
        assertEquals(1, p.followPlayback(0, 19))
        // A jump (a repeat, a bar chosen by hand) goes to the bar's page.
        assertEquals(0, p.followPlayback(2, 4))
        // The last page stays.
        assertEquals(3, p.followPlayback(3, 60))
        // By hand: the page stays while the bar is on it.
        assertEquals(1, p.pageShowing(1, 19))
        assertEquals(0, p.pageShowing(1, 3))
    }

    @Test
    fun theCurrentSystemNeverSitsUnderTheLayer() {
        val p = StandPages(systems(20), viewport = 720f)
        // No layer: the window starts at the page's top system.
        assertEquals(0f, p.windowTop(0, 16, obscured = 0f))
        // The layer covers the bottom 300 px; bar 16 is in system 5 (500 to 600), so the window moves
        // down, to a system top (200), so nothing above is cut in half.
        val top = p.windowTop(0, 16, obscured = 300f)
        assertEquals(200f, top)
        assertTrue("system bottom ${600 - top} clear of ${720 - 300}", 600 - top <= 720 - 300)
        // A bar above the layer leaves the window alone; the next page starts at its own top.
        assertEquals(0f, p.windowTop(0, 4, obscured = 300f))
        assertEquals(600f, p.windowTop(1, 19, obscured = 300f))
        // Below the page's last whole system, paper.
        assertEquals(700f, p.pageBottom(0, 0f))
    }

    @Test
    fun pagesAfterTheFirstNeverShowTheTitle() {
        // The first system starts below a title block; later pages start at their top system.
        val sys = listOf(StandSystem(300f, 400f, 1, 3)) + (1 until 10).map { i -> StandSystem(300f + i * 100, 400f + i * 100, i * 3 + 1, i * 3 + 3) }
        val p = StandPages(sys, viewport = 600f, content = 1300f)
        // Page 1 keeps the title (the window starts at 0); page 2 starts at its system.
        assertEquals(0f, p.windowTop(0, null))
        assertEquals(0f..600f, p.visible(0, 0f))
        // The last page cannot scroll past the engraving: paper covers what is above its first system.
        val last = p.count - 1
        val top = p.windowTop(last, null)
        assertTrue(p.visible(last, top).start >= p.systems[p.pages[last].first].top - top)
        assertTrue(p.visible(last, top).start > 0f)
    }

    @Test
    fun aShortScoreNeverShowsHalfTheTitle() {
        // A title block (0 to 300) and three systems; the engraving ends at 700, the window is 600 tall.
        val sys = listOf(StandSystem(300f, 400f, 1, 4), StandSystem(400f, 550f, 5, 8), StandSystem(550f, 700f, 9, 12))
        val p = StandPages(sys, viewport = 600f, content = 700f)
        // Bar 7 must sit above a 250 px layer: the window wants to start at a system top (300)...
        val wanted = p.wantedTop(0, 7, obscured = 250f)
        assertEquals(300f, wanted)
        // ...but the engraving ends first, so it starts at 100, and paper covers down to 300: no half title.
        val top = p.windowTop(0, 7, obscured = 250f)
        assertEquals(100f, top)
        assertEquals(200f, p.visible(0, top, wanted).start)
    }

    @Test
    fun keysTurnPagesAsPageTurnersSendThem() {
        val r = MusicStandRules
        for (k in listOf(KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_PAGE_DOWN)) assertEquals(StandCommand.NEXT_PAGE, r.command(k))
        for (k in listOf(KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_PAGE_UP)) assertEquals(StandCommand.PREVIOUS_PAGE, r.command(k))
        assertEquals(StandCommand.PLAY_PAUSE, r.command(KeyEvent.KEYCODE_SPACE))
        assertEquals(StandCommand.FIRST_PAGE, r.command(KeyEvent.KEYCODE_MOVE_HOME))
        assertEquals(StandCommand.LAST_PAGE, r.command(KeyEvent.KEYCODE_MOVE_END))
        assertEquals(StandCommand.NEXT_BAR, r.command(KeyEvent.KEYCODE_DPAD_DOWN, ctrl = true))
        assertEquals(StandCommand.PREVIOUS_BAR, r.command(KeyEvent.KEYCODE_DPAD_UP, ctrl = true))
        assertEquals(StandCommand.LEAVE, r.command(KeyEvent.KEYCODE_ESCAPE))
        assertEquals(StandCommand.LEAVE, r.command(KeyEvent.KEYCODE_F))
        assertEquals(StandCommand.SHOW_CONTROLS, r.command(KeyEvent.KEYCODE_TAB))
        assertNull(r.command(KeyEvent.KEYCODE_F, ctrl = true))
        assertNull(r.command(KeyEvent.KEYCODE_DPAD_RIGHT, alt = true))
        assertNull(r.command(KeyEvent.KEYCODE_A))
        // Only Tab and Space show the controls: a Bluetooth page turner sends arrows and Page Up/Down.
        assertTrue(r.showsControls(KeyEvent.KEYCODE_TAB))
        assertTrue(r.showsControls(KeyEvent.KEYCODE_SPACE))
        for (k in listOf(KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_UP,
                KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_MOVE_HOME, KeyEvent.KEYCODE_MOVE_END,
                KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_ESCAPE)) assertFalse(r.showsControls(k))
        assertTrue(r.opensStand(KeyEvent.KEYCODE_F, ctrl = false, alt = false, shift = false))
        assertFalse(r.opensStand(KeyEvent.KEYCODE_F, ctrl = true, alt = false, shift = false))
    }

    @Test
    fun whileARepeatIsSetThePedalsPlayAndGoBackToItsStart() {
        val r = MusicStandRules
        for (k in listOf(KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_PAGE_DOWN))
            assertEquals(StandCommand.PLAY_PAUSE, r.command(k, repeating = true))
        for (k in listOf(KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_PAGE_UP))
            assertEquals(StandCommand.REPEAT_START, r.command(k, repeating = true))
        // The other keys stay as they are: Home and End still turn to the first and last page, Ctrl+arrows move a bar.
        assertEquals(StandCommand.FIRST_PAGE, r.command(KeyEvent.KEYCODE_MOVE_HOME, repeating = true))
        assertEquals(StandCommand.LAST_PAGE, r.command(KeyEvent.KEYCODE_MOVE_END, repeating = true))
        assertEquals(StandCommand.NEXT_BAR, r.command(KeyEvent.KEYCODE_DPAD_DOWN, ctrl = true, repeating = true))
        assertEquals(StandCommand.PREVIOUS_BAR, r.command(KeyEvent.KEYCODE_DPAD_UP, ctrl = true, repeating = true))
        assertEquals(StandCommand.PLAY_PAUSE, r.command(KeyEvent.KEYCODE_SPACE, repeating = true))
        assertNull(r.command(KeyEvent.KEYCODE_PAGE_DOWN, ctrl = true, repeating = true))
    }

    @Test
    fun theLayerHidesByItselfOnlyWhilePlayingAndNeverWithAssistiveTech() {
        val r = MusicStandRules
        assertTrue(r.autoHides(playing = true, assistive = false, focusInLayer = false, keyboard = false, keepVisible = false))
        assertFalse(r.autoHides(playing = false, assistive = false, focusInLayer = false, keyboard = false, keepVisible = false))
        assertFalse(r.autoHides(playing = true, assistive = true, focusInLayer = false, keyboard = false, keepVisible = false))
        assertFalse(r.autoHides(playing = true, assistive = false, focusInLayer = true, keyboard = false, keepVisible = false))
        assertFalse(r.autoHides(playing = true, assistive = false, focusInLayer = false, keyboard = true, keepVisible = false))
        assertFalse(r.autoHides(playing = true, assistive = false, focusInLayer = false, keyboard = false, keepVisible = true))
    }

    @Test
    fun talkBackAndSwitchAccessCountTestServicesDoNot() {
        val r = MusicStandRules
        assertTrue(r.assistive(touchExploration = true, services = emptyList()))
        assertTrue(r.assistive(false, listOf("com.google.android.marvin.talkback/.TalkBackService" to AccessibilityServiceInfo.FEEDBACK_SPOKEN)))
        assertTrue(r.assistive(false, listOf("com.google.android.accessibility.switchaccess/.SwitchAccessService" to AccessibilityServiceInfo.FEEDBACK_GENERIC)))
        // UiAutomation (instrumented tests) and password managers are services, not assistive tech.
        assertFalse(r.assistive(false, listOf("androidx.test/.UiAutomation" to AccessibilityServiceInfo.FEEDBACK_GENERIC)))
        assertFalse(r.assistive(false, emptyList()))
    }

    @Test
    fun layoutFollowsTheSizingTable() {
        val r = MusicStandRules
        assertEquals(3, r.barsPerSystem(411, portrait = true))
        assertEquals(4, r.barsPerSystem(411, portrait = false))
        assertEquals(4, r.barsPerSystem(800, portrait = true))
        assertTrue(r.lockAvailable(411))
        assertFalse(r.lockAvailable(600))
    }

    @Test
    fun aNarrowColumnTakesFewerBarsNeverSmallerNotes() {
        val r = MusicStandRules
        // A phone upright (411 dp) keeps its 3; on its side (914 dp) and a tablet keep 4.
        assertEquals(3, r.barsFitting(3, 411f, 1f))
        assertEquals(4, r.barsFitting(4, 914f, 1f))
        // Zoomed to 220 %, a 628 dp column holds 2 bars, not 4 squeezed ones; never fewer than 1.
        assertEquals(2, r.barsFitting(4, 628f, 2.2f))
        assertEquals(1, r.barsFitting(4, 100f, 4f))
    }

    @Test
    fun swipesStartClearOfTheEdges() {
        val r = MusicStandRules
        val edge = 63f
        assertEquals(1, r.swipe(startX = 500f, dx = -200f, dy = 10f, width = 1080f, edgePx = edge, minPx = 126f))
        assertEquals(-1, r.swipe(500f, 200f, 10f, 1080f, edge, 126f))
        // From within 24 dp of an edge: the system's back gesture, never a page.
        assertEquals(0, r.swipe(20f, 300f, 0f, 1080f, edge, 126f))
        assertEquals(0, r.swipe(1070f, -300f, 0f, 1080f, edge, 126f))
        // Too short, or mostly up and down.
        assertEquals(0, r.swipe(500f, -60f, 0f, 1080f, edge, 126f))
        assertEquals(0, r.swipe(500f, -200f, 200f, 1080f, edge, 126f))
    }

    @Test
    fun yourPartIsTheLeadAndOnlyMyPartNeedsOneToName() {
        val r = MusicStandRules
        val band = listOf("Soprano Cornet", "Solo Cornet", "Repiano Cornet")
        assertEquals(1, r.yourPart(band, null))
        assertTrue(r.offersOnlyMine(band, 1))
        assertEquals(0, r.yourPart(listOf("1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"), Lineup.QUARTET))
        // A pop score has no part to name: no "(you)" and no Only my part.
        assertNull(r.yourPart(listOf("Vocals", "Guitar"), null))
        assertFalse(r.offersOnlyMine(listOf("Vocals", "Guitar"), null))
        // One part alone has nothing else to hide.
        assertFalse(r.offersOnlyMine(listOf("Solo Cornet"), 0))
        // MusicXML part names can carry no-break spaces.
        assertEquals(0, r.yourPart(listOf("Solo Cornet", "Tuba"), null))
    }
}
