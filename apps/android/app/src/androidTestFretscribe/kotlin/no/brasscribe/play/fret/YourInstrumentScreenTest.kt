package no.brasscribe.play.fret

import android.content.Context
import android.graphics.Bitmap
import android.view.KeyEvent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsNotSelected
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.design.BrasscribeDarkColors
import no.brasscribe.design.BrasscribeLightColors
import no.brasscribe.play.Appearance
import no.brasscribe.play.AppearanceStore
import no.brasscribe.play.MainActivity
import no.brasscribe.play.PlayApplication
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.Product
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.SeatChoice
import no.brasscribe.play.SeatPickerMode
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * "Your instrument" on the device, with the accessibility checks on: asked after the first run in place
 * of Brasscribe's "What do you play?", in English and bokmål, each row one element that says its answer,
 * radio choices in the pickers, 48 dp targets, 200 % text, the keyboard, Not now, and the way in from Settings.
 * Screenshots of the first run, Your instrument and Home, light and dark, go to the app's files,
 * fretscribe/.
 */
@RunWith(AndroidJUnit4::class)
class YourInstrumentScreenTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]
    private val container get() = (rule.activity.application as PlayApplication).container
    private val store get() = yourInstrumentStore(rule.activity)
    private val dir by lazy { File(rule.activity.getExternalFilesDir(null), "fretscribe").apply { mkdirs() } }

    @Before
    fun setUp() {
        assertEquals("Fretscribe", Product.NAME)
        // The first run asks its question only when the core's seats are there: both come with the native core.
        assumeTrue("the native core is not in this build (scripts/build-core.sh)", container.seats.isNotEmpty())
        rule.enableAccessibilityChecks()
        forget()
    }

    @After
    fun tearDown() {
        shell("cmd locale set-app-locales $PACKAGE --locales en-GB")
        shell("settings put system font_scale 1.0")
        forget()
        rule.runOnUiThread {
            container.updateAppearance(Appearance.SYSTEM)
            container.firstRunDone = true
        }
    }

    /** No answer stored, as on a new phone. */
    private fun forget() {
        val prefs = rule.activity.getSharedPreferences(AppearanceStore.PREFS, Context.MODE_PRIVATE).edit()
        listOf(YourInstrumentStore.KIND, YourInstrumentStore.INSTRUMENT, YourInstrumentStore.STRINGS, YourInstrumentStore.TUNING, YourInstrumentStore.HAND, YourInstrumentStore.READS)
            .forEach(prefs::remove)
        prefs.commit()
    }

    private fun shell(cmd: String) {
        instrumentation.uiAutomation.executeShellCommand(cmd).close()
        Thread.sleep(400)
    }

    private fun shot(name: String): Bitmap {
        rule.waitForIdle()
        Thread.sleep(700)
        val shot = checkNotNull(instrumentation.uiAutomation.takeScreenshot()) { "no screenshot" }
        File(dir, "$name.png").outputStream().use { shot.compress(Bitmap.CompressFormat.PNG, 100, it) }
        return shot.copy(Bitmap.Config.ARGB_8888, false)
    }

    /** How many pixels of the screenshot have exactly this colour (anti-aliased edges don't count). */
    private fun Bitmap.count(colour: Color): Int {
        val want = android.graphics.Color.argb(255, (colour.red * 255 + 0.5f).toInt(), (colour.green * 255 + 0.5f).toInt(), (colour.blue * 255 + 0.5f).toInt())
        val pixels = IntArray(width * height).also { getPixels(it, 0, width, 0, 0, width, height) }
        return pixels.count { it == want }
    }

    private fun language(tag: String) {
        shell("cmd locale set-app-locales $PACKAGE --locales $tag")
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
    }

    private fun text(id: Int, vararg args: Any): String = rule.activity.getString(id, *args)

    /** The first-run screen, as a new phone opens on it. */
    private fun firstRun() {
        rule.runOnUiThread {
            container.firstRunDone = false
            vm.home()
            vm.navigate(Screen.FIRST_RUN)
        }
        rule.waitUntil(5_000) { rule.onAllNodesWithText(text(R.string.first_run_start)).fetchSemanticsNodes().isNotEmpty() }
    }

    /** Get started on the first run: Your instrument is next. */
    private fun getStarted() {
        firstRun()
        rule.onNodeWithText(text(R.string.first_run_start)).performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
    }

    private fun row(tag: String): SemanticsNodeInteraction = rule.onNodeWithTag("fs-row-$tag")

    private fun open(tag: String, option: String) {
        row(tag).performScrollTo().performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-$tag-$option").fetchSemanticsNodes().isNotEmpty() }
    }

    private fun pick(tag: String, option: String) {
        open(tag, option)
        rule.onNodeWithTag("fs-$tag-$option").performScrollTo().performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-$tag-$option").fetchSemanticsNodes().isEmpty() }
    }

    private fun closePicker() {
        rule.onNodeWithText(text(R.string.cancel)).performClick()
        rule.waitForIdle()
    }

    /**
     * The element is read once. In the tree a screen reader gets, its name is its one description, it has
     * no text of its own and nothing under it. In the tree as composed, whatever is under it (the question,
     * the answer, the note, the mark) is either cleared by the element or has no words.
     */
    private fun assertSaidOnce(tag: String, prefix: String = "fs-row-") {
        val read = rule.onNodeWithTag("$prefix$tag").fetchSemanticsNode()
        assertEquals("$tag: one description", 1, read.config.getOrNull(SemanticsProperties.ContentDescription)?.size)
        assertEquals("$tag: no text beside the description", null, read.config.getOrNull(SemanticsProperties.Text))
        assertEquals("$tag: nothing under it is read", emptyList<String>(), read.children.map { it.config.toString() })
        // And it is the element a keyboard or a switch lands on.
        assertTrue("$tag: can take the focus", read.config.contains(SemanticsProperties.Focused))
        val composed = rule.onNodeWithTag("$prefix$tag", useUnmergedTree = true).fetchSemanticsNode()
        fun words(node: SemanticsNode): List<String> = node.children.flatMap { child ->
            child.config.getOrNull(SemanticsProperties.Text).orEmpty().map { it.text } +
                child.config.getOrNull(SemanticsProperties.ContentDescription).orEmpty() +
                (if (child.config.isClearingSemantics) emptyList() else words(child))
        }
        if (!composed.config.isClearingSemantics) assertEquals("$tag: no words under it", emptyList<String>(), words(composed))
    }

    private val isRadio = SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)
    private val isPicker = SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.DropdownList)

    /** Every text on screen is drawn whole: no line is cut off or ellipsized. */
    private fun assertNoTextIsClipped() {
        val clipped = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.GetTextLayoutResult), useUnmergedTree = true)
            .fetchSemanticsNodes().mapNotNull { node ->
                val layouts = mutableListOf<TextLayoutResult>()
                node.config.getOrNull(SemanticsActions.GetTextLayoutResult)?.action?.invoke(layouts)
                val l = layouts.firstOrNull() ?: return@mapNotNull null
                // Wrapped text can only run out of lines; one-line text can also be wider than its box.
                // (didOverflowWidth is no use here: it is true for any text narrower than the room it was offered.)
                val cut = l.didOverflowHeight || (0 until l.lineCount).any(l::isLineEllipsized) ||
                    (!l.layoutInput.softWrap && l.multiParagraph.maxIntrinsicWidth > l.size.width + 1f)
                l.layoutInput.text.text.takeIf { cut }
            }
        assertEquals("clipped text", emptyList<String>(), clipped)
    }

    @Test
    fun theFirstRunAsksYourInstrumentInEnglishAndBokmal() {
        val words = mapOf(
            "en-GB" to listOf("Your instrument", "Instrument, Guitar", "Strings, 6 strings", "Usual tuning, Standard",
                "Which hand is on the neck?, Left hand on the neck (most players), Tab looks the same either way.",
                "You read, Tab", "Not now", "Continue"),
            "nb-NO" to listOf("Instrumentet ditt", "Instrument, Gitar", "Strenger, 6 strenger", "Vanlig stemming, Standard",
                "Hvilken hånd er på halsen?, Venstre hånd på halsen (de fleste), Tabben ser lik ut uansett.",
                "Du leser, Tab", "Ikke nå", "Fortsett"),
        )
        // What the rows say as the instrument changes: the bass, the ukulele in its two sizes, the mandolin.
        val others = mapOf(
            "en-GB" to listOf("Instrument, Bass", "Strings, 4 strings", "Instrument, Ukulele", "Size, Soprano, concert or tenor", "Usual tuning, High G",
                "Usual tuning, Low G", "Size, Baritone", "Usual tuning, Standard", "Instrument, Mandolin"),
            "nb-NO" to listOf("Instrument, Bass", "Strenger, 4 strenger", "Instrument, Ukulele", "Størrelse, Sopran, konsert eller tenor", "Vanlig stemming, Høy G",
                "Vanlig stemming, Lav G", "Størrelse, Baryton", "Vanlig stemming, Standard", "Instrument, Mandolin"),
        )
        for ((lang, w) in words) {
            language(lang)
            getStarted()
            // Fretscribe's screen, not Brasscribe's cornet seats.
            assertTrue(rule.onAllNodesWithTag("seat-continue").fetchSemanticsNodes().isEmpty())
            assertEquals(SeatPickerMode.FIRST_RUN, vm.seatPicker)
            rule.onNodeWithText(w[0]).assertIsDisplayed()
            // Each row is one element: its name is the question and the answer, and it opens a list.
            listOf("instrument", "strings", "tuning", "hand", "reads").forEachIndexed { i, tag ->
                row(tag).performScrollTo().assertIsDisplayed().assertHasClickAction()
                    .assertContentDescriptionEquals(w[1 + i]).assert(isPicker)
                    .assertHeightIsAtLeast(48.dp)
                assertSaidOnce(tag)
            }
            rule.onNodeWithTag("fs-not-now").assertIsDisplayed().assert(hasText(w[6]))
                .assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
            rule.onNodeWithTag("fs-keep").assertIsDisplayed().assert(hasText(w[7])).assertHeightIsAtLeast(48.dp)
            // Every instrument can be chosen, and the rows under it follow: a bass by its strings, a ukulele by its
            // size with a high or a low G, a mandolin with nothing more to ask.
            val o = others.getValue(lang)
            pick("tuning", "drop-d")
            pick("instrument", "bass")
            row("instrument").assertContentDescriptionEquals(o[0])
            row("strings").assertContentDescriptionEquals(o[1])
            // (The guitar was in drop D; nothing says the bass is.)
            row("tuning").assertContentDescriptionEquals(w[3])
            pick("instrument", "ukulele")
            row("instrument").assertContentDescriptionEquals(o[2])
            row("strings").assertContentDescriptionEquals(o[3]).assert(isPicker).assertHeightIsAtLeast(48.dp)
            row("tuning").assertContentDescriptionEquals(o[4])
            assertSaidOnce("strings")
            pick("tuning", "low-g")
            row("tuning").assertContentDescriptionEquals(o[5])
            pick("strings", "ukulele-baritone")
            row("strings").assertContentDescriptionEquals(o[6])
            row("tuning").assertContentDescriptionEquals(o[7])
            pick("instrument", "mandolin")
            row("instrument").assertContentDescriptionEquals(o[8])
            row("tuning").assertContentDescriptionEquals(o[7])
            assertTrue(rule.onAllNodesWithTag("fs-row-strings").fetchSemanticsNodes().isEmpty())
            listOf("instrument", "tuning", "hand", "reads").forEach { assertSaidOnce(it) }
            // Nothing of it is kept until Continue.
            assertEquals(YourInstrument.DEFAULT, store.load())
        }
    }

    @Test
    fun thePickersAreRadioGroupsWithFullSizeTargets() {
        val options = mapOf(
            "instrument" to listOf("guitar", "bass", "ukulele", "mandolin"),
            "strings" to listOf("guitar-6", "guitar-7", "guitar-8"),
            "tuning" to listOf("standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e"),
            "hand" to listOf("left", "right", "right-upside-down"),
            "reads" to listOf("tab", "tab-and-notation", "notation"),
        )
        // What each choice is called, in order, per language.
        val names = mapOf(
            "en-GB" to mapOf(
                "instrument" to listOf("Guitar", "Bass", "Ukulele", "Mandolin"),
                "strings" to listOf("6 strings", "7 strings", "8 strings"),
                "tuning" to listOf("Standard", "E-flat standard (half a step down)", "D standard (a whole step down)", "C standard (two whole steps down)",
                    "Drop D", "Drop C", "Drop B", "D, A, D, G, A, D", "Open G", "Open D", "Open E"),
                "hand" to listOf("Left hand on the neck (most players)", "Right hand on the neck (left-handed instrument)", "Right hand on the neck (instrument upside down)"),
                "reads" to listOf("Tab", "Tab and notation", "Notation"),
            ),
            "nb-NO" to mapOf(
                "instrument" to listOf("Gitar", "Bass", "Ukulele", "Mandolin"),
                "strings" to listOf("6 strenger", "7 strenger", "8 strenger"),
                "tuning" to listOf("Standard", "Ess-standard (en halvtone ned)", "D-standard (en heltone ned)", "C-standard (to heltoner ned)",
                    "Drop D", "Drop C", "Drop B", "D, A, D, G, A, D", "Åpen G", "Åpen D", "Åpen E"),
                "hand" to listOf("Venstre hånd på halsen (de fleste)", "Høyre hånd på halsen (venstrehendt instrument)", "Høyre hånd på halsen (instrumentet opp ned)"),
                "reads" to listOf("Tab", "Tab og noter", "Noter"),
            ),
        )
        for ((lang, spoken) in names) {
            language(lang)
            getStarted()
            for ((tag, ids) in options) {
                open(tag, ids.first())
                // The choices are the only radio buttons, one group, in order, and exactly one is chosen.
                val radios = rule.onAllNodes(isRadio).fetchSemanticsNodes()
                assertEquals(tag, ids.map { "fs-$tag-$it" }, radios.map { it.config.getOrNull(SemanticsProperties.TestTag) })
                assertEquals("$tag: one group", 1, radios.map { it.parent?.id }.distinct().size)
                assertTrue("$tag: a group", radios.first().parent?.config?.contains(SemanticsProperties.SelectableGroup) == true)
                assertEquals("$tag: one chosen", listOf(ids.first()), ids.filter { id ->
                    radios.first { it.config.getOrNull(SemanticsProperties.TestTag) == "fs-$tag-$id" }.config.getOrNull(SemanticsProperties.Selected) == true
                })
                // Each is named once, in words (the flat written out, DADGAD letter by letter).
                assertEquals("$lang $tag", spoken.getValue(tag), radios.map { it.config.getOrNull(SemanticsProperties.ContentDescription)?.single() })
                ids.forEach {
                    rule.onNodeWithTag("fs-$tag-$it").performScrollTo().assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
                    assertSaidOnce("$tag-$it", prefix = "fs-")
                }
                closePicker()
            }
            // Every instrument can be chosen; the guitar is the one chosen to begin with.
            open("instrument", "guitar")
            rule.onNodeWithTag("fs-instrument-guitar").assertIsEnabled().assertIsSelected()
            listOf("bass", "ukulele", "mandolin").forEach { rule.onNodeWithTag("fs-instrument-$it").assertIsEnabled().assertIsNotSelected() }
            closePicker()
            // The other instruments' own choices, as they are said: a bass's tunings, a ukulele's sizes and tunings.
            fun said(tag: String, first: String): List<String?> {
                open(tag, first)
                return rule.onAllNodes(isRadio).fetchSemanticsNodes().map { it.config.getOrNull(SemanticsProperties.ContentDescription)?.single() }.also { closePicker() }
            }
            val nb = lang == "nb-NO"
            pick("instrument", "bass")
            assertEquals(if (nb) listOf("4 strenger", "5 strenger", "6 strenger") else listOf("4 strings", "5 strings", "6 strings"), said("strings", "bass-4"))
            assertEquals(spoken.getValue("tuning").take(3) + listOf("Drop D", "B, E, A, D"), said("tuning", "standard"))
            pick("instrument", "ukulele")
            assertEquals(if (nb) listOf("Sopran, konsert eller tenor", "Baryton") else listOf("Soprano, concert or tenor", "Baritone"), said("strings", "ukulele"))
            assertEquals(if (nb) listOf("Høy G", "Lav G") else listOf("High G", "Low G"), said("tuning", "high-g"))
            pick("instrument", "mandolin")
            assertEquals(listOf("Standard"), said("tuning", "standard"))
        }
    }

    private fun key(code: Int) {
        instrumentation.sendKeyDownUpSync(code)
        rule.waitForIdle()
    }

    /**
     * The tag of the element with the keyboard's focus, or null. With a dialog open, the screen under it
     * still has its own focused element; the dialog's window is the later one, and it has the keys.
     */
    private fun focusedTag(): String? = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true))
        .fetchSemanticsNodes().lastOrNull()?.config?.getOrNull(SemanticsProperties.TestTag)

    /**
     * Whether the focus ring is drawn on the element: the focus colour on its left edge, inside the gap. Read
     * from a screenshot of the whole screen, so an element in a dialog's window is looked at where it is shown.
     */
    private fun ringed(tag: String, colour: Color): Boolean {
        rule.waitForIdle()
        Thread.sleep(400)
        val node = rule.onNodeWithTag(tag).fetchSemanticsNode()
        val at = node.positionOnScreen
        val x = at.x.toInt() + (4 * rule.activity.resources.displayMetrics.density).toInt() - 1
        val y = at.y.toInt() + node.size.height / 2
        val shot = checkNotNull(instrumentation.uiAutomation.takeScreenshot()) { "no screenshot" }.copy(Bitmap.Config.ARGB_8888, false)
        val want = android.graphics.Color.argb(255, (colour.red * 255 + 0.5f).toInt(), (colour.green * 255 + 0.5f).toInt(), (colour.blue * 255 + 0.5f).toInt())
        return shot.getPixel(x, y) == want
    }

    @Test
    fun theKeyboardReachesEveryRowAndWorksThePickers() {
        language("en-GB")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        getStarted()
        val focus = BrasscribeLightColors.focus
        val rows = listOf("instrument", "strings", "tuning", "hand", "reads").map { "fs-row-$it" }
        assertFalse("no ring before the keyboard is used", ringed(rows[0], focus))
        // Tab reaches Not now, Continue and the five rows, the rows in reading order, and every row gets the
        // ring while it has the focus. (The shared screen layout puts its docked button before the content.)
        val order = mutableListOf<String?>()
        repeat(7) {
            key(KeyEvent.KEYCODE_TAB)
            val at = focusedTag()
            order += at
            if (at in rows) {
                assertTrue("$at: the focus ring is drawn", ringed(at!!, focus))
                rows.filter { it != at }.forEach { assertFalse("$it: no ring without the focus", ringed(it, focus)) }
            }
        }
        assertEquals(rows, order.filter { it in rows })
        assertEquals(setOf("fs-not-now", "fs-keep") + rows, order.toSet())
        assertEquals("fs-row-reads", order.last())
        shot("your-instrument-focus-light")

        // Back up to Usual tuning. Enter opens its picker with the focus on the chosen tuning.
        repeat(2) { instrumentation.sendKeySync(KeyEvent(0, 0, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_TAB, 0, KeyEvent.META_SHIFT_ON)); instrumentation.sendKeySync(KeyEvent(0, 0, KeyEvent.ACTION_UP, KeyEvent.KEYCODE_TAB, 0, KeyEvent.META_SHIFT_ON)) }
        rule.waitForIdle()
        assertEquals("fs-row-tuning", focusedTag())
        key(KeyEvent.KEYCODE_ENTER)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-standard").fetchSemanticsNodes().isNotEmpty() }
        rule.waitUntil(5_000) { focusedTag() == "fs-tuning-standard" }
        assertTrue("the chosen tuning has the ring", ringed("fs-tuning-standard", focus))
        // The arrows move through the group, one choice at a time, both ways.
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        assertEquals("fs-tuning-eb-standard", focusedTag())
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        assertEquals("fs-tuning-drop-d", focusedTag())
        assertTrue("the ring follows the arrows", ringed("fs-tuning-drop-d", focus))
        shot("your-instrument-tuning-focus-light")
        key(KeyEvent.KEYCODE_DPAD_UP)
        assertEquals("fs-tuning-c-standard", focusedTag())
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        // Moving chooses nothing; Enter does, and the focus is back on the row, which says the new answer.
        rule.onNodeWithTag("fs-tuning-standard").assertIsSelected()
        key(KeyEvent.KEYCODE_ENTER)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-drop-d").fetchSemanticsNodes().isEmpty() }
        row("tuning").assertContentDescriptionEquals("Usual tuning, Drop D")
        rule.waitUntil(5_000) { focusedTag() == "fs-row-tuning" }

        // Space opens it too, and Escape closes it with nothing changed.
        key(KeyEvent.KEYCODE_SPACE)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-drop-d").fetchSemanticsNodes().isNotEmpty() }
        rule.waitUntil(5_000) { focusedTag() == "fs-tuning-drop-d" }
        key(KeyEvent.KEYCODE_DPAD_UP)
        key(KeyEvent.KEYCODE_ESCAPE)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-drop-d").fetchSemanticsNodes().isEmpty() }
        row("tuning").assertContentDescriptionEquals("Usual tuning, Drop D")
        rule.waitUntil(5_000) { focusedTag() == "fs-row-tuning" }
        // So does Back; and Space chooses in the group as Enter does.
        key(KeyEvent.KEYCODE_ENTER)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-drop-d").fetchSemanticsNodes().isNotEmpty() }
        key(KeyEvent.KEYCODE_BACK)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-drop-d").fetchSemanticsNodes().isEmpty() }
        row("tuning").assertContentDescriptionEquals("Usual tuning, Drop D")
        assertEquals(listOf(Screen.WHAT_DO_YOU_PLAY), vm.screen.value)
        rule.waitUntil(5_000) { focusedTag() == "fs-row-tuning" }
        key(KeyEvent.KEYCODE_SPACE)
        rule.waitUntil(5_000) { focusedTag() == "fs-tuning-drop-d" }
        repeat(3) { key(KeyEvent.KEYCODE_DPAD_DOWN) }
        assertEquals("fs-tuning-dadgad", focusedTag())
        key(KeyEvent.KEYCODE_SPACE)
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-tuning-dadgad").fetchSemanticsNodes().isEmpty() }
        row("tuning").assertContentDescriptionEquals("Usual tuning, D, A, D, G, A, D")
        // Nothing is stored by any of it until Continue, which the keyboard reaches and presses.
        assertEquals(YourInstrument.DEFAULT, store.load())
        var tabs = 0
        while (focusedTag() != "fs-keep" && tabs++ < 8) key(KeyEvent.KEYCODE_TAB)
        assertEquals("fs-keep", focusedTag())
        key(KeyEvent.KEYCODE_ENTER)
        rule.waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME) }
        assertEquals(YourInstrument(tuning = "dadgad"), store.load())
    }

    @Test
    fun notNowKeepsTheDefaultsAndIsNotAskedAgain() {
        language("en-GB")
        getStarted()
        // Choices made and then skipped are not kept.
        pick("strings", "guitar-7")
        rule.onNodeWithTag("fs-not-now").performClick()
        rule.waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME) }
        assertTrue(container.firstRunDone)
        assertEquals(YourInstrument.DEFAULT, store.load())
        assertEquals(TabJobOptions("guitar-6", "standard", "tab"), store.load().jobOptions())
        // Brasscribe's own answer is left as it was.
        assertEquals(SeatChoice.NotSet, container.seat)
    }

    @Test
    fun continueKeepsTheAnswerAndSettingsShowsAndChangesIt() {
        language("en-GB")
        getStarted()
        pick("instrument", "bass")
        pick("tuning", "drop-d")
        row("tuning").assertContentDescriptionEquals("Usual tuning, Drop D")
        // Five strings have no Drop D: the tuning goes back to standard, and says so on its row.
        pick("strings", "bass-5")
        row("strings").assertContentDescriptionEquals("Strings, 5 strings")
        row("tuning").assertContentDescriptionEquals("Usual tuning, Standard")
        pick("tuning", "drop-a")
        pick("hand", "right-upside-down")
        pick("reads", "tab-and-notation")
        // Nothing is kept until Continue.
        assertEquals(YourInstrument.DEFAULT, store.load())
        rule.onNodeWithTag("fs-keep").performClick()
        rule.waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME) }
        val chosen = YourInstrument(FrettedInstrument.BASS_5, "drop-a", FrettingHand.RIGHT_UPSIDE_DOWN, Reads.TAB_AND_NOTATION)
        assertEquals(chosen, store.load())
        assertTrue(container.firstRunDone)

        // Settings shows it on its row, and the row opens the same screen with Save and a way back.
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("setting-seat").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("5-string bass · Drop A · Tab and notation").assertIsDisplayed()
        // The row is named as the screen it opens, and the band's sound choice is not offered.
        rule.onNodeWithTag("setting-seat").assert(hasText("Your instrument"))
        assertTrue(rule.onAllNodesWithText("Realistic").fetchSemanticsNodes().isEmpty())
        assertTrue(rule.onAllNodesWithText("Sound", ignoreCase = true).fetchSemanticsNodes().isEmpty())
        shot("settings-light")
        rule.onNodeWithTag("setting-seat").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(rule.onAllNodesWithTag("fs-not-now").fetchSemanticsNodes().isEmpty())
        // Inside Settings the screen doesn't point to Settings.
        rule.onNodeWithText("Fretscribe remembers this for your tabs.").assertIsDisplayed()
        assertTrue(rule.onAllNodesWithText("Settings", substring = true).fetchSemanticsNodes().none { n ->
            n.config.getOrNull(SemanticsProperties.Text)?.any { it.text.contains("change it in Settings") } == true
        })
        shot("your-instrument-settings-light")
        rule.onNodeWithTag("fs-keep").assert(hasText("Save"))
        row("hand").assertContentDescriptionEquals(
            "Which hand is on the neck?, Right hand on the neck (instrument upside down), Tab looks the same either way.")
        // Back without Save changes nothing.
        pick("reads", "notation")
        rule.runOnUiThread { vm.back() }
        rule.waitUntil(5_000) { vm.screen.value.last() == Screen.SETTINGS }
        assertEquals(chosen, store.load())
        // Save keeps it and goes back to Settings.
        rule.onNodeWithTag("setting-seat").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
        pick("reads", "notation")
        rule.onNodeWithTag("fs-keep").performClick()
        rule.waitUntil(5_000) { vm.screen.value.last() == Screen.SETTINGS }
        assertEquals(chosen.copy(reads = Reads.NOTATION), store.load())
        rule.onNodeWithText("5-string bass · Drop A · Notation").assertIsDisplayed()
        // The row names the other instruments as they are.
        for ((mine, value) in listOf(
            YourInstrument(FrettedInstrument.GUITAR_7, "eb-standard") to "7-string guitar · E-flat standard (half a step down) · Tab",
            YourInstrument(FrettedInstrument.UKULELE, "low-g") to "Ukulele · Low G · Tab",
            YourInstrument(FrettedInstrument.UKULELE_BARITONE) to "Baritone ukulele · Standard · Tab",
            YourInstrument(FrettedInstrument.MANDOLIN, reads = Reads.TAB_AND_NOTATION) to "Mandolin · Standard · Tab and notation",
        )) {
            store.save(mine)
            // (Settings reads the answer when it is opened.)
            rule.runOnUiThread { vm.home() }
            rule.waitForIdle()
            rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
            rule.waitUntil(5_000) { rule.onAllNodesWithText(value).fetchSemanticsNodes().isNotEmpty() }
        }
    }

    @Test
    fun aBassChosenInTheVersionThatOfferedOnlyTheBassIsStillThatBass() {
        language("en-GB")
        // What that version stored.
        rule.activity.getSharedPreferences(AppearanceStore.PREFS, Context.MODE_PRIVATE).edit()
            .putString("fret_instrument", "bass").putString("fret_strings", "5").putString("fret_tuning", "drop-a")
            .putString("fret_hand", "right").putString("fret_reads", "notation").commit()
        assertEquals(YourInstrument(FrettedInstrument.BASS_5, "drop-a", FrettingHand.RIGHT, Reads.NOTATION), store.load())
        rule.runOnUiThread { container.firstRunDone = true; vm.home(); vm.navigate(Screen.SETTINGS) }
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("setting-seat").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("5-string bass · Drop A · Notation").assertIsDisplayed()
        rule.onNodeWithTag("setting-seat").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
        row("instrument").assertContentDescriptionEquals("Instrument, Bass")
        row("strings").assertContentDescriptionEquals("Strings, 5 strings")
        row("tuning").assertContentDescriptionEquals("Usual tuning, Drop A")
        row("reads").assertContentDescriptionEquals("You read, Notation")
    }

    @Test
    fun choicesLeftWithoutSaveAreGoneAfterTheAppIsRestored() {
        val words = mapOf(
            "en-GB" to listOf("You read, Notation", "Usual tuning, Standard", "You read, Tab", "Usual tuning, Drop A", "Strings, 5 strings"),
            "nb-NO" to listOf("Du leser, Noter", "Vanlig stemming, Standard", "Du leser, Tab", "Vanlig stemming, Drop A", "Strenger, 5 strenger"),
        )
        for ((lang, w) in words) {
            language(lang)
            val stored = YourInstrument(FrettedInstrument.BASS_5, tuning = "drop-a")
            store.save(stored)
            rule.runOnUiThread { vm.home(); vm.navigate(Screen.SETTINGS); vm.openSeatPicker(SeatPickerMode.SETTINGS) }
            rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
            pick("reads", "notation")
            pick("tuning", "standard")
            // Restored in the middle of choosing (the activity is destroyed and made again from its saved
            // state): the choices are still there, and still not stored.
            rule.activityRule.scenario.recreate()
            rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
            row("reads").assertContentDescriptionEquals(w[0])
            row("tuning").assertContentDescriptionEquals(w[1])
            assertEquals(stored, store.load())
            // The app is stopped with the choices on screen, and comes back on Settings (as after the process
            // was killed, when the screens come back from what was saved but not always to the same one): the
            // state saved for this visit must not be picked up by the next. Back and the restore are asked for
            // together, so the state is saved while the screen is still composed.
            rule.runOnUiThread { vm.back(); rule.activity.recreate() }
            rule.waitForIdle()
            rule.waitUntil(5_000) { rule.onAllNodesWithTag("setting-seat").fetchSemanticsNodes().isNotEmpty() }
            // The row opens on what is stored, and Save stores that.
            rule.onNodeWithTag("setting-seat").performClick()
            rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
            row("reads").assertContentDescriptionEquals(w[2])
            row("tuning").assertContentDescriptionEquals(w[3])
            row("strings").assertContentDescriptionEquals(w[4])
            rule.onNodeWithTag("fs-keep").performClick()
            rule.waitUntil(5_000) { vm.screen.value.last() == Screen.SETTINGS }
            assertEquals(stored, store.load())
        }
    }

    @Test
    fun at200PercentTextNothingIsClipped() {
        for (lang in listOf("en-GB", "nb-NO")) {
            language(lang)
            shell("settings put system font_scale 2.0")
            rule.waitUntil(10_000) { rule.activity.resources.configuration.fontScale >= 1.9f }
            getStarted()
            assertNoTextIsClipped()
            listOf("instrument", "strings", "tuning", "hand", "reads").forEach { tag ->
                row(tag).performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
            }
            rule.onNodeWithTag("fs-keep").assertIsDisplayed()
            rule.onNodeWithTag("fs-not-now").assertIsDisplayed()
            row("instrument").performScrollTo()
            shot("your-instrument-200-${lang.take(2)}")
            // The longest list, in a dialog: every choice can be reached and none is cut off.
            open("tuning", "open-e")
            assertNoTextIsClipped()
            listOf("standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e").forEach {
                rule.onNodeWithTag("fs-tuning-$it").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
            }
            shot("your-instrument-200-tuning-${lang.take(2)}")
            closePicker()
            // The ukulele's size is the longest answer on a row.
            pick("instrument", "ukulele")
            assertNoTextIsClipped()
            row("strings").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
            shot("your-instrument-200-ukulele-${lang.take(2)}")
            shell("settings put system font_scale 1.0")
            rule.waitUntil(10_000) { rule.activity.resources.configuration.fontScale <= 1.1f }
        }
    }

    @Test
    fun screenshotsOfTheFirstRunYourInstrumentAndHomeLightAndDark() {
        for (lang in listOf("en-GB", "nb-NO")) {
            language(lang)
            for (appearance in listOf(Appearance.LIGHT, Appearance.DARK)) {
                rule.runOnUiThread { container.updateAppearance(appearance) }
                val tag = "${lang.take(2)}-${appearance.key}"
                forget()
                firstRun()
                // Fretscribe's words: tab, and nothing about a band.
                val shown = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text)).fetchSemanticsNodes()
                    .flatMap { it.config[SemanticsProperties.Text] }.joinToString(" ") { it.text }
                assertTrue(shown, shown.contains("Fretscribe") && shown.contains(if (lang == "en-GB") "Tab from any recording." else "Tab fra et hvilket som helst opptak."))
                assertFalse(shown, BRASSCRIBE_WORDS.containsMatchIn(shown))
                // The first run is a brand moment: the tinted band with the mark in blue ink, on Fretscribe's paper.
                val colours = if (appearance == Appearance.DARK) BrasscribeDarkColors else BrasscribeLightColors
                val first = shot("first-run-$tag")
                val all = first.width * first.height
                assertTrue("$tag: the first run is on Fretscribe's paper", first.count(colours.bg) > all / 3)
                assertTrue("$tag: the band is the brand tint", first.count(colours.brassTint) > all / 10)
                assertTrue("$tag: the mark is in blue ink", first.count(colours.brass) > 200)
                rule.onNodeWithText(text(R.string.first_run_start)).performClick()
                rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
                // Your instrument: paper, the rows on the raised surface, and one primary button in ink.
                val yours = shot("your-instrument-$tag")
                assertTrue("$tag: Your instrument is on Fretscribe's paper", yours.count(colours.bg) > all / 3)
                assertTrue("$tag: the rows are a raised group", yours.count(colours.surfaceRaised) > all / 10)
                assertTrue("$tag: the primary button is ink", yours.count(colours.primary) > all / 50)
                assertEquals("$tag: no brand colour outside brand moments", 0, yours.count(colours.brass))
                open("tuning", "standard")
                shot("your-instrument-tuning-$tag")
                closePicker()
                open("instrument", "guitar")
                shot("your-instrument-instruments-$tag")
                closePicker()
                pick("instrument", "ukulele")
                shot("your-instrument-ukulele-$tag")
                pick("instrument", "guitar")
                rule.onNodeWithTag("fs-keep").performClick()
                rule.waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME) }
                val home = rule.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text)).fetchSemanticsNodes()
                    .flatMap { it.config[SemanticsProperties.Text] }.joinToString(" ") { it.text }
                assertFalse(home, BRASSCRIBE_WORDS.containsMatchIn(home))
                shot("home-$tag")
            }
        }
    }

    private companion object {
        const val PACKAGE = "no.fretscribe.play"

        /** Words of Brasscribe's that Fretscribe's first run and Home don't use, as whole words ("MuseScore" is fine). */
        val BRASSCRIBE_WORDS = Regex("""\b(Brasscribe|bands?|scores?|parts?|brass|partitur\w*|stemme\w*|bandet|korps\w*)\b""", RegexOption.IGNORE_CASE)
    }
}
