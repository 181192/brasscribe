package no.brasscribe.play.fret

import android.app.UiModeManager
import android.graphics.Bitmap
import android.graphics.Rect
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.Uri
import android.view.KeyEvent
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
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
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.Tab
import no.brasscribe.play.model.BrasscribeJson
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.test.Slow
import org.junit.experimental.categories.Category
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import no.brasscribe.play.test.DeviceOnly

/**
 * Practice, on a fixture computer (apps/fixtures/bass-line-marks): the recording plays under the tab, the
 * cursor stands at the beat it is at, it slows down with its pitch kept, and chosen bars repeat. The
 * recording is made here: a short tone on every note of the fixture's tab, at the second the computer heard
 * it.
 */
@RunWith(AndroidJUnit4::class)
@Category(Slow::class)
class PracticeTest : ScreenTest() {
    private val practice get() = ViewModelProvider(rule.activity)[PracticeModel::class.java]
    private val kept get() = File(rule.activity.noBackupFilesDir, "recordings")

    /** The computer still holds the recording it was sent. */
    @Volatile private var computerHasRecording = true

    @Before
    fun setUp() {
        yourInstrumentStore(rule.activity).save(YourInstrument.DEFAULT)
        kept.deleteRecursively()
        container.fixtureSource = FixtureSource { name ->
            if (name == FixtureEngineApi.INPUT_FILE) sound().takeIf { computerHasRecording }
            else ScreenDevice.fixture("$FIXTURE/$name")
        }
    }

    @After
    fun tearDown() {
        TabPlaces.forget()
        kept.deleteRecursively()
    }

    override val shots = "fretscribe/practice"

    /** The picture [name] of the screen at rest. */
    private fun shotOf(name: String) {
        settle()
        shot(name)
    }

    private fun asset(name: String): String = checkNotNull(ScreenDevice.fixture("$FIXTURE/$name")) { name }.decodeToString()
    private val tabData: Tab by lazy { BrasscribeJson.decodeFromString(Tab.serializer(), asset("tab.json")) }
    private val index: TabIndex by lazy { TabIndex.parse(asset("tab.musicxml")) }
    private val clock: TabClock by lazy { TabClock.of(index, tabData, null)!! }

