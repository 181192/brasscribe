package no.brasscribe.play.fret

import android.net.Uri
import android.view.KeyEvent
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
import androidx.compose.ui.test.assertIsNotSelected
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.Appearance
import no.brasscribe.play.MainActivity
import no.brasscribe.play.PlayApplication
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.Product
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.engine.Octave
import no.brasscribe.play.engine.Recording
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A guitar's and a ukulele's recording become tabs, on a fixture computer that answers as the engine did
 * for a short take of each (apps/fixtures/guitar-line and ukulele-line):
 * What is this? for each instrument, the job that is sent, Check the song with the capo and what was left
 * out, and the song's line in Your songs. In English and bokmål, with the accessibility checks on every
 * action, at 200 % text, and the capo's picker with the keyboard.
 */
@RunWith(AndroidJUnit4::class)
class SendGuitarAndUkuleleTabFlowTest : ScreenTest() {
    private val store get() = yourInstrumentStore(rule.activity)

    override val shots = "fretscribe/guitar-flow"

    @Before
    fun setUp() {
        assertEquals("Fretscribe", Product.NAME)
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
    }

    @After
    fun tearDown() {
        store.save(YourInstrument.DEFAULT)
    }

    /**
     * The computer of the tests: what the engine answered for [take], with [tab] changed on the way when given.
     * [older]: a computer whose Fretscribe is from before the tab profile; it has the bass tab's id only.
     */
    private fun computer(take: String, older: Boolean = false, profiles: (() -> ByteArray?)? = null, tab: ((JSONObject) -> Unit)? = null) {
        // (Another computer than the one before: the app lets go of that one first.)
        container.fixtureSource = null
        container.engine()
        container.fixtureSource = FixtureSource { name ->
            // [profiles]: the computer's answer to which profiles it has, when a test makes it slow or makes it fail.
            if (name == FixtureEngineApi.PROFILES_FILE) return@FixtureSource if (profiles != null) profiles() else if (older) OLDER.toByteArray() else null
            val bytes = ScreenDevice.fixture("$take/$name")
            if (name == "tab.json" && bytes != null && tab != null) JSONObject(String(bytes)).also(tab).toString().toByteArray() else bytes
        }
    }

