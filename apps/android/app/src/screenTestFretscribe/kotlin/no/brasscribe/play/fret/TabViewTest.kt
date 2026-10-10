package no.brasscribe.play.fret

import alphaTab.model.NoteSubElement
import android.graphics.Bitmap
import android.graphics.Paint
import android.graphics.Rect
import android.net.Uri
import android.view.KeyEvent
import android.view.View
import android.widget.FrameLayout
import androidx.compose.ui.geometry.Rect as ComposeRect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.design.BrasscribeColors
import no.brasscribe.design.BrasscribeDarkColors
import no.brasscribe.design.BrasscribeHighContrastColors
import no.brasscribe.design.BrasscribeLightColors
import no.brasscribe.play.Appearance
import no.brasscribe.play.MainActivity
import no.brasscribe.play.PlayApplication
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.TabLayout
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlin.math.abs
import no.brasscribe.play.test.DeviceOnly

/**
 * The tab view, on a fixture computer: Check the song, then Show the tab. The first fixture
 * (apps/fixtures/bass-line) has nothing to check; the second (bass-line-marks) has a doubtful note, a
 * doubtful note written as tied pieces and a note below the lowest string. The marks are looked for
 * on the screen itself: the "?" and the tinted numeral in the doubt colour over the right column, the
 * boxed "!" in ink, and nothing in the doubt colour anywhere else.
 */
@RunWith(AndroidJUnit4::class)
class TabViewTest : TabScreenTest() {

    override val shots = "fretscribe/tab"

    /** The screenshot [name] of the screen at rest. */
    private fun shotOf(name: String) {
        settle()
        shot(name)
    }

    /** The whole screen at rest, to look at its pixels. */
    private fun still(): Bitmap {
        // (At rest also where alphaTab has a hand in it: its page is drawn on a thread of its own.)
        rest()
        return screen()
    }

    private fun near(pixel: Int, colour: Int, tolerance: Int = 36): Boolean =
        abs((pixel shr 16 and 0xFF) - (colour shr 16 and 0xFF)) <= tolerance && abs((pixel shr 8 and 0xFF) - (colour shr 8 and 0xFF)) <= tolerance &&
            abs((pixel and 0xFF) - (colour and 0xFF)) <= tolerance

    /** How many pixels of [area] are [colour] (as nearly as an edge allows). */
    private fun count(image: Bitmap, area: Rect, colour: Int, tolerance: Int = 36): Int {
        var n = 0
        for (y in maxOf(0, area.top) until minOf(image.height, area.bottom)) for (x in maxOf(0, area.left) until minOf(image.width, area.right)) {
            if (near(image.getPixel(x, y), colour, tolerance)) n++
        }
        return n
    }

    private fun bounds(tag: String): Rect = rule.onNodeWithTag(tag).fetchSemanticsNode().boundsInWindow.toRect()
    private fun ComposeRect.toRect() = Rect(left.toInt(), top.toInt(), right.toInt(), bottom.toInt())

    /** The upper part of a mark's element, where its glyph is: 1.4 line spaces and a little air. */
    private fun glyphArea(tab: TabView, mark: Rect, box: MarkBox): Rect {
        val top = mark.top + ((mark.height() - (box.columnBottom - box.top)) / 2).toInt().coerceAtLeast(0)
        return Rect(mark.left, top - 2, mark.right, top + (box.bottom - box.top).toInt() + (0.3f * tab.lineSpace).toInt())
    }

