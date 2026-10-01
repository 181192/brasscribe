package no.brasscribe.play.fret

import android.content.Context
import android.graphics.Bitmap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
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
 * radio choices in the pickers, 48 dp targets, 200 % text, Not now, and the way in from Settings.
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
        listOf(YourInstrumentStore.INSTRUMENT, YourInstrumentStore.STRINGS, YourInstrumentStore.TUNING, YourInstrumentStore.HAND, YourInstrumentStore.READS)
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
            "en-GB" to listOf("Your instrument", "Instrument, Bass", "Strings, 4 strings", "Usual tuning, Standard",
                "Which hand frets?, Left hand (most players), Tab looks the same either way. Chord boxes and the fretboard turn round.",
                "You read, Tab", "Not now", "Continue", "Guitar, Later"),
            "nb-NO" to listOf("Instrumentet ditt", "Instrument, Bass", "Strenger, 4 strenger", "Vanlig stemming, Standard",
                "Hvilken hånd tar grepene?, Venstre hånd (de fleste), Tabben ser lik ut uansett. Akkordbokser og gripebrettet snus.",
                "Du leser, Tab", "Ikke nå", "Fortsett", "Gitar, Senere"),
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
            }
            rule.onNodeWithTag("fs-not-now").assertIsDisplayed().assert(hasText(w[6]))
                .assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp)
            rule.onNodeWithTag("fs-keep").assertIsDisplayed().assert(hasText(w[7])).assertHeightIsAtLeast(48.dp)
            // The instruments that can't be chosen yet say so, in words.
            open("instrument", "guitar")
            rule.onNodeWithTag("fs-instrument-guitar").assertContentDescriptionEquals(w[8]).assertIsNotEnabled()
            closePicker()
        }
    }

    @Test
    fun thePickersAreRadioGroupsWithFullSizeTargets() {
        language("en-GB")
        getStarted()
        val options = mapOf(
            "instrument" to listOf("bass", "guitar", "ukulele", "mandolin"),
            "strings" to listOf("4", "5", "6"),
            "tuning" to listOf("standard", "eb-standard", "d-standard", "drop-d", "bead"),
            "hand" to listOf("left", "right", "right-upside-down"),
            "reads" to listOf("tab", "tab-and-notation", "notation"),
        )
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
            ids.forEach { rule.onNodeWithTag("fs-$tag-$it").performScrollTo().assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp) }
            closePicker()
        }
        // Only the bass can be chosen; the others are there, and off.
        open("instrument", "bass")
        rule.onNodeWithTag("fs-instrument-bass").assertIsEnabled().assertIsSelected()
        listOf("guitar", "ukulele", "mandolin").forEach { rule.onNodeWithTag("fs-instrument-$it").assertIsNotEnabled().assertIsNotSelected() }
        closePicker()
        // E♭ is spoken as "E flat".
        open("tuning", "eb-standard")
        rule.onNodeWithTag("fs-tuning-eb-standard").assertContentDescriptionEquals("E flat standard (half a step down)")
        closePicker()
    }

    @Test
    fun notNowKeepsTheDefaultsAndIsNotAskedAgain() {
        language("en-GB")
        getStarted()
        // Choices made and then skipped are not kept.
        pick("strings", "5")
        rule.onNodeWithTag("fs-not-now").performClick()
        rule.waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME) }
        assertTrue(container.firstRunDone)
        assertEquals(YourInstrument.DEFAULT, store.load())
        assertEquals(TabJobOptions("bass-4", "standard", "tab"), store.load().jobOptions())
        // Brasscribe's own answer is left as it was.
        assertEquals(SeatChoice.NotSet, container.seat)
    }

    @Test
    fun continueKeepsTheAnswerAndSettingsShowsAndChangesIt() {
        language("en-GB")
        getStarted()
        pick("tuning", "drop-d")
        row("tuning").assertContentDescriptionEquals("Usual tuning, Drop D")
        // Five strings have no Drop D: the tuning goes back to standard, and says so on its row.
        pick("strings", "5")
        row("strings").assertContentDescriptionEquals("Strings, 5 strings")
        row("tuning").assertContentDescriptionEquals("Usual tuning, Standard")
        pick("tuning", "drop-a")
        pick("hand", "right-upside-down")
        pick("reads", "tab-and-notation")
        // Nothing is kept until Continue.
        assertEquals(YourInstrument.DEFAULT, store.load())
        rule.onNodeWithTag("fs-keep").performClick()
        rule.waitUntil(5_000) { vm.screen.value == listOf(Screen.HOME) }
        val chosen = YourInstrument(Instrument.BASS, 5, "drop-a", FrettingHand.RIGHT_UPSIDE_DOWN, Reads.TAB_AND_NOTATION)
        assertEquals(chosen, store.load())
        assertTrue(container.firstRunDone)

        // Settings shows it on its row, and the row opens the same screen with Save and a way back.
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS) }
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("setting-seat").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("5-string bass · Drop A · Tab and notation").assertIsDisplayed()
        shot("settings-light")
        rule.onNodeWithTag("setting-seat").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("fs-keep").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(rule.onAllNodesWithTag("fs-not-now").fetchSemanticsNodes().isEmpty())
        rule.onNodeWithTag("fs-keep").assert(hasText("Save"))
        row("hand").assertContentDescriptionEquals(
            "Which hand frets?, Right hand, instrument upside down, Tab looks the same either way. Chord boxes and the fretboard turn round.")
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
            open("tuning", "bead")
            assertNoTextIsClipped()
            listOf("standard", "eb-standard", "d-standard", "drop-d", "bead").forEach {
                rule.onNodeWithTag("fs-tuning-$it").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
            }
            shot("your-instrument-200-tuning-${lang.take(2)}")
            closePicker()
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
                assertTrue(shown, shown.contains("Fretscribe") && shown.contains(if (lang == "en-GB") "Tab from any recording." else "Tab fra hvilket som helst opptak."))
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