    /** Open a recording from Home, as the file picker's answer does: What is this? follows. */
    private fun openARecording(name: String = "Riff.wav", answered: Boolean = true) {
        val file = recording(name)
        rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(file)) }
        waitUntil(20_000) { rule.onAllNodesWithTag("fs-what-continue").fetchSemanticsNodes().isNotEmpty() }
        // (The computer is asked what it can write when the screen opens; Continue waits for its answer.)
        if (answered) waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
    }

    private fun card(tag: String) = rule.onNode(
        SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            androidx.compose.ui.test.hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-$tag")),
    )

    /** The element with the keyboard's focus: its tag, and what it says. With a dialog open it is the dialog's. */
    private fun focused() = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true)).fetchSemanticsNodes().lastOrNull()?.config
    private fun focusedTag(): String? = focused()?.getOrNull(SemanticsProperties.TestTag)

    /** The job the computer was last asked for, and the options the app made it with. */
    private fun lastJob() = runBlocking { container.engine()!!.job(vm.result.value!!.jobId!!) }
    private fun sent() = tabOptions(store.load(), SongAnswers.of(vm.source.value))

    @Test
    fun aGuitarInASongBecomesATabInEnglishAndBokmal() {
        val words = mapOf(
            "en-GB" to listOf("A band or a record. Fretscribe picks out the guitar.", "One instrument playing, with nothing else.", "Picking out your instrument",
                "Tuning: Sounds like Drop D. Written for Standard.", "Capo: Capo on fret 2. Changing the capo changes the frets. The notes stay the same.", "Change the capo",
                "Notes left out: 3 notes left out. They can't be played together with the rest.",
                "Notes added: 2 notes added to complete a chord. They are marked ?.", "You can change this later.", "6-string guitar · Standard", "Use Drop D"),
            "nb-NO" to listOf("Et band eller en plate. Fretscribe plukker ut gitaren.", "Ett instrument som spiller, uten noe annet.", "Plukker ut instrumentet ditt",
                "Stemming: Høres ut som Drop D. Skrevet for Standard.", "Capo: Capo på bånd 2. Endrer du capo, endres båndene. Tonene er de samme.", "Endre capo",
                "Utelatte toner: 3 toner er utelatt. De kan ikke spilles sammen med resten.",
                "Toner lagt til: 2 toner er lagt til for å fullføre en akkord. De er merket ?.", "Du kan endre dette senere.", "6-strengs gitar · Standard", "Bruk Drop D"),
        )
        store.save(YourInstrument(FrettedInstrument.GUITAR_6))
        for ((lang, w) in words) {
            language(lang)
            // As the computer answered for the guitar take, as if it had been written for a capo on the second fret,
            // with three notes left out and two added.
            computer("guitar-line") { tab ->
                tab.getJSONObject("instrument").put("capo", 2)
                tab.put("unplayable_dropped", 3).put("inferred_notes", 2)
            }
            openARecording()

            // What is this? Nothing is chosen for a guitar, and A full song says which instrument is picked out.
            val alone = card("instrument").assert(hasText(w[1])).assertIsNotSelected()
            val song = card("song").assert(hasText(w[0])).assertIsNotSelected().assertHeightIsAtLeast(48.dp)
            rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
            assertFalse(shown(), Regex("bass|guitar is playing|gitar spiller", RegexOption.IGNORE_CASE).containsMatchIn(shown()))
            checkAccessibility()
            shot("guitar-what-is-this-${lang.take(2)}-light")
            song.performClick()
            song.assertIsSelected()
            alone.assertIsNotSelected()
            rule.onNodeWithTag("fs-what-continue").assertIsEnabled().performClick()

            // A song is separated first: the step names the player's instrument, never the bass.
            waitUntil(20_000) { shown().contains(w[2]) }
            assertFalse(shown(), Regex("\\bbass", RegexOption.IGNORE_CASE).containsMatchIn(shown()))

            // Check the song: the tuning that fits, the capo, and what was left out and added, each one element.
            waitForTag("fs-show-tab")
            waitForTag("fs-check-capo", 10_000)
            rule.onNodeWithTag("fs-check-tuning").assertContentDescriptionEquals(w[3])
            rule.onNodeWithTag("fs-check-change-tuning").assert(hasText(w[10])).assertHeightIsAtLeast(48.dp)
            rule.onNodeWithTag("fs-check-capo").performScrollTo().assertContentDescriptionEquals(w[4])
            rule.onNodeWithTag("fs-check-change-capo").performScrollTo().assert(hasText(w[5])).assertHeightIsAtLeast(48.dp)
            rule.onNodeWithTag("fs-check-left-out").performScrollTo().assertContentDescriptionEquals(w[6])
            rule.onNodeWithTag("fs-check-added").performScrollTo().assertContentDescriptionEquals(w[7])
            rule.onNodeWithText(w[8]).assertIsDisplayed()
            checkAccessibility()
            rule.onNodeWithTag("fs-check-tuning").performScrollTo()
            shot("guitar-check-the-song-${lang.take(2)}-light")
            rule.onNodeWithTag("fs-check-added").performScrollTo()
            shot("guitar-check-the-song-left-out-${lang.take(2)}-light")

            // What was sent: a tab job for the six-string guitar, the song separated, no capo, and no chords asked for.
            val sent = sent()
            assertEquals(listOf(FrettedInstrument.GUITAR_6, "standard", 0, Octave.AUTO, Recording.SONG, null),
                listOf(sent.instrument, sent.tuning, sent.capo, sent.octave, sent.recording, sent.chords))
            val job = lastJob()
            assertEquals("tab", job.profile)
            assertEquals(listOf("beats", "stems", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes", "arrange", "export"), job.stages.map { it.name })

            // Show the tab, and the song is in Your songs with its instrument and tuning.
            rule.onNodeWithTag("fs-show-tab").performClick()
            waitForTag("fs-tab", 30_000)
            waitUntil(30_000) {
                rule.onNodeWithTag("fs-tab").fetchSemanticsNode().config.getOrNull(SemanticsProperties.ContentDescription)
                    ?.firstOrNull()?.let { d -> Regex("""\d+""").findAll(d).any { it.value.toInt() > 1 } } == true
            }
            if (lang == "en-GB") shot("guitar-the-tab-en-light")
            rule.runOnUiThread { vm.home() }
            waitUntil(10_000) { rule.onAllNodesWithText(w[9], substring = true).fetchSemanticsNodes().isNotEmpty() }
            rule.onAllNodesWithText(w[9], substring = true).onFirst().performScrollTo().assertIsDisplayed()
            if (lang == "en-GB") shot("guitar-home-song-en-light")
            rule.runOnUiThread { vm.scores.value.forEach(vm::deleteEntry) }
        }
    }

    @Test
    fun theCapoIsChosenOnCheckTheSongAndTheSongIsWrittenDownAgainForIt() {
        language("en-GB")
        store.save(YourInstrument(FrettedInstrument.GUITAR_6))
        computer("guitar-line")
        openARecording()
        card("instrument").performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-check-change-capo")
        rule.onNodeWithTag("fs-check-capo").performScrollTo().assertContentDescriptionEquals("Capo: No capo. Changing the capo changes the frets. The notes stay the same.")
        // The guitar alone is not separated, and a first job never has a capo.
        assertEquals(listOf("beats", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes", "arrange", "export"), lastJob().stages.map { it.name })
        assertEquals(0, sent().capo)

        // The keyboard reaches the button; Enter opens the choices with the focus on the one the tab has.
        var tabs = 0
        while (!focusedWords().contains("Change the capo") && tabs++ < 12) key(KeyEvent.KEYCODE_TAB)
        assertTrue("the keyboard reaches Change the capo: ${focusedWords()}", focusedWords().contains("Change the capo"))
        key(KeyEvent.KEYCODE_ENTER)
        waitForTag("fs-check-capo-0", 5_000)
        waitUntil(5_000) { focusedTag() == "fs-check-capo-0" }
        // One radio group: no capo and the twelve frets, each named in words and a full-size target; exactly one is chosen.
        val radios = rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).fetchSemanticsNodes()
            .filter { it.config.getOrNull(SemanticsProperties.TestTag)?.startsWith("fs-check-capo-") == true }
        assertEquals((0..12).map { "fs-check-capo-$it" }, radios.map { it.config.getOrNull(SemanticsProperties.TestTag) })
        assertEquals(listOf("No capo") + (1..12).map { "Capo on fret $it" }, radios.map { it.config.getOrNull(SemanticsProperties.ContentDescription)?.single() })
        assertEquals(1, radios.map { it.parent?.id }.distinct().size)
        assertTrue(radios.first().parent?.config?.contains(SemanticsProperties.SelectableGroup) == true)
        assertEquals(listOf("fs-check-capo-0"), radios.filter { it.config.getOrNull(SemanticsProperties.Selected) == true }.map { it.config.getOrNull(SemanticsProperties.TestTag) })
        (0..12).forEach { rule.onNodeWithTag("fs-check-capo-$it").performScrollTo().assertHeightIsAtLeast(48.dp).assertWidthIsAtLeast(48.dp) }
        rule.onNodeWithTag("fs-check-capo-0").performScrollTo()
        checkAccessibility()
        shot("guitar-capo-picker-en-light")
        // The arrows move without choosing, and Escape closes it with nothing written down again and the focus back on the button.
        val first = vm.result.value!!.jobId
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        assertEquals("fs-check-capo-2", focusedTag())
        key(KeyEvent.KEYCODE_ESCAPE)
        waitUntil(5_000) { rule.onAllNodesWithTag("fs-check-capo-0").fetchSemanticsNodes().isEmpty() }
        waitUntil(5_000) { focusedWords().contains("Change the capo") }
        assertEquals(first, vm.result.value!!.jobId)
        assertEquals(1, runBlocking { container.engine()!!.jobs() }.size)
        // Choosing the one the tab already has changes nothing either.
        rule.onNodeWithTag("fs-check-change-capo").performClick()
        waitForTag("fs-check-capo-0", 5_000)
        rule.onNodeWithTag("fs-check-capo-0").performClick()
        waitUntil(5_000) { rule.onAllNodesWithTag("fs-check-capo-0").fetchSemanticsNodes().isEmpty() }
        assertEquals(1, runBlocking { container.engine()!!.jobs() }.size)

        // The second fret: the recording is written down again for it, and Check the song comes back.
        rule.onNodeWithTag("fs-check-change-capo").performClick()
        waitForTag("fs-check-capo-2", 5_000)
        rule.onNodeWithTag("fs-check-capo-2").performScrollTo().performClick()
        waitUntil(60_000) { vm.result.value?.jobId != first && vm.screen.value == listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT) }
        waitForTag("fs-show-tab")
        val sent = sent()
        assertEquals(listOf(FrettedInstrument.GUITAR_6, "standard", 2, Recording.INSTRUMENT, Octave.AUTO), listOf(sent.instrument, sent.tuning, sent.capo, sent.recording, sent.octave))
        assertNull(sent.chords)
        assertEquals(2, runBlocking { container.engine()!!.jobs() }.size)
        assertEquals("tab", lastJob().profile)
        // The capo is this song's: the player's instrument is as it was.
        assertEquals(YourInstrument(FrettedInstrument.GUITAR_6), store.load())
    }

    @Test
    fun aUkuleleStartsOnItsOwnAndAFullSongSaysWhenItWorksInEnglishAndBokmal() {
        val words = mapOf(
            "en-GB" to listOf("A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a ukulele from a guitar.",
                "Tuning: High G", "Capo: No capo. Changing the capo changes the frets. The notes stay the same.", "Ukulele · High G", "Continue"),
            "nb-NO" to listOf("Et band eller en plate. Dette virker bare når ingen gitar spiller: i en sang kan ikke Fretscribe skille en ukulele fra en gitar.",
                "Stemming: Høy G", "Capo: Ingen capo. Endrer du capo, endres båndene. Tonene er de samme.", "Ukulele · Høy G", "Fortsett"),
        )
        store.save(YourInstrument(FrettedInstrument.UKULELE))
        for ((lang, w) in words) {
            language(lang)
            computer("ukulele-line")
            openARecording("Uke.wav")

            // What is this? starts on the instrument alone, as the computer takes a ukulele, and Continue is ready.
            val alone = card("instrument").assertIsSelected()
            // The warning is part of the choice it is about: read with it, and shown whole.
            val song = card("song").assert(hasText(w[0])).assertIsNotSelected().assertIsDisplayed()
            assertEquals(2, rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).fetchSemanticsNodes().size)
            rule.onNodeWithTag("fs-what-continue").assert(hasText(w[4])).assertIsEnabled()
            assertNoTextIsClipped()
            checkAccessibility()
            shot("ukulele-what-is-this-${lang.take(2)}-light")

            // English sends a full song, bokmål what it started on.
            val whole = lang == "en-GB"
            if (whole) {
                song.performClick()
                song.assertIsSelected()
                alone.assertIsNotSelected()
                shot("ukulele-what-is-this-song-en-light")
                rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
                shot("ukulele-what-is-this-song-en-dark")
                rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
            }
            rule.onNodeWithTag("fs-what-continue").performClick()

            waitForTag("fs-show-tab")
            waitForTag("fs-check-capo", 10_000)
            rule.onNodeWithTag("fs-check-tuning").assertContentDescriptionEquals(w[1])
            rule.onNodeWithTag("fs-check-capo").performScrollTo().assertContentDescriptionEquals(w[2])
            // The take fits its tuning and nothing was left out: no change of tuning is offered, and no row says notes were left out.
            listOf("change-tuning", "left-out", "added").forEach { assertTrue(it, rule.onAllNodesWithTag("fs-check-$it").fetchSemanticsNodes().isEmpty()) }
            checkAccessibility()
            rule.onNodeWithTag("fs-check-tuning").performScrollTo()
            shot("ukulele-check-the-song-${lang.take(2)}-light")

            val sent = sent()
            assertEquals(listOf(FrettedInstrument.UKULELE, "high-g", 0, if (whole) Recording.SONG else Recording.INSTRUMENT, null),
                listOf(sent.instrument, sent.tuning, sent.capo, sent.recording, sent.chords))
            val job = lastJob()
            assertEquals("tab", job.profile)
            assertEquals(whole, job.stages.any { it.name == "stems" })
            assertTrue(job.stages.any { it.name == "transcribe.ukulele.basic-pitch" })
            // The answer stays with this recording: back on What is this?, it is still the one chosen.
            rule.runOnUiThread { vm.back() }
            waitForTag("fs-what-continue", 10_000)
            waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
            card(if (whole) "song" else "instrument").assertIsSelected()
            rule.onNodeWithTag("fs-what-continue").performClick()
            waitForTag("fs-show-tab")

            rule.onNodeWithTag("fs-show-tab").performClick()
            waitForTag("fs-tab", 30_000)
            waitUntil(30_000) {
                rule.onNodeWithTag("fs-tab").fetchSemanticsNode().config.getOrNull(SemanticsProperties.ContentDescription)
                    ?.firstOrNull()?.let { d -> Regex("""\d+""").findAll(d).any { it.value.toInt() > 1 } } == true
            }
            if (whole) shot("ukulele-the-tab-en-light")
            rule.runOnUiThread { vm.home() }
            waitUntil(10_000) { rule.onAllNodesWithText(w[3], substring = true).fetchSemanticsNodes().isNotEmpty() }
            rule.runOnUiThread { vm.scores.value.forEach(vm::deleteEntry) }
        }
    }

    @Test
    fun aMandolinAndABaritoneUkuleleSayTheSameAndABassAndAGuitarDoNot() {
        language("en-GB")
        computer("ukulele-line")
        val warned = mapOf(
            FrettedInstrument.MANDOLIN to "A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a mandolin from a guitar.",
            FrettedInstrument.UKULELE_BARITONE to "A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a ukulele from a guitar.",
        )
        for ((kind, words) in warned) {
            store.save(YourInstrument(kind))
            openARecording("${kind.name}.wav")
            card("instrument").assertIsSelected()
            card("song").assert(hasText(words)).assertIsNotSelected()
            rule.onNodeWithTag("fs-what-continue").assertIsEnabled()
            if (kind == FrettedInstrument.MANDOLIN) shot("mandolin-what-is-this-en-light")
        }
        val picked = mapOf(
            FrettedInstrument.BASS_5 to "A band or a record. Fretscribe picks out the bass.",
            FrettedInstrument.GUITAR_8 to "A band or a record. Fretscribe picks out the guitar.",
        )
        for ((kind, words) in picked) {
            store.save(YourInstrument(kind))
            openARecording("${kind.name}.wav")
            // Nothing is chosen until the player chooses.
            card("instrument").assertIsNotSelected()
            card("song").assert(hasText(words)).assertIsNotSelected()
            rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        }
    }

    @Test
    fun at200PercentTextTheWarningAndTheCapoAreShownWhole() {
        store.save(YourInstrument(FrettedInstrument.UKULELE, "low-g"))
        for (lang in listOf("en-GB", "nb-NO")) {
            language(lang)
            computer("ukulele-line") { tab -> tab.getJSONObject("instrument").put("capo", 12); tab.put("unplayable_dropped", 1).put("inferred_notes", 1) }
            textSize(2.0f)
            openARecording("Uke.wav")
            assertNoTextIsClipped()
            card("instrument").performScrollTo().assertIsDisplayed()
            card("song").performScrollTo().assertIsDisplayed()
            shot("ukulele-what-is-this-200-${lang.take(2)}")
            rule.onNodeWithTag("fs-what-continue").assertIsDisplayed().performClick()
            waitForTag("fs-check-change-capo")
            assertNoTextIsClipped()
            listOf("tuning", "capo", "change-capo", "key", "left-out", "added").forEach {
                rule.onNodeWithTag("fs-check-$it").performScrollTo().assertIsDisplayed()
            }
            rule.onNodeWithTag("fs-show-tab").assertIsDisplayed()
            rule.onNodeWithTag("fs-check-capo").performScrollTo()
            shot("ukulele-check-the-song-200-${lang.take(2)}")
            // The capo's choices at this size: every one can be reached and none is cut off.
            rule.onNodeWithTag("fs-check-change-capo").performScrollTo().performClick()
            waitForTag("fs-check-capo-12", 5_000)
            assertNoTextIsClipped()
            listOf(0, 6, 12).forEach { rule.onNodeWithTag("fs-check-capo-$it").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp) }
            rule.onNodeWithTag("fs-check-capo-12").assertIsSelected()
            shot("ukulele-capo-picker-200-${lang.take(2)}")
            rule.onNodeWithText(rule.activity.getString(no.brasscribe.play.R.string.cancel)).performClick()
            textSize(1.0f)
        }
    }

    @Test
    fun aBassStillBecomesATabOnAComputerFromBeforeTheOtherInstruments() {
        language("en-GB")
        store.save(YourInstrument(FrettedInstrument.BASS_4))
        // The bass line, as if it had been heard an octave up: a change is on offer.
        computer("bass-line", older = true) { tab -> tab.put("octave_shift", -12) }
        openARecording("Bass.wav")
        // Nothing says the computer is too old: for a bass it is not.
        assertFalse(shown(), shown().contains("too old"))
        card("instrument").performClick()
        rule.onNodeWithTag("fs-what-continue").assertIsEnabled().performClick()
        waitForTag("fs-check-change-octave")
        // Sent under the id that computer knows.
        assertEquals("bass-tab", lastJob().profile)
        assertEquals(FrettedInstrument.BASS_4, sent().instrument)
        // And written down again under it.
        val first = vm.result.value!!.jobId
        rule.onNodeWithTag("fs-check-change-octave").performScrollTo().performClick()
        waitUntil(60_000) { vm.result.value?.jobId != first && vm.screen.value == listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT) }
        waitForTag("fs-show-tab")
        assertEquals("bass-tab", lastJob().profile)
        assertEquals(Octave.AS_HEARD, sent().octave)
        assertEquals(listOf("bass-tab", "bass-tab"), runBlocking { container.engine()!!.jobs() }.map { it.profile })
    }

    @Test
    fun onAComputerWithTheTabProfileABassGoesAsATabLikeTheRest() {
        language("en-GB")
        store.save(YourInstrument(FrettedInstrument.BASS_5))
        computer("bass-line")
        openARecording("Bass.wav")
        card("instrument").performClick()
        // (The computer has said what it can write before the job is made.)
        waitUntil(10_000) { ComputerProfiles.listed?.contains("tab") == true }
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        assertEquals("tab", lastJob().profile)
    }

    @Test
    fun aGuitarAUkuleleAndAMandolinAreRefusedBeforeAnythingIsSentToAComputerThatIsTooOld() {
        val words = mapOf(
            "en-GB" to mapOf(
                FrettedInstrument.GUITAR_6 to "Fretscribe on your computer is too old to write guitar tabs. Update it there.",
                FrettedInstrument.UKULELE to "Fretscribe on your computer is too old to write ukulele tabs. Update it there.",
                FrettedInstrument.MANDOLIN to "Fretscribe on your computer is too old to write mandolin tabs. Update it there."),
            "nb-NO" to mapOf(
                FrettedInstrument.GUITAR_6 to "Fretscribe på datamaskinen er for gammel til å skrive gitartab. Oppdater den der.",
                FrettedInstrument.UKULELE to "Fretscribe på datamaskinen er for gammel til å skrive ukuleletab. Oppdater den der.",
                FrettedInstrument.MANDOLIN to "Fretscribe på datamaskinen er for gammel til å skrive mandolintab. Oppdater den der."),
        )
        for ((lang, said) in words) {
            language(lang)
            computer("guitar-line", older = true)
            for ((kind, why) in said) {
                store.save(YourInstrument(kind))
                openARecording("${kind.name}.wav")
                // The computer is there, and says what it can write: the reason is on screen, in true words.
                waitUntil(10_000) { rule.onAllNodesWithText(why).fetchSemanticsNodes().isNotEmpty() }
                rule.onNodeWithText(why).assertIsDisplayed()
                // With an answer chosen there is still no way on.
                card("song").performClick()
                card("song").assertIsSelected()
                rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
                assertFalse(shown(), Regex("didn't accept|godtok ikke").containsMatchIn(shown()))
                assertNoTextIsClipped()
                checkAccessibility()
                if (kind == FrettedInstrument.GUITAR_6) shot("guitar-too-old-${lang.take(2)}-light")
            }
            // Nothing was sent: no recording, no job.
            assertEquals(emptyList<String>(), runBlocking { container.engine()!!.jobs() }.map { it.id })
            assertNull(vm.result.value)
            rule.runOnUiThread { container.fixtureSource = null }
        }
    }

    /** The Continue button's state, as a screen reader says it after "disabled". */
    private fun continueSays(): String? = rule.onNodeWithTag("fs-what-continue").fetchSemanticsNode().config.getOrNull(SemanticsProperties.StateDescription)

    @Test
    fun whenTheComputerCannotSayWhatItHasABassGoesUnderTheOlderIdAndTheRestAsTabs() {
        language("en-GB")
        // The computer is there and takes jobs, but its list of profiles can't be had.
        computer("guitar-line", profiles = { throw java.io.IOException("no answer") })
        for ((kind, profile) in listOf(FrettedInstrument.BASS_4 to "bass-tab", FrettedInstrument.GUITAR_6 to "tab", FrettedInstrument.UKULELE to "tab", FrettedInstrument.MANDOLIN to "tab")) {
            store.save(YourInstrument(kind))
            openARecording("${kind.name}.wav")
            assertEquals(ComputerProfiles.Answer(ComputerProfiles.answer!!.computer, asking = false, listed = null), ComputerProfiles.answer)
            // Nothing says the computer is too old or still being asked, and Continue works once there is an answer.
            assertFalse(shown(), Regex("too old|Asking your computer").containsMatchIn(shown()))
            card("song").performClick()
            rule.onNodeWithTag("fs-what-continue").assertIsEnabled()
            assertNull(continueSays())
            rule.onNodeWithTag("fs-what-continue").performClick()
            waitForTag("fs-show-tab")
            assertEquals(kind.name, profile, lastJob().profile)
            assertEquals(kind, sent().instrument)
        }
    }

    @Test
    fun aFastTapBeforeTheComputerHasAnsweredSendsNothing() {
        language("en-GB")
        store.save(YourInstrument(FrettedInstrument.GUITAR_6))
        // A computer from before the tab profile that takes its time to say so.
        val answer = java.util.concurrent.CountDownLatch(1)
        computer("guitar-line", profiles = { answer.await(30, java.util.concurrent.TimeUnit.SECONDS); OLDER.toByteArray() })
        openARecording(answered = false)
        // While it is asked, Continue is off and says why, also with an answer chosen.
        rule.onNodeWithTag("fs-what-missing").assertIsDisplayed().assert(hasText("Asking your computer…"))
        card("song").performClick()
        card("song").assertIsSelected()
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        assertEquals("Asking your computer…", continueSays())
        assertTrue(ComputerProfiles.answer?.asking == true)
        assertNull(ComputerProfiles.listed)
        checkAccessibility()
        shot("guitar-asking-en-light")
        // A tap on it does nothing: no recording goes, no job is made.
        rule.onNodeWithTag("fs-what-continue").performClick()
        rule.waitForIdle()
        assertEquals(listOf(Screen.HOME, Screen.PROFILE), vm.screen.value)
        // The computer answers: it is too old. The line changes where a screen reader is told of it, and the button says why.
        answer.countDown()
        val why = "Fretscribe on your computer is too old to write guitar tabs. Update it there."
        waitUntil(10_000) { rule.onAllNodesWithText(why).fetchSemanticsNodes().isNotEmpty() }
        val line = rule.onNodeWithTag("fs-what-missing").assert(hasText(why)).fetchSemanticsNode()
        assertEquals(androidx.compose.ui.semantics.LiveRegionMode.Polite, line.config.getOrNull(SemanticsProperties.LiveRegion))
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        assertEquals(why, continueSays())
        rule.onNodeWithTag("fs-what-continue").performClick()
        rule.waitForIdle()
        assertEquals(listOf(Screen.HOME, Screen.PROFILE), vm.screen.value)
        assertEquals(emptyList<String>(), runBlocking { container.engine()!!.jobs() }.map { it.id })
        assertNull(vm.result.value)
    }

    @Test
    fun theButtonSaysWhyItIsOffAndAnotherComputerIsAskedAfresh() {
        language("en-GB")
        store.save(YourInstrument(FrettedInstrument.GUITAR_6))
        computer("guitar-line")
        openARecording()
        // Nothing chosen yet: the line and the button both say so.
        rule.onNodeWithTag("fs-what-missing").assert(hasText("Choose one to continue."))
        assertEquals("Choose one to continue.", continueSays())
        assertEquals(setOf("tab", "bass-tab"), ComputerProfiles.listed!!.filter { it.contains("tab") }.toSet())
        card("instrument").performClick()
        rule.onNodeWithTag("fs-what-continue").assertIsEnabled()
        assertNull(continueSays())
        assertTrue(rule.onAllNodesWithTag("fs-what-missing").fetchSemanticsNodes().isEmpty())
        // Another computer, an older one, slow to answer: what the first one said is not kept for it.
        val answer = java.util.concurrent.CountDownLatch(1)
        computer("guitar-line", profiles = { answer.await(30, java.util.concurrent.TimeUnit.SECONDS); OLDER.toByteArray() })
        openARecording(answered = false)
        waitUntil(10_000) { ComputerProfiles.answer?.asking == true }
        assertNull(ComputerProfiles.listed)
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        answer.countDown()
        waitUntil(10_000) { ComputerProfiles.answer?.asking == false }
        assertFalse("tab" in ComputerProfiles.listed!!)
    }

    private companion object {
        /** The profiles of a computer from before the tab profile. */
        const val OLDER = """["solo","brass-band","orchestra-with-soloist","pop-rock","bass-tab"]"""
    }
}