    private val marks get() = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.TestTag) and hasClickAction())
        .fetchSemanticsNodes().mapNotNull { it.config.getOrNull(SemanticsProperties.TestTag)?.takeIf { t -> t.startsWith("fs-tab-mark-") } }

    /** What the marks of the second fixture say, in the order they are read. */
    private val expected = listOf(
        "Bar 3, beat 2. 3rd string, fret 2, B. Fretscribe isn't sure about this one.",
        "Bar 7, beat 2. D1 is lower than your lowest string. Is the tuning right?",
        "Bar 15, beat 1. 4th string, open, E. Fretscribe isn't sure about this one.",
    )

    /**
     * The tab view was given [colours], and alphaTab is told to engrave every doubtful numeral (or note head) in their
     * doubt colour and every other note in ink. (That it then draws them so is theDoubtfulNumeralsAreDrawnInTheDoubtColour's,
     * on a device: alphaSkia's desktop build swaps red and blue.)
     */
    private fun assertTheDoubtColourIsGiven(tab: TabView, colours: BrasscribeColors) {
        rule.runOnUiThread {
            assertEquals(tabPalette(colours), tab.palette)
            val uncertain = colours.uncertain.toArgb()
            val doubtful = tab.placed.flatMap { it.doubtful }
            assertTrue("doubtful notes", doubtful.isNotEmpty())
            for (note in doubtful) {
                val c = note.style?.colors?.get(NoteSubElement.GuitarTabFretNumber) ?: throw AssertionError("a doubtful numeral with no colour of its own")
                assertEquals("the doubtful numeral's colour", listOf(uncertain shr 16 and 0xFF, uncertain shr 8 and 0xFF, uncertain and 0xFF), listOf(c.r.toInt(), c.g.toInt(), c.b.toInt()))
            }
            val score = tab.view.api.score!!
            for (track in score.tracks) for (staff in track.staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) for (n in beat.notes) {
                if (doubtful.none { it === n }) assertNull("a sure note is in ink", n.style)
            }
        }
    }

    /** The marks of the second fixture are over their columns, in [colours]; nothing else on the screen is in the doubt colour. */
    private fun assertTheMarksAreDrawn(tab: TabView, colours: BrasscribeColors, numeralsToo: Boolean = false) {
        assertTheDoubtColourIsGiven(tab, colours)
        val uncertain = colours.uncertain.toArgb()
        val ink = colours.ink.toArgb()
        val boxes = tab.engraving.value!!.boxes
        assertEquals(3, boxes.size)
        for ((i, box) in boxes.withIndex()) {
            rule.onNodeWithTag("fs-tab-mark-$i").performScrollTo()
            // Under the status bar a mark would be read from the wrong pixels: bring it well into view.
            val image = still()
            val mark = bounds("fs-tab-mark-$i")
            val glyph = glyphArea(tab, mark, box)
            val numerals = Rect(mark.left, glyph.bottom, mark.right, mark.bottom)
            if (i == 1) {
                assertTrue("the boxed ! is in ink", count(image, glyph, ink) > 40)
                assertEquals("the boxed ! is not in the doubt colour", 0, count(image, glyph, uncertain))
            } else {
                assertTrue("a ? in the doubt colour above column $i", count(image, glyph, uncertain) > 40)
                if (numeralsToo) assertTrue("the numeral of column $i in the doubt colour", count(image, numerals, uncertain) > 20)
                tabPalette(colours).uncertainTint?.let { wash -> assertTrue("the wash behind the numeral of column $i", count(image, numerals, wash, 6) > 40) }
            }
            // Nothing in the doubt colour outside the marks on this screen: no second "?" from the page's own words.
            val others = marks.map { bounds(it) }
            var stray = 0
            for (y in 0 until image.height step 2) for (x in 0 until image.width step 2) {
                if (near(image.getPixel(x, y), uncertain) && others.none { it.contains(x, y) }) stray++
            }
            assertEquals("pixels in the doubt colour outside the marks", 0, stray)
        }
    }

    @Test
    @DeviceOnly
    fun theDoubtfulNumeralsAreDrawnInTheDoubtColour() {
        assumeTrue("on a device only: alphaSkia's desktop build swaps red and blue", ScreenDevice.ENGRAVES_IN_COLOUR)
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        assertTheMarksAreDrawn(showTheTab(), BrasscribeLightColors, numeralsToo = true)
    }

    /**
     * A phone on its side with the navigation bar at the side (three buttons): the note under the tab keeps clear of the
     * bar once, not twice. It is as wide as the screen beside the bar, where its words have the least room.
     */
    @Test
    fun withTheNavigationBarAtTheSideTheNoteUnderTheTabKeepsItsWidth() {
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        showTheTab()
        ScreenDevice.turn(rule, sideways = true)
        settle()
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo().performClick()
        waitForTag("fs-tab-note", 5_000)
        val density = rule.activity.resources.displayMetrics.density
        val bar = (48 * density).toInt()
        var width = 0
        rule.runOnUiThread {
            val decor = rule.activity.window.decorView
            width = decor.width
            val now = androidx.core.view.ViewCompat.getRootWindowInsets(decor)!!
            val side = androidx.core.view.WindowInsetsCompat.Builder(now)
                .setInsets(androidx.core.view.WindowInsetsCompat.Type.navigationBars(), androidx.core.graphics.Insets.of(0, 0, bar, 0))
                .build()
            decor.dispatchApplyWindowInsets(side.toWindowInsets())
        }
        settle()
        val close = rule.onNodeWithTag("fs-tab-note-close").fetchSemanticsNode().boundsInWindow
        val note = rule.onNodeWithTag("fs-tab-note").fetchSemanticsNode().boundsInWindow
        assertTrue("Close is not clear of the bar at the side: it ends at ${close.right} of $width, the bar is $bar wide", close.right <= width - bar + 0.5f)
        assertTrue("the note keeps clear of the bar twice: Close ends at ${close.right} of $width, the bar is $bar wide",
            close.right >= width - bar - 8 * density)
        assertTrue("the note starts ${note.left} px in", note.left <= 24 * density)
    }

    @Test
    fun theTabIsShownWithItsMarksOnTheRightNotes() {
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = showTheTab()
        assertEquals(Screen.SCORE, vm.screen.value.last())
        assertTrue("fret numbers in Fretscribe Tab", tab.tabFont)
        assertEquals("every marked note has its column", 0, tab.unmatched)

        // The header: the tuning chip reads its whole state, and the lines under it say what there is to check.
        rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Tuning: Standard, no capo").assertHeightIsAtLeast(48.dp).assert(hasClickAction())
        rule.onNodeWithTag("fs-tab-marked").assertTextEquals("2 notes marked ? · Check them").assertHeightIsAtLeast(48.dp).assert(hasClickAction())
        rule.onNodeWithTag("fs-tab-no-place").assertTextEquals("1 note with no place")
        rule.onNodeWithTag("fs-tab").assertContentDescriptionEquals("Bass line. Tab. Tuning: Standard, no capo. 100 beats a minute. 16 bars. 2 notes marked ?. 1 note with no place.")
        // Nothing of the band's score screen.
        listOf("score-view", "print", "share").forEach { assertTrue(it, rule.onAllNodesWithTag(it).fetchSemanticsNodes().isEmpty()) }

        // The marks, in reading order, each an element of 48 dp that says which note it is.
        assertEquals(listOf("fs-tab-mark-0", "fs-tab-mark-1", "fs-tab-mark-2"), marks)
        expected.forEachIndexed { i, words ->
            rule.onNodeWithTag("fs-tab-mark-$i").performScrollTo().assertContentDescriptionEquals(words).assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
        }
        // Each is over the note the data names: the doubtful 2 on the 3rd string, the rest that stands for the low D, the open 4th string.
        rule.runOnUiThread {
            val placed = tab.placed
            assertEquals(listOf(MarkKind.DOUBT, MarkKind.NO_PLACE, MarkKind.DOUBT), placed.map { it.kind })
            assertEquals(listOf(2, 14), listOf(placed[0], placed[2]).map { it.beat.voice.bar.index.toInt() })
            // alphaTab counts strings from the lowest: its 2nd is the page's 3rd on a four-string bass.
            assertEquals(listOf(2 to 2, 0 to 1), listOf(placed[0], placed[2]).map { it.doubtful.single().let { n -> n.fret.toInt() to n.string.toInt() } })
            assertTrue("the ! stands over a rest", placed[1].beat.isRest && placed[1].beat.voice.bar.index.toInt() == 6)
            // The tied note has its mark once, on the piece where it starts.
            assertEquals(1, placed.count { it.beat.voice.bar.index.toInt() >= 14 })
            val lookup = tab.view.api.boundsLookup!!
            val density = rule.activity.resources.displayMetrics.density
            for ((mark, box) in placed.zip(tab.engraving.value!!.boxes)) {
                val beat = lookup.findBeats(mark.beat)!![0]
                val head = beat.notes?.takeIf { it.length.toInt() > 0 }?.get(0)?.noteHeadBounds
                val staff = beat.barBounds.visualBounds
                if (head != null) assertEquals("the mark is centred on its numeral", (head.x + head.w / 2) * density, box.centre.toDouble(), 1.0)
                assertTrue("the mark is above the staff", box.bottom <= staff.y * density)
            }
        }
        assertTheMarksAreDrawn(tab, BrasscribeLightColors)
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-marks-light")
        rule.onNodeWithTag("fs-tab-mark-2").performScrollTo()
        shotOf("tab-marks-light-end")

        // A tap says which note it is, on the screen and to a screen reader; nothing is changed (Fix a note is not here yet).
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo().performClick()
        rule.onNodeWithTag("fs-tab-note").assertTextEquals(expected[0])
        assertEquals(androidx.compose.ui.semantics.LiveRegionMode.Polite, rule.onNodeWithTag("fs-tab-note").fetchSemanticsNode().config[SemanticsProperties.LiveRegion])
        shotOf("tab-mark-told-light")
        rule.onNodeWithTag("fs-tab-mark-1").performScrollTo().performClick()
        rule.onNodeWithTag("fs-tab-note").assertTextEquals(expected[1])
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-note-close").assertHeightIsAtLeast(48.dp).performClick()
        assertTrue(rule.onAllNodesWithTag("fs-tab-note").fetchSemanticsNodes().isEmpty())

        // Dark: the same marks in the dark theme's colours.
        val light = tab.engravings
        rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
        waitUntil(20_000) { TabScreenProbe.view?.let { it !== tab || it.engravings > light } == true }
        assertTheMarksAreDrawn(engraved(), BrasscribeDarkColors)
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-marks-dark")

        // The chip opens Check the song, and Show the tab comes back.
        rule.onNodeWithTag("fs-tab-tuning").performClick()
        waitForTag("fs-show-tab")
        assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT), vm.screen.value)
        rule.onNodeWithTag("fs-show-tab").performClick()
        engraved()
        // The line goes to the first "?" on the page, with its note open, and stays on the tab.
        rule.onNodeWithTag("fs-tab-marked").performClick()
        waitForTag("fs-tab-note", 5_000)
        rule.onNodeWithTag("fs-tab-note").assertTextEquals(expected[0])
        assertEquals(Screen.SCORE, vm.screen.value.last())
    }

    @Test
    fun withNotationAboveTheMarksAreOnTheTabStaff() {
        computer("bass-line-marks", page = "tab-and-notation") { it.put("layout", "tab-and-notation") }
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = showTheTab()
        assertEquals(0, tab.unmatched)
        rule.onNodeWithTag("fs-tab").assertContentDescriptionEquals("Bass line. Tab and notation. Tuning: Standard, no capo. 100 beats a minute. 16 bars. 2 notes marked ?. 1 note with no place.")
        assertEquals(listOf("fs-tab-mark-0", "fs-tab-mark-1", "fs-tab-mark-2"), marks)
        rule.onNodeWithTag("fs-tab-mark-0").assertContentDescriptionEquals(expected[0])
        // The notation staff writes the low D, so the mark spells it from there.
        rule.onNodeWithTag("fs-tab-mark-1").assertContentDescriptionEquals("Bar 7, beat 2. D is lower than your lowest string. Is the tuning right?")
        rule.onNodeWithTag("fs-tab-mark-2").assertContentDescriptionEquals(expected[2])
        rule.runOnUiThread {
            val staves = tab.view.api.score!!.tracks[0].staves
            assertEquals(2, staves.length.toInt())
            // The tab staff's music is in the bar's first voice, so no rest is drawn over the numbers.
            for (bar in staves[1].bars) assertFalse("bar ${bar.index}", bar.voices[0].isEmpty)
            assertEquals(listOf(false, true), listOf(staves[0].showTablature, staves[1].showTablature))
            assertEquals(listOf(true, false), listOf(staves[0].showStandardNotation, staves[1].showStandardNotation))
            // Every mark stands on the tab staff, the second of the pair; the doubtful ones over a numeral.
            assertEquals(listOf(1, 1, 1), tab.placed.map { it.beat.voice.bar.staff.index.toInt() })
            assertEquals(listOf(2 to 2, 0 to 1), listOf(tab.placed[0], tab.placed[2]).map { it.doubtful.single().let { n -> n.fret.toInt() to n.string.toInt() } })
            assertEquals(alphaTab.TabRhythmMode.Hidden, tab.view.settings.notation.rhythmMode)
        }
        assertTheMarksAreDrawn(tab, BrasscribeLightColors)
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-and-notation-light")
    }

    @Test
    fun inTheNotationLayoutTheMarksAreOnTheNotes() {
        computer("bass-line-marks", page = "notation") { it.put("layout", "notation") }
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = showTheTab()
        assertEquals(0, tab.unmatched)
        rule.onNodeWithTag("fs-tab").assertContentDescriptionEquals("Bass line. Notation. Tuning: Standard, no capo. 100 beats a minute. 16 bars. 2 notes marked ?. 1 note with no place.")
        assertEquals(listOf("fs-tab-mark-0", "fs-tab-mark-1", "fs-tab-mark-2"), marks)
        // No string or fret is written on this page: the mark names the note.
        rule.onNodeWithTag("fs-tab-mark-0").assertContentDescriptionEquals("Bar 3, beat 2. B. Fretscribe isn't sure about this one.")
        rule.onNodeWithTag("fs-tab-mark-1").assertContentDescriptionEquals("Bar 7, beat 2. D is lower than your lowest string. Is the tuning right?")
        rule.runOnUiThread {
            val staves = tab.view.api.score!!.tracks[0].staves
            assertEquals(1, staves.length.toInt())
            assertTrue(staves[0].showStandardNotation && !staves[0].showTablature)
            assertEquals(listOf(MarkKind.DOUBT, MarkKind.NO_PLACE, MarkKind.DOUBT), tab.placed.map { it.kind })
            assertEquals(listOf(1, 0, 1), tab.placed.map { it.doubtful.size })
        }
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("notation-light")
    }

    @Test
    fun inHighContrastTheMarksAreShapesWithoutAWash() {
        assumeTrue("this device does not take the contrast setting", ScreenDevice.highContrast(rule, true))
        computer("bass-line-marks")
        val tab = showTheTab()
        rule.runOnUiThread { assertEquals(null, tab.palette.uncertainTint) }
        assertTheMarksAreDrawn(tab, BrasscribeHighContrastColors)
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-marks-high-contrast")
    }

    @Test
    fun theMarksComeFromTheDataNotFromThePagesWords() {
        // The first fixture's page has no "?"; its data is given a doubtful note, and the tab marks it.
        computer("bass-line") { tab -> tab.getJSONArray("notes").getJSONObject(2).put("confidence", 0.2) }
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        var tab = showTheTab()
        assertEquals(listOf("fs-tab-mark-0"), marks)
        rule.onNodeWithTag("fs-tab-mark-0").assertContentDescriptionEquals("Bar 2, beat 1. 4th string, fret 3, G. Fretscribe isn't sure about this one.")
        rule.onNodeWithTag("fs-tab-marked").assertTextEquals("1 note marked ? · Check it")
        assertTrue(rule.onAllNodesWithTag("fs-tab-no-place").fetchSemanticsNodes().isEmpty())
        val image = still()
        assertTrue("the ? is drawn", count(image, bounds("fs-tab-mark-0"), BrasscribeLightColors.uncertain.toArgb()) > 60)
        assertEquals(0, tab.unmatched)

        // The second fixture's page has two "?" and a "!"; its data says every note is sure and has a place only for the "!":
        // the page's own "?" words are not drawn, and its doubt colour is gone.
        computer("bass-line-marks") { t ->
            val notes = t.getJSONArray("notes")
            for (i in 0 until notes.length()) notes.getJSONObject(i).put("confidence", 0.9)
        }
        tab = showTheTab()
        assertEquals(listOf("fs-tab-mark-0"), marks)
        rule.onNodeWithTag("fs-tab-mark-0").assertContentDescriptionEquals("Bar 7, beat 2. D1 is lower than your lowest string. Is the tuning right?")
        assertTrue(rule.onAllNodesWithTag("fs-tab-marked").fetchSemanticsNodes().isEmpty())
        rule.onNodeWithTag("fs-tab-no-place").assertTextEquals("1 note with no place")
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        val uncertain = BrasscribeLightColors.uncertain.toArgb()
        run {
            val seen = still()
            assertEquals("nothing in the doubt colour", 0, count(seen, Rect(0, 0, seen.width, seen.height), uncertain))
        }
    }

    @Test
    fun withoutTheComputerTheMarksAreThePagesOwn() {
        // The computer answers for Check the song, and no longer has the tab's notes when the tab is shown.
        computer("bass-line-marks", withTab = false)
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = showTheTab()
        assertEquals(0, tab.unmatched)
        assertEquals(listOf("fs-tab-mark-0", "fs-tab-mark-1", "fs-tab-mark-2"), marks)
        rule.onNodeWithTag("fs-tab-mark-0").assertContentDescriptionEquals(expected[0])
        // The page names the note and not why it has no place.
        rule.onNodeWithTag("fs-tab-mark-1").assertContentDescriptionEquals("Bar 7, beat 2. D1 has no place on your instrument here. Is the tuning right?")
        rule.onNodeWithTag("fs-tab-mark-2").assertContentDescriptionEquals(expected[2])
        rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Tuning: Standard, no capo")
        rule.onNodeWithTag("fs-tab-marked").assertTextEquals("2 notes marked ? · Check them")
        assertTheMarksAreDrawn(tab, BrasscribeLightColors)
    }

    @Test
    fun largerMeansMoreLinesOfFewerBarsAndNoSidewaysScrolling() {
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        textSize(2.0f)
        var tab = showTheTab()
        fun width() = tab.view.findViewById<View>(net.alphatab.R.id.renderSurface).width to tab.view.width
        val lines200 = tab.engraving.value!!.barsPerLine
        assertEquals(16, lines200.sum())
        width().let { (surface, view) -> assertTrue("the page is as wide as the screen at 200 % text ($surface of $view)", surface <= view) }
        assertNoTextIsClipped()
        assertEquals(0, tab.unmatched)
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo().assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-200-text")
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-200-text-mark")

        // The page is as large as a bar can be across this screen: there is no larger to ask for.
        rule.onNodeWithTag("fs-tab-zoom-in").assertIsNotEnabled()
        assertTheMarksAreDrawn(tab, BrasscribeLightColors)

        // At the ordinary text size the same song takes fewer lines; zoomed in more again, never wider than the screen.
        textSize(1.0f)
        tab = engraved()
        waitUntil(20_000) { TabScreenProbe.view?.engraving?.value?.barsPerLine?.let { it.size < lines200.size } == true }
        tab = engraved()
        settle()
        val lines100 = tab.engraving.value!!.barsPerLine
        repeat(6) { rule.onNodeWithTag("fs-tab-zoom-in").performClick() }
        waitUntil(20_000) { TabScreenProbe.view?.engraving?.value?.barsPerLine?.let { it.size > lines100.size } == true }
        tab = engraved()
        settle()
        val lines160 = tab.engraving.value!!.barsPerLine
        assertEquals(16, lines160.sum())
        width().let { (surface, view) -> assertTrue("the page is as wide as the screen at 160 % ($surface of $view)", surface <= view) }
        rule.onNodeWithTag("fs-tab-zoom-in").assert(SemanticsMatcher("says the size") { it.config.getOrNull(SemanticsProperties.ContentDescription).orEmpty().any { d -> d.contains("160%") } })
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        assertTheMarksAreDrawn(tab, BrasscribeLightColors)
        rule.onNodeWithTag("fs-tab-mark-0").performScrollTo()
        shotOf("tab-160-zoom")

        // Zoomed out, more bars to a line.
        repeat(11) { rule.onNodeWithTag("fs-tab-zoom-out").performClick() }
        waitUntil(20_000) { TabScreenProbe.view?.engraving?.value?.barsPerLine?.let { it.size < lines100.size } == true }
        tab = engraved()
        settle()
        val lines50 = tab.engraving.value!!.barsPerLine
        android.util.Log.i("TabViewTest", "bars per line: $lines200 at 200 % text, $lines100 at 100 %, $lines160 at 160 %, $lines50 at 50 %")
        assertEquals(16, lines50.sum())
        assertTrue("more bars to a line when smaller: $lines50", lines50.max() > lines100.max())
        // The marks are small at 50 %; their elements are not.
        for (i in 0..2) rule.onNodeWithTag("fs-tab-mark-$i").performScrollTo().assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
        assertTheMarksAreDrawn(tab, BrasscribeLightColors)
        checkAccessibility()
        rule.onNodeWithTag("fs-tab-zoom-out").assertIsNotEnabled()
        shotOf("tab-50-zoom")
    }

    @Test
    fun theKeyboardReachesTheChipTheLineTheZoomAndTheMarks() {
        computer("bass-line-marks")
        showTheTab()
        val reached = LinkedHashSet<String>()
        repeat(24) { key(KeyEvent.KEYCODE_TAB); reached += focusedWords() }
        listOf("Zoom out", "Zoom in", "Tuning: Standard, no capo", "2 notes marked ? · Check them", expected[0], expected[1], expected[2]).forEach { w ->
            assertTrue("\"$w\" in $reached", reached.any { it.contains(w) })
        }
        // In reading order.
        val order = reached.toList()
        assertTrue(order.toString(), order.indexOfFirst { it.contains(expected[0]) } < order.indexOfFirst { it.contains(expected[1]) } &&
            order.indexOfFirst { it.contains(expected[1]) } < order.indexOfFirst { it.contains(expected[2]) })
        // Enter on a mark says its note.
        repeat(24) { if (!focusedWords().contains(expected[1])) key(KeyEvent.KEYCODE_TAB) }
        assertTrue(focusedWords(), focusedWords().contains(expected[1]))
        shotOf("tab-keyboard-focus")
        key(KeyEvent.KEYCODE_ENTER)
        rule.onNodeWithTag("fs-tab-note").assertTextEquals(expected[1])
    }

    @Test
    fun inBokmalTheTabSaysItsOwnWords() {
        language("nb-NO")
        computer("bass-line-marks")
        showTheTab()
        rule.onNodeWithTag("fs-tab-tuning").assertContentDescriptionEquals("Stemming: Standard, uten capo")
        rule.onNodeWithTag("fs-tab-marked").assertTextEquals("2 toner merket ? · Sjekk dem")
        rule.onNodeWithTag("fs-tab-no-place").assertTextEquals("1 tone uten plass")
        rule.onNodeWithTag("fs-tab").assertContentDescriptionEquals("Bass line. Tab. Stemming: Standard, uten capo. 100 slag i minuttet. 16 takter. 2 toner merket ?. 1 tone uten plass.")
        rule.onNodeWithTag("fs-tab-mark-0").assertContentDescriptionEquals("Takt 3, slag 2. 3. streng, bånd 2, H. Fretscribe er ikke sikker på denne.")
        rule.onNodeWithTag("fs-tab-mark-1").assertContentDescriptionEquals("Takt 7, slag 2. D1 er lavere enn den laveste strengen din. Er stemmingen riktig?")
        checkAccessibility()
        shotOf("tab-marks-nb")
    }

    /** A page in a tab view of its own, in place of the app's screens: for what is asked of the view and not of the screen. */
    private fun alone(xml: String, layout: TabLayout, index: TabIndex, marks: TabMarks, ownFace: Boolean = true): TabView {
        lateinit var tab: TabView
        rule.runOnUiThread {
            tab = TabView(rule.activity, TabView.BASE_SCALE, tabPalette(BrasscribeLightColors), ownFace)
            // (With an empty composition beside it, so the test rule still has one to wait for.)
            rule.activity.setContentView(FrameLayout(rule.activity).apply {
                setBackgroundColor(BrasscribeLightColors.bg.toArgb())
                addView(androidx.compose.ui.platform.ComposeView(rule.activity).apply { setContent { } }, 1, 1)
                addView(tab.view)
            })
            tab.show(xml, layout, index, marks)
        }
        waitUntil(30_000) { tab.engraving.value != null }
        settle()
        return tab
    }

    private fun asset(path: String): String = checkNotNull(ScreenDevice.fixture(path)) { path }.decodeToString()

    @Test
    fun onTheProbesEveryMarkHasItsColumnInEveryLayout() {
        // What each probe has, as the data says it: columns with a mark, notes drawn "?", notes under a "!".
        val probes = linkedMapOf(
            "chords" to Triple(2, 3, 0), "tie-over-the-bar" to Triple(1, 1, 0), "moved-to-the-grid" to Triple(3, 3, 0), "pickup" to Triple(3, 3, 0),
            "triplets" to Triple(2, 2, 0), "no-place-in-a-chord" to Triple(3, 1, 2), "capo" to Triple(2, 2, 0), "six-eight" to Triple(2, 2, 0),
        )
        val layouts = listOf("tab" to TabLayout.TAB, "tab-and-notation" to TabLayout.TAB_AND_NOTATION, "notation" to TabLayout.NOTATION)
        val said = ArrayList<String>()
        for ((name, want) in probes) for ((file, layout) in layouts) {
            val xml = asset("tab-probes/$name/$file.musicxml")
            val data = no.brasscribe.play.model.BrasscribeJson.decodeFromString(no.brasscribe.play.engine.Tab.serializer(), asset("tab-probes/$name/tab.json")).copy(layout = layout)
            val index = TabIndex.parse(xml)
            for ((source, tab) in listOf("the data" to data, "the page alone" to null)) {
                val marks = TabMarks.of(index, tab)
                val view = alone(xml, layout, index, marks)
                val what = "$name, $file, marks from $source"
                var drawn = 0
                rule.runOnUiThread { drawn = view.placed.sumOf { it.doubtful.size } }
                said += "$what: ${marks.columns.size} columns, ${marks.doubtful} ?, ${marks.noPlace} !, ${marks.unplaced} without a column, ${view.unmatched} without a beat, $drawn tinted"
                assertEquals("$what: columns, notes marked ?, notes with no place", want, Triple(marks.columns.size, marks.doubtful, marks.noPlace))
                assertEquals("$what: marked notes the page has no column for", 0, marks.unplaced)
                assertEquals("$what: marked notes alphaTab has no beat for", 0, view.unmatched)
                assertEquals("$what: every column has its mark", marks.columns.size, view.engraving.value!!.boxes.size)
                assertEquals("$what: every note marked ? is tinted", marks.doubtful, drawn)
                rule.runOnUiThread {
                    // No mark stands on a bar number: each is above its staff by the height of one.
                    val lookup = view.view.api.boundsLookup!!
                    val density = rule.activity.resources.displayMetrics.density
                    val number = view.view.settings.display.resources.barNumberFont.size * view.scale * density
                    for ((mark, box) in view.placed.zip(view.engraving.value!!.boxes)) {
                        val staff = lookup.findBeats(mark.beat)!![0].barBounds.visualBounds
                        assertTrue("$what: mark ${box.column} is above the bar numbers", box.bottom <= staff.y * density - number)
                        assertTrue("$what: mark ${box.column} is on the page", box.top >= 0)
                    }
                }
                if (source == "the data" && (name == "pickup" || name == "chords" || name == "no-place-in-a-chord" || name == "triplets")) shotOf("probe-$name-$file")
                rule.runOnUiThread { view.release() }
            }
        }
        said.forEach { android.util.Log.i("TabViewTest", "probe $it") }
        // What the marks say where the bar and the beat are not the plain ones.
        fun words(name: String) = TabMarks.of(TabIndex.parse(asset("tab-probes/$name/tab.musicxml")), null).columns.map { TabWords.describe(rule.activity.resources, it, false) }
        assertEquals("The pickup bar, beat 4. 3rd string, fret 2, B. Fretscribe isn't sure about this one.", words("pickup").first())
        assertEquals("Bar 1, beat 1. 4th string, open, E. Fretscribe isn't sure about this one.", words("pickup")[1])
        assertEquals("Bar 1, beat 4. 3rd string, fret 2, B. Fretscribe isn't sure about this one.", words("six-eight").first())
        assertTrue(words("capo").first(), words("capo").first().startsWith("Bar 1, beat 2. "))
    }

    @Test
    fun aLongSongScrollsToItsEndWithTheMarksInPlace() {
        // 224 bars, with the marks of the page itself (the computer's notes are for the 16 bars).
        longSong()
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = showTheTab()
        val e = tab.engraving.value!!
        assertEquals(224, e.barsPerLine.sum())
        assertEquals(42, e.boxes.size)
        assertEquals(0, tab.unmatched)
        rule.onNodeWithTag("fs-tab-marked").assertTextEquals("28 notes marked ? · Check them")
        toTheEnd()
        var page = 0; var range = 0
        rule.runOnUiThread { page = tab.pageScrolled; range = tab.pageScrollRange }
        assertEquals(range, page)
        assertTheElementsAreOnTheMarks(tab, "a long song, at the end")
        // The last line is drawn, with its mark: the page is not blank at the end.
        val last = e.boxes.last()
        val image = still()
        val el = element("fs-tab-mark-${last.column}")
        assertTrue("the last ? of a long song is drawn", count(image, Rect(el.left.toInt(), el.top.toInt(), el.right.toInt(), el.bottom.toInt()), BrasscribeLightColors.uncertain.toArgb()) > 40)
        shotOf("tab-long-song-end")
    }

    /** The ink of the first numeral 0 of [tab]'s first bar, as a box in pixels, with the size its font was set at. */
    private fun firstZero(tab: TabView): Pair<Rect, Float> {
        waitUntil(30_000) { tab.engraving.value != null }
        settle()
        var out: Pair<Rect, Float>? = null
        val image = still()
        val ink = Rect(Int.MAX_VALUE, Int.MAX_VALUE, Int.MIN_VALUE, Int.MIN_VALUE)
        rule.runOnUiThread {
            val density = rule.activity.resources.displayMetrics.density
            val score = tab.view.api.score!!
            val beat = score.tracks[0].staves[0].bars[0].voices[0].beats[0]
            assertEquals("the first note of the fixture is an open string", 0, beat.notes[0].fret.toInt())
            val head = tab.view.api.boundsLookup!!.findBeats(beat)!![0].notes!![0].noteHeadBounds
            val at = IntArray(2).also(tab.view::getLocationOnScreen)
            // The numeral with a little air around it, clear of its neighbours and of the stem under it.
            val pad = (0.2f * tab.lineSpace).toInt()
            val area = Rect(at[0] + (head.x * density).toInt() - pad, at[1] + (head.y * density).toInt() - pad,
                at[0] + ((head.x + head.w) * density).toInt() + pad, at[1] + ((head.y + head.h) * density).toInt() + pad)
            val numeral = BrasscribeLightColors.ink.toArgb()
            for (y in area.top until area.bottom) {
                val row = (area.left until area.right).filter { x -> near(image.getPixel(x, y), numeral, 70) }
                // A row of the numeral has more ink than the stem under it or the string line through it is wide.
                if (row.size < 9 || row.last() - row.first() < 12) continue
                ink.left = minOf(ink.left, row.first()); ink.right = maxOf(ink.right, row.last()); ink.top = minOf(ink.top, y); ink.bottom = maxOf(ink.bottom, y)
            }
            val font = tab.view.settings.display.resources.tablatureFont
            out = ink to (font.size * tab.scale * density).toFloat()
        }
        return out!!
    }

    @Test
    fun theFretNumbersAreSetInFretscribeTab() = fretNumbers(systemsToo = false)

    @Test
    @DeviceOnly
    fun withoutItsFaceTheFretNumbersAreInTheSystemsMonospace() {
        // On the JVM alphaSkia takes "monospace" from the computer's fonts, not from the phone's: only a device has Android's to compare with.
        assumeTrue("on a device only: the system's monospace face", !ScreenDevice.JVM)
        fretNumbers(systemsToo = true)
    }

    /** A 0 drawn with Fretscribe Tab has its measures; with [systemsToo], one drawn without it has the system monospace's. */
    private fun fretNumbers(systemsToo: Boolean) {
        val xml = asset("bass-line/tab.musicxml")
        val index = TabIndex.parse(xml)
        fun shown(ownFace: Boolean): TabView = alone(xml, TabLayout.TAB, index, TabMarks.of(index, null), ownFace)
        val own = shown(ownFace = true)
        assertTrue(own.tabFont)
        val (ownInk, size) = firstZero(own)
        shotOf("tab-font")
        val system = shown(ownFace = false)
        assertFalse(system.tabFont)
        val (systemInk, systemSize) = firstZero(system)
        assertEquals(size, systemSize, 0.01f)

        // What a 0 measures in each face at that size, as Android draws it from the same font file.
        fun measured(face: android.graphics.Typeface): Rect = Rect().also { r ->
            Paint(Paint.ANTI_ALIAS_FLAG).apply { typeface = face; textSize = size }.getTextBounds("0", 0, 1, r)
        }
        val want = measured(android.graphics.Typeface.createFromAsset(rule.activity.assets, TabFont.ASSET))
        val other = measured(android.graphics.Typeface.create(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD))
        val message = "0 at $size px: Fretscribe Tab is ${want.width()} x ${want.height()}, the system's monospace ${other.width()} x ${other.height()}; " +
            "drawn ${ownInk.width() + 1} x ${ownInk.height() + 1} with the face and ${systemInk.width() + 1} x ${systemInk.height() + 1} without"
        android.util.Log.i("TabViewTest", message)
        // The two faces differ enough at this size for the comparison to mean something.
        fun apart(a: Rect, w: Int, h: Int) = abs(a.width() - w) + abs(a.height() - h)
        assertTrue(message, apart(want, other.width(), other.height()) >= 6)
        // Drawn with the face, the 0 has Fretscribe Tab's measures; without it, the system's.
        assertEquals(message, want.width().toFloat(), (ownInk.width() + 1).toFloat(), 3f)
        assertEquals(message, want.height().toFloat(), (ownInk.height() + 1).toFloat(), 3f)
        assertTrue(message, apart(want, ownInk.width() + 1, ownInk.height() + 1) < apart(other, ownInk.width() + 1, ownInk.height() + 1))
        if (!systemsToo) return
        assertEquals(message, other.width().toFloat(), (systemInk.width() + 1).toFloat(), 3f)
        assertEquals(message, other.height().toFloat(), (systemInk.height() + 1).toFloat(), 3f)
        assertTrue(message, apart(other, systemInk.width() + 1, systemInk.height() + 1) < apart(want, systemInk.width() + 1, systemInk.height() + 1))
    }

    /** The screen's scroll: how far it is and how far it goes. */
    private fun scrolled(): Pair<Float, Float> = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange]
        .let { it.value() to it.maxValue() }

    private fun scrollBy(pixels: Float) {
        rule.onNodeWithTag("fs-tab-scroll").performSemanticsAction(SemanticsActions.ScrollBy) { it(0f, pixels) }
        settle()
    }

    private fun toTheEnd() = scrollBy(scrolled().let { (at, max) -> max - at })

    /** Where the mark of [box] is drawn on the screen: from alphaTab's own layout, its view's place and how far it has scrolled its page. */
    private fun drawn(tab: TabView, box: MarkBox): android.graphics.RectF {
        var out = android.graphics.RectF()
        rule.runOnUiThread {
            val at = IntArray(2).also(tab.view::getLocationOnScreen)
            val half = (box.bottom - box.top) * 0.3f
            out = android.graphics.RectF(at[0] + box.centre - half, at[1] + box.top - tab.pageScrolled, at[0] + box.centre + half, at[1] + box.bottom - tab.pageScrolled)
        }
        return out
    }

    /** The whole element of a mark on the screen, also the part of it that is scrolled out of view. */
    private fun element(tag: String): android.graphics.RectF = rule.onNodeWithTag(tag).fetchSemanticsNode().let { n ->
        android.graphics.RectF(n.positionInWindow.x, n.positionInWindow.y, n.positionInWindow.x + n.size.width, n.positionInWindow.y + n.size.height)
    }

    /** The first and the last mark's elements are over the marks as alphaTab's layout draws them, within [slack] pixels. */
    private fun assertTheElementsAreOnTheMarks(tab: TabView, where: String, slack: Float = 3f) {
        val boxes = tab.engraving.value!!.boxes
        for (box in listOf(boxes.first(), boxes.last())) {
            val mark = drawn(tab, box)
            val el = element("fs-tab-mark-${box.column}")
            assertTrue("$where: the element of mark ${box.column} ($el) is over the drawn mark ($mark)",
                el.left - slack <= mark.left && mark.right <= el.right + slack && el.top - slack <= mark.top && mark.bottom <= el.bottom + slack)
            // And it starts where the mark starts (or a little above, where the mark and its numerals are less than 48 dp tall).
            val target = 48 * rule.activity.resources.displayMetrics.density
            assertTrue("$where: the element of mark ${box.column} starts at the mark (${el.top} for ${mark.top})", mark.top - el.top <= (target - (box.columnBottom - box.top)).coerceAtLeast(0f) / 2 + slack)
        }
    }

    @Test
    fun theMarksElementsAreOnTheDrawnMarksToTheEndOfThePage() {
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        var tab = showTheTab()
        fun check(where: String) {
            tab = engraved()
            toTheEnd()
            val (at, max) = scrolled()
            var page = 0; var range = 0
            rule.runOnUiThread { page = tab.pageScrolled; range = tab.pageScrollRange }
            android.util.Log.i("TabViewTest", "scroll ranges, $where: the screen's ${max.toInt()} px, alphaTab's $range px, the header in the scroll ${max.toInt() - range} px; at the end ${at.toInt()} and $page")
            assertEquals("$where: at the end of the screen's scroll", max, at, 0.5f)
            assertEquals("$where: alphaTab's page is at its own end too", range, page)
            assertTrue("$where: the screen's scroll is alphaTab's and the header's", max.toInt() - range in 0..(rule.activity.resources.displayMetrics.heightPixels / 2))
            assertTheElementsAreOnTheMarks(tab, "$where, at the end")
            // The last mark, as it is on the screen: the "?" inside its element.
            val last = tab.engraving.value!!.boxes.last()
            val image = still()
            val el = element("fs-tab-mark-${last.column}")
            val mark = drawn(tab, last)
            val glyph = Rect(el.left.toInt(), (mark.top - 3).toInt(), el.right.toInt(), (mark.bottom + 0.3f * tab.lineSpace).toInt())
            assertTrue("$where: the last ? is drawn where its element is", count(image, glyph, BrasscribeLightColors.uncertain.toArgb()) > 40)
            scrollBy(-scrolled().first)
            assertTheElementsAreOnTheMarks(tab, "$where, at the top")
        }
        check("upright at 100 %")
        shotOf("tab-end-of-page")
        repeat(5) { rule.onNodeWithTag("fs-tab-zoom-in").performClick() }
        waitUntil(20_000) { TabScreenProbe.view?.engraving?.value?.barsPerLine?.all { it == 1 } == true }
        tab = engraved()
        check("upright at 150 %")
        repeat(5) { rule.onNodeWithTag("fs-tab-zoom-out").performClick() }
        turn(landscape = true)
        check("on its side at 100 %")
        shotOf("tab-landscape-end-of-page")
    }

    /**
     * The page is drawn where the tab is on the screen: string lines and ink numerals, by their pixels. What
     * alphaTab's layout says is no proof of that: a page can be laid out and its lines left undrawn.
     */
    private fun assertThePageIsDrawn(where: String, colours: BrasscribeColors = BrasscribeLightColors) {
        val image = still()
        val area = bounds("fs-tab")
        val lines = count(image, area, colours.staff.toArgb(), 24)
        val ink = count(image, area, colours.ink.toArgb(), 24)
        android.util.Log.i("TabViewTest", "drawn, $where: $lines pixels of string lines and $ink of ink in $area")
        assertTrue("$where: the staff is drawn ($lines pixels of string lines)", lines > 3000)
        assertTrue("$where: the numbers are drawn ($ink pixels of ink)", ink > 800)
    }

    @Test
    @DeviceOnly
    fun turnedOnItsSideFromTheEndOfThePageTheTabIsDrawn() {
        // A device's: where alphaTab's page is after a turn follows the scroll steps the phone's window sends it, and the
        // JVM's phone is turned by hand (ScreenDevice.turn), which leaves the page a line off or undrawn.
        assumeTrue("on a device only: the turned page", !ScreenDevice.JVM)
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        var tab = showTheTab()
        for (percent in listOf(100, 150)) {
            if (percent == 150) {
                repeat(5) { rule.onNodeWithTag("fs-tab-zoom-in").performClick() }
                tab = engraved()
            }
            // Upright, scrolled to the end: bar 10 or later is at the top.
            toTheEnd()
            rule.onNodeWithTag("fs-tab-scroll").performTouchInput { down(center); moveBy(androidx.compose.ui.geometry.Offset(0f, -40f)); up() }
            settle()
            assertTrue("at $percent %, bar ${barInView(tab) + 1} is at the top before the turn", barInView(tab) >= 9)
            assertThePageIsDrawn("upright at the end, $percent %")
            val upright = tab
            turn(landscape = true)
            tab = engraved()
            // On its side: the staff and the numbers are on the screen, at once and after a swipe.
            assertThePageIsDrawn("on its side from the end, $percent %")
            assertTrue("a turned phone has a view of its own", tab !== upright)
            shotOf("tab-turned-from-the-end-$percent")
            rule.onNodeWithTag("fs-tab-scroll").performTouchInput { swipeDown() }
            assertThePageIsDrawn("on its side after a swipe, $percent %")
            rule.onNodeWithTag("fs-tab-scroll").performTouchInput { swipeUp() }
            assertThePageIsDrawn("on its side after a swipe back, $percent %")
            assertEquals(0, tab.unmatched)
            turn(landscape = false)
            tab = engraved()
            assertThePageIsDrawn("upright again, $percent %")
        }
    }

    @Test
    fun theKeysMoveThePageBeforeAnythingHasTheFocus() {
        computer("bass-line-marks")
        showTheTab()
        // No Tab has been pressed: nothing on the screen was reached with the keyboard.
        assertEquals(0f, scrolled().first)
        key(KeyEvent.KEYCODE_PAGE_DOWN)
        settle()
        val one = scrolled().first
        assertTrue("Page Down moves the page ($one)", one > 300f)
        key(KeyEvent.KEYCODE_MOVE_END)
        settle()
        scrolled().let { (at, max) -> assertEquals("End", max, at, 0.5f) }
        key(KeyEvent.KEYCODE_MOVE_HOME)
        settle()
        assertEquals("Home, from the end of the page", 0f, scrolled().first)
        key(KeyEvent.KEYCODE_MOVE_END)
        settle()
        key(KeyEvent.KEYCODE_PAGE_UP)
        settle()
        scrolled().let { (at, max) -> assertTrue("Page Up from the end ($at of $max)", at < max - 300f) }
        // After a tap on the page (a mark told, then closed) the keys still move it.
        rule.onNodeWithTag("fs-tab-mark-2").performScrollTo().performClick()
        rule.onNodeWithTag("fs-tab-note-close").performClick()
        key(KeyEvent.KEYCODE_MOVE_HOME)
        settle()
        assertEquals("Home after a tap", 0f, scrolled().first)
    }

    /** The bar the page is read at: the first bar of the first line that is not scrolled past. */
    private fun barInView(tab: TabView): Int {
        var bar = -1
        rule.runOnUiThread { bar = tab.engraving.value!!.barAt(tab.pageScrolled) ?: -1 }
        return bar
    }

    @Test
    @DeviceOnly
    fun theBarBeingReadIsKeptThroughATurnASizeAndAVisitToCheckTheSong() {
        // A device's: where alphaTab's page is after a turn follows the scroll steps the phone's window sends it, and the
        // JVM's phone is turned by hand (ScreenDevice.turn), which leaves the page a line off or undrawn.
        assumeTrue("on a device only: the turned page", !ScreenDevice.JVM)
        computer("bass-line-marks")
        var tab = showTheTab()
        // Read on to the line of bar 10 (the tenth bar is counted 9 from 0).
        val line = tab.engraving.value!!.lines.first { 9 in it.firstBar..it.lastBar }
        var range = 0
        rule.runOnUiThread { range = tab.pageScrollRange }
        scrollBy(scrolled().second - range + line.top - scrolled().first)
        val reading = barInView(tab)
        assertEquals("reading at the line of bar 10", line.firstBar, reading)
        fun assertStillThere(where: String) {
            tab = engraved()
            waitUntil(10_000) { barLineHolds(tab, reading) }
            tab = engraved()
            assertTrue("$where: the line of bar ${reading + 1} is the first in view (bar ${barInView(tab) + 1} is)", barLineHolds(tab, reading))
            android.util.Log.i("TabViewTest", "the bar being read, $where: bar ${reading + 1} is on the first line in view, which starts at bar ${barInView(tab) + 1}")
        }
        turn(landscape = true)
        assertStillThere("on its side")
        assertThePageIsDrawn("the place kept on its side")
        shotOf("tab-landscape-place")
        turn(landscape = false)
        assertStillThere("upright again")
        assertThePageIsDrawn("the place kept upright again")
        assertEquals("upright again the same line is at the top", reading, barInView(tab))
        val lines = tab.engraving.value!!.lines.size
        repeat(5) { rule.onNodeWithTag("fs-tab-zoom-in").performClick() }
        waitUntil(20_000) { TabScreenProbe.view?.engraving?.value?.lines?.let { it.size > lines } == true }
        tab = engraved()
        assertStillThere("at 150 %")
        shotOf("tab-zoomed-place")
        repeat(5) { rule.onNodeWithTag("fs-tab-zoom-out").performClick() }
        waitUntil(20_000) { TabScreenProbe.view?.engraving?.value?.lines?.size == lines }
        tab = engraved()
        assertStillThere("back at 100 %")
        assertEquals("at 100 % again the same line is at the top", reading, barInView(tab))
        rule.onNodeWithTag("fs-tab-tuning").performClick()
        waitForTag("fs-show-tab")
        rule.onNodeWithTag("fs-show-tab").performClick()
        assertStillThere("after Check the song")
        assertEquals(reading, barInView(tab))
    }

    /** The first line in view is the line with [bar], or the page is at its end and that line is in view. */
    private fun barLineHolds(tab: TabView, bar: Int): Boolean {
        var holds = false
        rule.runOnUiThread {
            val e = tab.engraving.value ?: return@runOnUiThread
            val first = e.lines.lastOrNull { it.top <= tab.pageScrolled + 2 } ?: return@runOnUiThread
            val line = e.lines.firstOrNull { bar in it.firstBar..it.lastBar } ?: return@runOnUiThread
            holds = first === line || (tab.pageScrolled >= tab.pageScrollRange - 1 && line.top >= tab.pageScrolled)
        }
        return holds
    }

    private fun nextIsOff(): Boolean = rule.onNodeWithTag("fs-tab-note-next").fetchSemanticsNode().config.getOrNull(SemanticsProperties.StateDescription) != null

    /** The mark whose note is open: its element says what the note says. */
    private fun toldMark(): android.graphics.RectF {
        val words = rule.onNodeWithTag("fs-tab-note").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString(" ") { it.text }
        val node = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.ContentDescription, listOf(words))).fetchSemanticsNodes().single()
        return android.graphics.RectF(node.positionInWindow.x, node.positionInWindow.y, node.positionInWindow.x + node.size.width, node.positionInWindow.y + node.size.height)
    }

    @Test
    fun aMarkShownOnceDoesNotPullThePageBackLater() {
        longSong()
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        showTheTab()
        // "Check them", then Next ? to the last "?".
        rule.onNodeWithTag("fs-tab-marked").performClick()
        waitForTag("fs-tab-note", 5_000)
        repeat(60) { if (!nextIsOff()) { rule.onNodeWithTag("fs-tab-note-next").performClick(); settle() } }
        assertTrue(nextIsOff())
        val atTheLast = scrolled().first
        assertTrue("the page went to the last ? ($atTheLast)", atTheLast > 1_000f)
        // Closed, scrolled back to the top and made larger: the page stays where the player put it.
        rule.onNodeWithTag("fs-tab-note-close").performClick()
        scrollBy(-scrolled().first)
        assertEquals(0f, scrolled().first)
        rule.onNodeWithTag("fs-tab-zoom-in").performClick()
        waitUntil(20_000) { TabScreenProbe.view?.let { it.scale == TabScreenProbe.wanted && it.engraving.value != null } == true }
        engraved()
        settle()
        assertTrue("the page is not pulled back to the last ? (${scrolled().first})", scrolled().first < 100f)
    }

    @Test
    fun onItsSideWithLargeTextEveryMarkIsShownAboveItsNote() {
        longSong()
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        textSize(2.0f)
        turn(landscape = true)
        showTheTab()
        engraved()
        // The page opens on its first line; the "?" line is above it, a scroll up away.
        rule.onNodeWithTag("fs-tab-marked").performScrollTo().performClick()
        waitForTag("fs-tab-note", 5_000)
        var shown = 0
        while (true) {
            settle()
            val window = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow
            val mark = toldMark()
            assertTrue("mark ${shown + 1}: the mark and its numerals (${mark.top}–${mark.bottom}) are in view above the note (${window.top}–${window.bottom})",
                mark.top >= window.top - 1 && mark.bottom <= window.bottom + 1)
            shown++
            if (nextIsOff()) break
            rule.onNodeWithTag("fs-tab-note-next").performClick()
        }
        assertTrue("every ? was shown ($shown)", shown > 10)
        assertNoTextIsClipped()
    }

    @Test
    fun onItsSideWithLargeTextTheHeaderScrollsAwayAndTheTabHasTheScreen() {
        computer("bass-line-marks")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        textSize(2.0f)
        turn(landscape = true)
        TabScreenProbe.made = 0
        var tab = showTheTab()
        tab = engraved()
        // The size was known before the page was engraved: one view, engraved at the size it is shown at.
        assertEquals("views made for the page", 1, TabScreenProbe.made)
        assertEquals(TabView.BASE_SCALE, tab.scale, 0.01)
        assertNoTextIsClipped()
        // The header is the top of the page here, not pinned above it: the page opens on its first line, under the header.
        val opened = scrolled().first
        assertTrue("the page opens past the header ($opened px)", opened > 0)
        val top = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow.top
        assertTrue("the header is above the view", element("fs-tab-tuning").bottom <= top + 1)
        scrollBy(-opened)
        rule.onNodeWithTag("fs-tab-tuning").assertIsDisplayed()
        shotOf("tab-landscape-200-text-top")
        val e = tab.engraving.value!!
        val (_, max) = scrolled()
        var range = 0; var room = 0
        rule.runOnUiThread { range = tab.pageScrollRange; room = tab.view.height }
        val header = max.toInt() - range
        assertTrue("the header scrolls with the page ($header px of it)", header > 0)
        // Scrolled to the second line: the header is gone and the tab has all the room under the top bar.
        scrollBy(header + e.lines[1].top - scrolled().first)
        var page = 0
        rule.runOnUiThread { page = tab.pageScrolled }
        assertEquals(e.lines[1].top.toFloat(), page.toFloat(), 4f)
        val window = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow
        assertTrue("the header is out of view", element("fs-tab-tuning").bottom <= window.top + 1)
        val whole = e.lines.count { it.top >= page - 4 && it.bottom <= page + room + 4 }
        val inView = e.lines.count { it.bottom > page && it.top < page + room }
        android.util.Log.i("TabViewTest", "on its side at 200 % text: scale ${tab.scale} (${TabView.BASE_SCALE} at the ordinary size), a line is ${e.lines[1].bottom - e.lines[1].top} px of $room: $whole whole, $inView in view")
        // On a phone on its side the numerals stay at their ordinary size (twice as large, less than one line would be in view):
        // a whole line and most of the next. The zoom still makes them larger.
        assertEquals(TabView.BASE_SCALE, tab.scale, 0.01)
        assertTrue("a whole line of the tab in view ($whole)", whole >= 1)
        assertTrue("and the next one under it ($inView)", inView >= 2)
        rule.onNodeWithTag("fs-tab-zoom-in").assertIsEnabled()
        assertEquals(0, tab.unmatched)
        assertTheElementsAreOnTheMarks(tab, "on its side at 200 % text")
        checkAccessibility()
        shotOf("tab-landscape-200-text")
    }

    @Test
    fun pageUpAndPageDownMoveThePage() {
        computer("bass-line-marks")
        showTheTab()
        repeat(6) { if (!focusedWords().contains("Tuning: Standard, no capo")) key(KeyEvent.KEYCODE_TAB) }
        assertTrue(focusedWords(), focusedWords().contains("Tuning: Standard, no capo"))
        assertEquals(0f, scrolled().first)
        key(KeyEvent.KEYCODE_PAGE_DOWN)
        settle()
        val one = scrolled().first
        assertTrue("Page Down moves the page ($one)", one > 300f)
        key(KeyEvent.KEYCODE_PAGE_UP)
        settle()
        // (The page is put back at the bar being read once alphaTab has published its layout again, a moment later.)
        runCatching { waitUntil(5_000) { scrolled().first == 0f } }
        assertEquals(0f, scrolled().first)
        key(KeyEvent.KEYCODE_PAGE_DOWN)
        settle()
        assertEquals(one, scrolled().first, 2f)
        key(KeyEvent.KEYCODE_MOVE_END)
        settle()
        scrolled().let { (at, max) -> assertEquals(max, at, 0.5f) }
        key(KeyEvent.KEYCODE_MOVE_HOME)
        settle()
        assertEquals(0f, scrolled().first)
    }

    /**
     * The tests' wait for the tab waits for the player under it too. The player comes once the recording has been looked
     * for on the phone, on Dispatchers.IO, and that can be after the tab is engraved, as on a busy runner: here every
     * thread of Dispatchers.IO is kept busy from the moment the tab's notes are read until the keys have been pressed (or
     * for 8 s). Had the keys paged by the room the tab had before the player came, Page Up would not undo Page Down.
     */
    @Test
    fun theWaitForTheTabWaitsForThePlayerUnderIt() {
        computer("bass-line-marks")
        val given = checkNotNull(container.fixtureSource)
        val keysPressed = CountDownLatch(1)
        val held = java.util.concurrent.atomic.AtomicBoolean()
        container.fixtureSource = FixtureSource { name ->
            // (More tasks than Dispatchers.IO runs at once: 64 threads, unless a system property sets more.)
            if (name == "tab.json" && showing && held.compareAndSet(false, true)) {
                repeat(128) { CoroutineScope(Dispatchers.IO).launch { keysPressed.await(8, TimeUnit.SECONDS) } }
            }
            given.read(name)
        }
        try {
            showTheTab()
            key(KeyEvent.KEYCODE_PAGE_DOWN)
            settle()
            val one = scrolled().first
            keysPressed.countDown()
            waitUntil(10_000) { practice.recording != RecordingState.LOOKING }
            settle()
            key(KeyEvent.KEYCODE_PAGE_UP)
            settle()
            assertEquals("Page Up after Page Down (by $one)", 0f, scrolled().first)
        } finally {
            keysPressed.countDown()
        }
    }

}