    /** The recording: a decaying tone on each note of the tab, at the second it was heard, as a WAV file's bytes. */
    private fun sound(): ByteArray {
        val rate = 22_050
        val notes = org.json.JSONObject(asset("tab.json")).getJSONArray("notes")
        val length = ((0 until notes.length()).maxOf { notes.getJSONObject(it).getDouble("offset_s") } + 1.0)
        val samples = FloatArray((length * rate).toInt())
        for (i in 0 until notes.length()) {
            val n = notes.getJSONObject(i)
            val hz = 440.0 * Math.pow(2.0, (n.getInt("pitch") - 69) / 12.0)
            val from = (n.getDouble("onset_s") * rate).toInt().coerceAtLeast(0)
            val to = (n.getDouble("offset_s") * rate).toInt().coerceAtMost(samples.size)
            for (k in from until to) samples[k] += (Math.sin(2 * Math.PI * hz * (k - from) / rate) * Math.exp(-3.0 * (k - from) / rate) * 0.4).toFloat()
        }
        val data = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN).also { b -> samples.forEach { b.putShort((it.coerceIn(-1f, 1f) * 32_000).toInt().toShort()) } }.array()
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
            .putInt(rate).putInt(rate * 2).putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size).array()
        return header + data
    }

    /** Home, the recording, What is this?, the notes written down, Check the song, Show the tab: the tab is engraved and the player is there. */
    private fun practise(): TabView {
        val file = ScreenDevice.recording(rule.activity, "Bass line.wav", sound(), 22_050)
        rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(file)) }
        waitForTag("fs-what-continue", 20_000)
        rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-instrument"))).performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        rule.onNodeWithTag("fs-show-tab").performClick()
        val tab = engraved()
        waitForTag("fs-practice-play", 20_000)
        return tab
    }

    private fun engraved(): TabView {
        waitForTag("fs-tab", 30_000)
        fun now() = TabScreenProbe.view?.let { Triple(it, it.engravings, it.engraving.value) }
        var seen: Triple<TabView, Int, TabEngraving?>?
        do {
            waitUntil(30_000) { TabScreenProbe.view?.let { it.engraving.value != null && it.scale == TabScreenProbe.wanted } == true }
            seen = now()
            settle()
        } while (now() != seen)
        return seen!!.first
    }

    private fun words(tag: String): String = rule.onNodeWithTag(tag).fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text).orEmpty().joinToString(" ") { it.text }
    private fun described(tag: String): String = rule.onNodeWithTag(tag, useUnmergedTree = true).fetchSemanticsNode().let { n ->
        (n.config.getOrNull(SemanticsProperties.ContentDescription).orEmpty() + n.children.flatMap { it.config.getOrNull(SemanticsProperties.ContentDescription).orEmpty() }).joinToString(" ")
    }
    /** What a screen reader says of the state of [tag], beside its name. */
    private fun state(tag: String): String? = rule.onNodeWithTag(tag).fetchSemanticsNode().config.getOrNull(SemanticsProperties.StateDescription)
    private fun isLive(tag: String): Boolean = rule.onNodeWithTag(tag).fetchSemanticsNode().config.contains(SemanticsProperties.LiveRegion)

    /** Where the recording is, in seconds, and whether it is playing, read together on the main thread. */
    private fun now(): Double {
        var at = 0.0
        rule.runOnUiThread { at = practice.now() }
        return at
    }

    private fun waitUntilPlaying(playing: Boolean = true) = waitUntil(10_000) { practice.playing == playing }

    /** The whole screen at rest, to look at its pixels. */
    private fun still(): Bitmap {
        settle()
        return screen()
    }

    private fun near(pixel: Int, colour: Int, tolerance: Int = 30): Boolean =
        abs((pixel shr 16 and 0xFF) - (colour shr 16 and 0xFF)) <= tolerance && abs((pixel shr 8 and 0xFF) - (colour shr 8 and 0xFF)) <= tolerance &&
            abs((pixel and 0xFF) - (colour and 0xFF)) <= tolerance

    private fun count(image: Bitmap, area: Rect, colour: Int): Int {
        var n = 0
        for (y in maxOf(0, area.top) until minOf(image.height, area.bottom)) for (x in maxOf(0, area.left) until minOf(image.width, area.right)) {
            if (near(image.getPixel(x, y), colour)) n++
        }
        return n
    }

    /** A box of the page, in the page's pixels, as it lies on the screen. */
    private fun onScreen(tab: TabView, left: Float, top: Float, right: Float, bottom: Float): Rect {
        var out = Rect()
        rule.runOnUiThread {
            val at = IntArray(2).also(tab.view::getLocationOnScreen)
            out = Rect((at[0] + left).toInt(), (at[1] + top - tab.pageScrolled).toInt(), (at[0] + right).toInt() + 1, (at[1] + bottom - tab.pageScrolled).toInt() + 1)
        }
        return out
    }

    private fun cursor(tab: TabView): Pair<BarBox, CursorStop>? {
        var at: Pair<BarBox, CursorStop>? = null
        rule.runOnUiThread { at = tab.cursor }
        return at
    }

    /** The cursor's line is on the screen in [colours], at the left edge of its beat's column. */
    private fun assertTheCursorIsDrawn(tab: TabView, colours: BrasscribeColors, where: String) {
        val image = still()
        val (bar, stop) = cursor(tab) ?: throw AssertionError("$where: no cursor")
        val density = rule.activity.resources.displayMetrics.density
        val line = onScreen(tab, stop.left - TabTokens.CURSOR_DP * density, bar.top, stop.left, bar.bottom)
        val drawn = count(image, line, colours.cursor.toArgb())
        assertTrue("$where: the cursor's line is drawn in its colour ($drawn of ${line.width() * line.height()} px in $line)", drawn >= line.width() * line.height() * 0.7)
        // Nothing else in the tab is in the cursor's colour: it is the only blue in it.
        val page = onScreen(tab, 0f, bar.top, tab.view.width.toFloat(), bar.bottom)
        val elsewhere = count(image, Rect(line.right + 2, page.top, page.right, page.bottom), colours.cursor.toArgb())
        assertEquals("$where: the cursor's colour away from the cursor", 0, elsewhere)
    }

    private fun focusedTag(): String = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true))
        .fetchSemanticsNodes().lastOrNull()?.config?.getOrNull(SemanticsProperties.TestTag).orEmpty()

    private fun turn(landscape: Boolean) = ScreenDevice.turn(rule, landscape)

    @Test
    fun theRecordingPlaysAndTheCursorFollowsIt() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = practise()
        // The transport is 64 dp, in the design's order, and says what it does.
        for (tag in listOf("fs-practice-play", "fs-practice-start", "fs-practice-previous", "fs-practice-next")) {
            rule.onNodeWithTag(tag).assertIsDisplayed().assertWidthIsAtLeast(64.dp).assertHeightIsAtLeast(64.dp)
        }
        for (tag in listOf("fs-practice-slower", "fs-practice-faster", "fs-practice-repeat")) rule.onNodeWithTag(tag).assertWidthIsAtLeast(48.dp).assertHeightIsAtLeast(48.dp)
        val order = listOf("fs-practice-play", "fs-practice-start", "fs-practice-previous", "fs-practice-next", "fs-practice-place", "fs-practice-slower", "fs-practice-speed", "fs-practice-faster", "fs-practice-repeat")
        val places = order.map { rule.onNodeWithTag(it).fetchSemanticsNode().boundsInWindow }
        places.zipWithNext().forEachIndexed { i, (a, b) -> assertTrue("${order[i]} comes before ${order[i + 1]}", b.top >= a.bottom - 1 || b.left >= a.right - 1) }
        assertEquals("Play", described("fs-practice-play"))
        assertEquals("Back to the start", described("fs-practice-start"))
        assertEquals("Previous bar", described("fs-practice-previous"))
        assertEquals("Next bar", described("fs-practice-next"))
        assertEquals("Bar 1, beat 1", words("fs-practice-place"))
        // The cursor stands at the first beat before anything plays.
        assertEquals(0, cursor(tab)!!.first.bar)
        assertTheCursorIsDrawn(tab, BrasscribeLightColors, "at the start")
        shotOf("practice-light")

        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        assertEquals("Pause", described("fs-practice-play"))
        // While it plays, the place changes with every beat and is not announced.
        assertFalse("the place is a live region while the recording plays", isLive("fs-practice-place"))
        // The cursor is at the beat the recording is at, all the way: sampled while it plays.
        var checked = 0
        val ahead = HashSet<Int>()
        while (now() < clock.secondsAt(6)) {
            var at = 0.0
            var shown: Pair<BarBox, CursorStop>? = null
            rule.runOnUiThread { at = practice.now(); shown = tab.cursor }
            val (bar, stop) = shown ?: throw AssertionError("no cursor while playing")
            // The cursor was put there a few frames ago (the test's own work is on the same thread).
            val fits = (0..6).map { at - it * 0.05 }.any { t -> clock.placeAt(t.coerceAtLeast(0.0)).let { p -> p.bar == bar.bar && bar.stopAt(p.tick) == stop } }
            assertTrue("at $at s the cursor is in bar ${bar.bar} at tick ${stop.tick}, the recording at ${clock.placeAt(at)}", fits)
            ahead += bar.bar
            checked++
            ScreenDevice.elapse(rule, 40)
        }
        assertTrue("the cursor was looked at often ($checked)", checked > 30)
        assertTrue("it went through the bars one after another ($ahead)", ahead.containsAll((1..5).toList()))
        var staysOn = false
        rule.runOnUiThread { staysOn = generateSequence(tab.view as android.view.View?) { it.parent as? android.view.View }.any { it.keepScreenOn } }
        assertTrue("the screen stays on while the recording plays", staysOn)

        val said = java.util.Collections.synchronizedList(ArrayList<String>())
        val listening = ScreenDevice.announcements(rule) { said += it }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying(false)
        assertEquals("Play", described("fs-practice-play"))
        val stopped = now()
        // The place it stopped at is said, once. (What is said reaches a screen reader on a device; on the JVM nothing listens.)
        if (!ScreenDevice.JVM) waitUntil(5_000) { said.isNotEmpty() }
        settle()
        listening.close()
        if (!ScreenDevice.JVM) assertEquals(listOf(words("fs-practice-place")), said.toList())
        assertTrue("it stopped where it was ($stopped s)", stopped >= clock.secondsAt(6) - 0.2 && stopped < clock.secondsAt(8))
        val there = clock.placeAt(stopped)
        assertEquals(text(no.brasscribe.play.R.string.fs_practice_bar_beat, index.measures[there.bar].number, clock.beatAt(there)), words("fs-practice-place"))
        assertTrue("the place is announced when the player moves it", isLive("fs-practice-place"))
        assertEquals(there.bar, cursor(tab)!!.first.bar)
        assertTheCursorIsDrawn(tab, BrasscribeLightColors, "after a pause")
        checkAccessibility()
        shotOf("practice-paused")

        // A bar on, a bar back, and back to the start.
        rule.onNodeWithTag("fs-practice-next").performClick()
        rule.waitForIdle()
        assertEquals(text(no.brasscribe.play.R.string.fs_practice_bar_beat, index.measures[there.bar + 1].number, 1), words("fs-practice-place"))
        assertEquals(clock.secondsAt(there.bar + 1), now(), 0.002)
        rule.onNodeWithTag("fs-practice-previous").performClick()
        rule.onNodeWithTag("fs-practice-previous").performClick()
        rule.waitForIdle()
        assertEquals(clock.secondsAt(there.bar - 1), now(), 0.002)
        rule.onNodeWithTag("fs-practice-start").performClick()
        rule.waitForIdle()
        assertEquals("Bar 1, beat 1", words("fs-practice-place"))
        assertEquals(0, cursor(tab)!!.first.bar)
    }

    @Test
    fun slowedDownTheRecordingKeepsItsPitch() {
        practise()
        assertEquals("100%", words("fs-practice-speed"))
        rule.onNodeWithTag("fs-practice-speed").assertContentDescriptionEquals("Speed 100%")
        assertTrue("a change of speed is said", isLive("fs-practice-speed"))
        assertEquals("Slower", described("fs-practice-slower"))
        assertEquals("Faster", described("fs-practice-faster"))
        rule.onNodeWithTag("fs-practice-slower").performClick()
        assertEquals("95%", words("fs-practice-speed"))
        repeat(9) { rule.onNodeWithTag("fs-practice-slower").performClick() }
        assertEquals("50%", words("fs-practice-speed"))
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        waitUntil(10_000) { now() > 0.3 }
        val from = now()
        val began = System.nanoTime()
        ScreenDevice.elapse(rule, 4_000)
        val went = now() - from
        val took = (System.nanoTime() - began) / 1e9
        // (How fast it goes by the clock on the wall is the phone's sound output's: on the JVM nothing plays it out.)
        if (!ScreenDevice.JVM) assertEquals("at half speed the recording goes half as fast ($went s in $took s)", 0.5, went / took, 0.06)
        assertTrue("it plays on ($went s in $took s)", went > 0.2)
        rule.runOnUiThread {
            val player = practice.recordingPlayer as MediaRecordingPlayer
            assertEquals(0.5f, player.speed, 0.001f)
            assertEquals("the pitch is the recording's own", 1f, player.pitch, 0f)
        }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying(false)
        // To its ends: 25 % and 150 %, and no further.
        repeat(8) { rule.onNodeWithTag("fs-practice-slower").performClick() }
        assertEquals("25%", words("fs-practice-speed"))
        rule.onNodeWithTag("fs-practice-slower").assertIsNotEnabled()
        repeat(30) { if (words("fs-practice-speed") != "150%") rule.onNodeWithTag("fs-practice-faster").performClick() }
        assertEquals("150%", words("fs-practice-speed"))
        rule.onNodeWithTag("fs-practice-faster").assertIsNotEnabled()
        rule.onNodeWithTag("fs-practice-slower").assertIsEnabled()
    }

    @Test
    fun chosenBarsRepeat() {
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        val tab = practise()
        assertEquals("Repeat bars", words("fs-practice-repeat"))
        rule.onNodeWithTag("fs-practice-repeat").performClick()
        waitForTag("fs-practice-repeat-set")
        // Four bars from the bar the song is in; each end is moved a bar at a time, and neither passes the other.
        assertEquals("Repeat bars 1 to 4", words("fs-practice-repeat-set"))
        rule.onNodeWithTag("fs-practice-from").assertContentDescriptionEquals("From bar 1")
        assertTrue(isLive("fs-practice-from"))
        rule.onNodeWithTag("fs-practice-from-down").assertIsNotEnabled()
        assertEquals("From bar: one bar later", described("fs-practice-from-up"))
        for (tag in listOf("fs-practice-from-down", "fs-practice-from-up", "fs-practice-to-down", "fs-practice-to-up")) rule.onNodeWithTag(tag).assertWidthIsAtLeast(48.dp).assertHeightIsAtLeast(48.dp)
        repeat(2) { rule.onNodeWithTag("fs-practice-from-up").performClick() }
        assertEquals("Repeat bars 3 to 4", words("fs-practice-repeat-set"))
        repeat(2) { rule.onNodeWithTag("fs-practice-from-up").performClick() }
        assertEquals("Repeat bar 5", words("fs-practice-repeat-set"))
        repeat(2) { rule.onNodeWithTag("fs-practice-to-down").performClick() }
        assertEquals("Repeat bar 3", words("fs-practice-repeat-set"))
        rule.onNodeWithTag("fs-practice-to-up").performClick()
        assertEquals("Repeat bars 3 to 4", words("fs-practice-repeat-set"))
        checkAccessibility()
        shotOf("practice-repeat-dialog")
        rule.onNodeWithTag("fs-practice-repeat-set").performClick()
        rule.waitForIdle()

        // The chip says it, the tab shows it, and the song is at its first bar.
        // What the chip shows is what it is called.
        assertEquals("Repeating 3–4", words("fs-practice-repeat"))
        assertEquals("", described("fs-practice-repeat"))
        assertEquals("Back to the start of the repeat", described("fs-practice-start"))
        assertEquals("Bar 3, beat 1", words("fs-practice-place"))
        rule.runOnUiThread { assertEquals(2..3, tab.repeat) }
        val span = clock.span(RepeatBars(2, 3))
        assertEquals(span.start, now(), 0.002)
        // A bracket at each end in the repeat's colour, and the band behind the bars.
        val bars = tab.engraving.value!!.bars
        val first = bars.first { it.bar == 2 }
        val last = bars.first { it.bar == 3 }
        val density = rule.activity.resources.displayMetrics.density
        val image = still()
        val edge = BrasscribeLightColors.loopEdge.toArgb()
        val open = onScreen(tab, first.left, first.staffTop, first.left + TabTokens.CURSOR_DP * density, first.bottom)
        val close = onScreen(tab, last.right - TabTokens.CURSOR_DP * density, last.staffTop, last.right, last.bottom)
        assertTrue("the bracket before bar 3", count(image, open, edge) >= open.width() * open.height() * 0.6)
        assertTrue("the bracket after bar 4", count(image, close, edge) >= close.width() * close.height() * 0.6)
        val band = onScreen(tab, first.left + 8 * density, first.top - 0.3f * tab.lineSpace, first.left + 16 * density, first.top - 0.1f * tab.lineSpace)
        assertTrue("the band behind the bars", count(image, band, BrasscribeLightColors.loopTint.toArgb()) >= band.width() * band.height() * 0.9)
        checkAccessibility()
        shotOf("practice-repeat")

        // It plays those bars again and again: the recording never leaves them, and turns back at their end.
        repeat(10) { rule.onNodeWithTag("fs-practice-faster").performClick() }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        var turns = 0
        var before = now()
        val until = System.nanoTime() + 7_000_000_000L
        while (System.nanoTime() < until) {
            val at = now()
            assertTrue("the recording stays in its bars ($at s of ${span.start}–${span.endInclusive})", at >= span.start - 0.05 && at <= span.endInclusive + 0.25)
            if (at < before - 0.5) turns++
            before = at
            ScreenDevice.elapse(rule, 30)
        }
        assertTrue("it turned back at the end of the bars ($turns times in 7 s)", turns >= 2)
        // Steps stay inside the bars too.
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying(false)
        rule.runOnUiThread { practice.toBar(2) }
        repeat(3) { rule.onNodeWithTag("fs-practice-next").performClick() }
        assertEquals("Bar 4, beat 1", words("fs-practice-place"))
        // In the last of the bars there is no bar on: the song stays where it is, also part of the way into the bar.
        // (Slowly, so the bar does not end and turn back to the first while the test looks.)
        repeat(25) { rule.onNodeWithTag("fs-practice-slower").performClick() }
        val into = clock.secondsAt(3, 10)
        rule.runOnUiThread { practice.recordingPlayer!!.seekTo(into) }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying(false)
        val inTheLast = now()
        assertTrue("in bar 4 ($inTheLast s)", clock.placeAt(inTheLast).let { it.bar == 3 && it.tick > 0 })
        // Next bar says there is none: off, and why.
        rule.onNodeWithTag("fs-practice-next").assertIsNotEnabled()
        assertEquals("Last bar of the repeat", state("fs-practice-next"))
        assertEquals("Next bar", described("fs-practice-next"))
        rule.onNodeWithTag("fs-practice-next").performClick()
        rule.waitForIdle()
        assertEquals(inTheLast, now(), 0.0)
        repeat(3) { rule.onNodeWithTag("fs-practice-previous").performClick() }
        assertEquals("Bar 3, beat 1", words("fs-practice-place"))
        rule.onNodeWithTag("fs-practice-next").assertIsEnabled()
        assertNull(state("fs-practice-next"))

        // Stop repeating.
        rule.onNodeWithTag("fs-practice-repeat").performClick()
        waitForTag("fs-practice-repeat-stop")
        assertEquals("Repeat bars 3 to 4", words("fs-practice-repeat-set"))
        rule.onNodeWithTag("fs-practice-repeat-stop").performClick()
        rule.waitForIdle()
        assertEquals("Repeat bars", words("fs-practice-repeat"))
        rule.runOnUiThread { assertNull(tab.repeat) }
        assertEquals(0, count(screen(), open, edge))
    }

    @Test
    fun aSongOpenedWithoutItsRecordingSaysSoAndGetsItFromTheComputer() {
        practise()
        // The song is in Your songs now. Opened from there on a phone that no longer has the recording:
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { vm.scores.value.isNotEmpty() }
        settle()
        kept.deleteRecursively()
        computerHasRecording = false
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        waitForTag("fs-practice-get", 20_000)
        rule.onNodeWithTag("fs-practice-says").assertTextEquals("The recording is not on this phone.")
        assertTrue(isLive("fs-practice-says"))
        assertEquals(0, rule.onAllNodesWithTag("fs-practice-play").fetchSemanticsNodes().size)
        rule.onNodeWithTag("fs-practice-get").assertHeightIsAtLeast(48.dp)
        checkAccessibility()
        shotOf("practice-not-on-this-phone")
        // The computer does not have it either.
        rule.onNodeWithTag("fs-practice-get").performClick()
        waitUntil(10_000) { practice.recording == RecordingState.GONE }
        rule.onNodeWithTag("fs-practice-says").assertTextEquals("Your computer doesn't have the recording any more. You can still read the tab.")
        assertEquals(0, rule.onAllNodesWithTag("fs-practice-get").fetchSemanticsNodes().size)
        // The tab is still there to read.
        rule.onNodeWithTag("fs-tab").assertIsDisplayed()

        // A computer that has it: the recording is fetched, kept on the phone, and plays.
        computerHasRecording = true
        rule.runOnUiThread { vm.home() }
        settle()
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        waitForTag("fs-practice-get", 20_000)
        rule.onNodeWithTag("fs-practice-get").performClick()
        waitForTag("fs-practice-play", 20_000)
        assertEquals(1, kept.listFiles()?.size)
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        waitUntil(10_000) { now() > 1.0 }
        // Leaving the tab stops the sound.
        rule.runOnUiThread { vm.home() }
        waitUntil(10_000) { !practice.playing && practice.recordingPlayer == null }
        // Opened again, the recording is on the phone, and the song is where it was left.
        computerHasRecording = false
        rule.runOnUiThread { vm.openEntry(vm.scores.value.first()) }
        engraved()
        waitForTag("fs-practice-play", 20_000)
        assertTrue("the song is where it was left (${now()} s)", now() > 1.0)
    }

    @Test
    fun theKeysPlayPauseAndMoveByBar() {
        val tab = practise()
        // The screen has the keyboard's focus when it opens: the keys work before anything on it has been reached.
        key(KeyEvent.KEYCODE_DPAD_RIGHT)
        assertEquals("Bar 2, beat 1", words("fs-practice-place"))
        key(KeyEvent.KEYCODE_DPAD_RIGHT)
        assertEquals("Bar 3, beat 1", words("fs-practice-place"))
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        assertEquals("Bar 2, beat 1", words("fs-practice-place"))
        assertEquals(1, cursor(tab)!!.first.bar)
        // Space plays. Held down, it plays once, not once more for every repeat of the key.
        ScreenDevice.hold(rule, KeyEvent.KEYCODE_SPACE, repeats = 3)
        waitUntilPlaying()
        ScreenDevice.elapse(rule, 500)
        assertTrue("still playing after Space was held", practice.playing)
        waitUntil(10_000) { now() > clock.secondsAt(1) + 0.3 }
        key(KeyEvent.KEYCODE_SPACE)
        waitUntilPlaying(false)
        // Page Down still moves the page, not the song.
        val at = now()
        key(KeyEvent.KEYCODE_PAGE_DOWN)
        assertEquals(at, now(), 0.0)
        // On a button, Space is that button's press: on Next bar it goes a bar on and does not play.
        repeat(30) { if (focusedTag() != "fs-practice-next") key(KeyEvent.KEYCODE_TAB) }
        assertEquals("fs-practice-next", focusedTag())
        val bar = clock.placeAt(now()).bar
        key(KeyEvent.KEYCODE_SPACE)
        rule.waitForIdle()
        assertFalse(practice.playing)
        assertEquals(clock.secondsAt(bar + 1), now(), 0.002)
        // With a repeat, left goes back to its start.
        rule.runOnUiThread { practice.repeat(RepeatBars(4, 6)); practice.toBar(6) }
        repeat(30) { if (!focusedTag().startsWith("fs-tab-mark-")) key(KeyEvent.KEYCODE_TAB) }
        assertTrue(focusedTag(), focusedTag().startsWith("fs-tab-mark-"))
        shotOf("practice-keyboard-focus")
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        assertEquals("Bar 5, beat 1", words("fs-practice-place"))
        // In the last bar of the tab the right arrow has nowhere to go.
        rule.runOnUiThread { practice.repeat(null); practice.toBar(clock.bars - 1) }
        rule.waitForIdle()
        val last = now()
        key(KeyEvent.KEYCODE_DPAD_RIGHT)
        assertEquals(last, now(), 0.0)
        rule.runOnUiThread { practice.repeat(RepeatBars(4, 6)); practice.toBar(4) }
        rule.waitForIdle()
        // On the player the arrows are the focus's own.
        repeat(30) { if (focusedTag() != "fs-practice-next") key(KeyEvent.KEYCODE_TAB) }
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        assertEquals("Bar 5, beat 1", words("fs-practice-place"))
        // Next bar pressed on to the last bar of the repeat: it says there is no bar on, and the focus stays on it.
        // (The left arrow took the focus to Previous bar.)
        repeat(30) { if (focusedTag() != "fs-practice-next") key(KeyEvent.KEYCODE_TAB) }
        key(KeyEvent.KEYCODE_SPACE)
        key(KeyEvent.KEYCODE_SPACE)
        assertEquals("Bar 7, beat 1", words("fs-practice-place"))
        assertEquals("fs-practice-next", focusedTag())
        rule.onNodeWithTag("fs-practice-next").assertIsNotEnabled()
        assertEquals("Last bar of the repeat", state("fs-practice-next"))
        key(KeyEvent.KEYCODE_SPACE)
        assertEquals("Bar 7, beat 1", words("fs-practice-place"))
        assertEquals("fs-practice-next", focusedTag())
        // Without the repeat, the last bar of the tab.
        rule.runOnUiThread { practice.repeat(null); practice.toBar(clock.bars - 1) }
        rule.waitForIdle()
        assertEquals("fs-practice-next", focusedTag())
        assertEquals("Last bar", state("fs-practice-next"))
    }

    @Test
    @DeviceOnly
    fun aCallThatTakesTheSoundForAWhilePausesTheSongAndItGoesOnAfter() {
        assumeTrue("on a device only: Robolectric's audio manager does not tell the player its focus is lost", !ScreenDevice.JVM)
        practise()
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        waitUntil(10_000) { now() > 0.5 }
        // What a phone call does: it takes the sound for a while, from this app's own AudioManager.
        val audio = rule.activity.getSystemService(AudioManager::class.java)
        val call = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).build())
            .build()
        var abandoned = false
        try {
            assertEquals(AudioManager.AUDIOFOCUS_REQUEST_GRANTED, audio.requestAudioFocus(call))
            waitUntilPlaying(false)
            rule.waitForIdle()
            assertEquals("Play", described("fs-practice-play"))
            val held = now()
            // Nothing moves while the call has the sound: no frames, and the recording stays where it is.
            assertEquals("frames drawn in four seconds of the call", 0, ScreenDevice.framesWhileStill(rule).let { if (it <= 2) 0 else it })
            assertEquals(held, now(), 0.05)
            // When the call ends, the song goes on by itself.
            audio.abandonAudioFocusRequest(call)
            abandoned = true
            waitUntilPlaying()
            rule.waitForIdle()
            assertEquals("Pause", described("fs-practice-play"))
            waitUntil(10_000) { now() > held + 0.3 }
        } finally {
            // A later test never starts without the sound.
            if (!abandoned) audio.abandonAudioFocusRequest(call)
        }
    }

    @Test
    @DeviceOnly
    fun aPausedSongDrawsNothing() {
        assumeTrue("on a device only: the frames are counted by its system", !ScreenDevice.JVM)
        practise()
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        // While it plays, the cursor moves: frames are drawn.
        val before = ScreenDevice.framesDrawn(rule)
        waitUntil(15_000) { now() > clock.secondsAt(3) }
        assertTrue("playing draws frames", ScreenDevice.framesDrawn(rule) - before > 3)
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying(false)
        val paused = ScreenDevice.framesWhileStill(rule)
        rule.runOnUiThread { practice.repeat(RepeatBars(1, 2)) }
        val withRepeat = ScreenDevice.framesWhileStill(rule)
        assertEquals("frames drawn in four seconds of a paused song, and of one with a repeat", listOf(0, 0), listOf(paused, withRepeat).map { if (it <= 2) 0 else it })
    }

    @Test
    fun thePageFollowsTheRecordingFromLineToLine() {
        val tab = practise()
        val e = tab.engraving.value!!
        assumeTrue("the tab is one line on this screen", e.lines.size > 2)
        // Sped up, and started in the last bar of the first line: the page goes to the second line when the cursor does.
        repeat(10) { rule.onNodeWithTag("fs-practice-faster").performClick() }
        val range = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange]
        assumeTrue("the page fits the screen", range.maxValue() > 0f)
        val third = e.lines[2]
        rule.runOnUiThread { practice.toBar(third.firstBar - 1) }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying()
        waitUntil(15_000) { cursor(tab)?.first?.bar == third.firstBar }
        rule.onNodeWithTag("fs-practice-play").performClick()
        waitUntilPlaying(false)
        settle()
        var page = 0
        var end = 0
        rule.runOnUiThread { page = tab.pageScrolled; end = tab.pageScrollRange }
        assertEquals("the line being played is at the top of the page (or the page is at its end)", minOf(third.top, end).toFloat(), page.toFloat(), 6f)
    }

    @Test
    fun inHighContrastTheCursorAndTheRepeatAreShapesWithoutWashes() {
        assumeTrue("this device does not take the contrast setting", ScreenDevice.highContrast(rule, true))
        val tab = practise()
        rule.runOnUiThread {
            assertNull(tab.palette.cursorTint)
            assertNull(tab.palette.repeatBand)
            practice.repeat(RepeatBars(1, 2))
        }
        settle()
        assertNotNull(cursor(tab))
        assertTheCursorIsDrawn(tab, BrasscribeHighContrastColors, "in high contrast")
        // A repeat over every line of the tab: each line has the rail under its bars, also the ones between the two brackets.
        val e = tab.engraving.value!!
        assumeTrue("the tab is not three lines here", e.lines.size >= 3)
        rule.runOnUiThread { practice.repeat(RepeatBars(e.lines[0].firstBar, e.lines[2].lastBar)) }
        val image = still()
        val density = rule.activity.resources.displayMetrics.density
        val inView = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow.bottom
        var middle = false
        for ((n, line) in e.lines.take(3).withIndex()) {
            val first = e.bar(line.firstBar)!!
            val lastOfLine = e.bar(line.lastBar)!!
            val bottom = first.bottom + 0.5f * tab.lineSpace
            val rail = onScreen(tab, first.left + 40 * density, bottom - TabTokens.CURSOR_DP * density, lastOfLine.right - 40 * density, bottom - 1)
            if (rail.bottom > inView) continue
            if (n == 1) middle = true
            val drawn = count(image, rail, BrasscribeHighContrastColors.loopEdge.toArgb())
            assertTrue("the rail under bars ${line.firstBar}–${line.lastBar} ($drawn of ${rail.width() * rail.height()} px)", drawn >= rail.width() * rail.height() * 0.8)
        }
        assertTrue("the line between the brackets was in view", middle)
        checkAccessibility()
        shotOf("practice-high-contrast")
    }

    @Test
    fun inTheDarkOnItsSideWithLargeTextAndInBokmalThePlayerIsWhole() {
        rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
        var tab = practise()
        rule.runOnUiThread { practice.repeat(RepeatBars(1, 2)) }
        assertTheCursorIsDrawn(tab, BrasscribeDarkColors, "in the dark")
        assertNoTextIsClipped()
        checkAccessibility()
        shotOf("practice-dark")

        // On its side the player is one row, and the tab keeps most of the height.
        turn(landscape = true)
        tab = engraved()
        assertNoTextIsClipped()
        for (tag in listOf("fs-practice-play", "fs-practice-start", "fs-practice-previous", "fs-practice-next")) {
            rule.onNodeWithTag(tag).assertIsDisplayed().assertWidthIsAtLeast(64.dp).assertHeightIsAtLeast(64.dp)
        }
        rule.onNodeWithTag("fs-practice-repeat").assertIsDisplayed()
        val player = rule.onNodeWithTag("fs-practice").fetchSemanticsNode().boundsInWindow
        val page = rule.onNodeWithTag("fs-tab-scroll").fetchSemanticsNode().boundsInWindow
        assertTrue("on its side the tab (${page.height} px) has more room than the player (${player.height} px)", page.height > player.height)
        checkAccessibility()
        shotOf("practice-landscape")

        // At 200 % text everything is still there, whole, and large enough to press.
        textSize(2.0f)
        tab = engraved()
        waitForTag("fs-practice-play", 20_000)
        assertNoTextIsClipped()
        for (tag in listOf("fs-practice-play", "fs-practice-start", "fs-practice-previous", "fs-practice-next")) {
            rule.onNodeWithTag(tag).assertIsDisplayed().assertWidthIsAtLeast(64.dp).assertHeightIsAtLeast(64.dp)
        }
        checkAccessibility()
        shotOf("practice-landscape-200-text")
        // The dialog is taller than the screen here: it scrolls, down to its last button.
        rule.onNodeWithTag("fs-practice-repeat").performClick()
        waitForTag("fs-practice-repeat-set")
        assertNoTextIsClipped()
        rule.onNodeWithTag("fs-practice-repeat-cancel").performScrollTo().assertIsDisplayed()
        shotOf("practice-landscape-200-text-repeat-dialog")
        rule.onNodeWithTag("fs-practice-repeat-cancel").performClick()
        rule.waitForIdle()
        turn(landscape = false)
        tab = engraved()
        assertNoTextIsClipped()
        rule.onNodeWithTag("fs-practice-repeat").assertIsDisplayed()
        rule.onNodeWithTag("fs-practice-repeat").performClick()
        waitForTag("fs-practice-repeat-set")
        assertNoTextIsClipped()
        checkAccessibility()
        shotOf("practice-200-text-repeat-dialog")
        rule.onNodeWithTag("fs-practice-repeat-stop").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithTag("fs-practice-repeat-cancel").performScrollTo().performClick()
        rule.waitForIdle()
        shotOf("practice-200-text")

        // In bokmål.
        textSize(1.0f)
        language("nb-NO")
        engraved()
        waitForTag("fs-practice-play", 20_000)
        assertEquals("Spill av", described("fs-practice-play"))
        assertEquals("Tilbake til starten av gjentakelsen", described("fs-practice-start"))
        assertEquals("Forrige takt", described("fs-practice-previous"))
        assertEquals("Neste takt", described("fs-practice-next"))
        assertEquals("Saktere", described("fs-practice-slower"))
        assertEquals("Raskere", described("fs-practice-faster"))
        assertEquals("Gjentar 2–3", words("fs-practice-repeat"))
        assertTrue(words("fs-practice-place"), words("fs-practice-place").startsWith("Takt "))
        assertTrue(described("fs-practice-speed"), described("fs-practice-speed").startsWith("Tempo 100"))
        checkAccessibility()
        shotOf("practice-nb")
    }

    private companion object {
        const val FIXTURE = "bass-line-marks"
    }
}
