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
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.accessibility.enableAccessibilityChecks
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.activity.compose.setContent
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
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
import no.brasscribe.play.ScoreEntry
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.Octave
import no.brasscribe.play.engine.Recording
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
 * A recording becomes a tab, on a fixture computer that answers as the engine did for a short bass line
 * (apps/fixtures/bass-line): Home, open a recording, What is this?,
 * writing down the notes, Check the song, Show the tab. In English and bokmål, with the accessibility
 * checks on every action, at 200 % text, and with the keyboard alone, with screenshots in light and dark.
 */
@RunWith(AndroidJUnit4::class)
class SendBassTabFlowTest : ScreenTest() {

    @Before
    fun setUp() {
        assertEquals("Fretscribe", Product.NAME)
        yourInstrumentStore(rule.activity).save(YourInstrument(no.brasscribe.play.engine.FrettedInstrument.BASS_4))
    }

    /** The computer of the tests: what the engine answered for the bass line, with [tab] changed on the way when given. */
    private fun computer(tab: ((JSONObject) -> Unit)? = null) = computer("bass-line") { name, bytes ->
        if (name == "tab.json" && bytes != null && tab != null) JSONObject(String(bytes)).also(tab).toString().toByteArray() else bytes
    }

    override val shots = "fretscribe/bass-flow"

    /** Open a recording from Home, as the file picker's answer does: What is this? follows. */
    private fun openARecording() {
        val file = recording()
        openFromHome(file)
        waitUntil(20_000) { rule.onAllNodesWithTag("fs-what-continue").fetchSemanticsNodes().isNotEmpty() }
        // (The computer is asked what it can write when the screen opens; Continue waits for its answer.)
        waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
    }

    private fun card(tag: String) = rule.onNode(
        SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            androidx.compose.ui.test.hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-$tag")),
    )

    @Test
    fun aRecordingBecomesATabInEnglishAndBokmal() {
        val words = mapOf(
            "en-GB" to listOf("What is this?", "Just my instrument", "A full song", "On your computer",
                "Bandroom on your computer writes down the notes. The recording is not sent online.", "Choose one to continue.", "Continue",
                "Stop writing down the notes?", "Stop", "Check the song", "Tuning: Standard", "Key and tempo: E minor, 100 beats a minute, two-four time",
                "Show the tab", "You can change this later.", "4-string bass · Standard", "is writing down the notes. You can switch to another app: when the tab is ready, it is in Your songs while your phone is connected to your computer."),
            "nb-NO" to listOf("Hva er dette?", "Bare instrumentet mitt", "En hel sang", "På datamaskinen din",
                "Bandroom på datamaskinen skriver ned tonene. Opptaket sendes ikke til nettet.", "Velg ett for å fortsette.", "Fortsett",
                "Slutte å skrive ned tonene?", "Stopp", "Sjekk sangen", "Stemming: Standard", "Toneart og tempo: e-moll, 100 slag i minuttet, to firedels takt",
                "Vis tabben", "Du kan endre dette senere.", "4-strengs bass · Standard", "skriver ned tonene. Du kan bytte til en annen app: når tabben er klar, ligger den i Sangene dine så lenge telefonen er koblet til datamaskinen."),
        )
        val steps = mapOf(
            "en-GB" to listOf("Sending the recording to your computer", "Listening for the beat", "Writing down the notes",
                "Placing the notes in bars", "Choosing strings and frets", "Laying out the tab"),
            "nb-NO" to listOf("Sender opptaket til datamaskinen", "Lytter etter pulsen", "Plukker ut instrumentet ditt", "Skriver ned tonene",
                "Plasserer tonene i takter", "Velger strenger og bånd", "Setter opp tabben"),
        )
        for ((lang, w) in words) {
            language(lang)
            computer()
            rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
            openARecording()

            // What is this? Two choices, nothing chosen, and where the notes are written down.
            rule.onNode(isHeading() and hasText(w[0])).assertIsDisplayed()
            val alone = card("instrument").assert(hasText(w[1])).assertIsNotSelected().assertHeightIsAtLeast(48.dp)
            val song = card("song").assert(hasText(w[2])).assertIsNotSelected().assertHeightIsAtLeast(48.dp)
            assertEquals(2, rule.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton)).fetchSemanticsNodes().size)
            assertEquals(0, alone.fetchSemanticsNode().config.getOrNull(SemanticsProperties.CollectionItemInfo)?.rowIndex)
            assertEquals(1, song.fetchSemanticsNode().config.getOrNull(SemanticsProperties.CollectionItemInfo)?.rowIndex)
            rule.onNodeWithTag("fs-what-where").assertIsDisplayed()
            rule.onNodeWithText(w[3]).assertIsDisplayed()
            rule.onNodeWithText(w[4]).assertIsDisplayed()
            // Nothing is offered on the phone, and nothing of Brasscribe's choices.
            assertFalse(shown(), Regex("Brasscribe|Brass band|Korps|On this phone|På denne telefonen").containsMatchIn(shown()))
            rule.onNodeWithText(w[5]).assertIsDisplayed()
            rule.onNodeWithTag("fs-what-continue").assert(hasText(w[6])).assertIsNotEnabled()
            shot("what-is-this-${lang.take(2)}-light")

            // English sends the bass alone, bokmål a full song.
            val whole = lang == "en-GB"
            (if (whole) alone else song).performClick()
            (if (whole) alone else song).assertIsSelected()
            (if (whole) song else alone).assertIsNotSelected()
            rule.onNodeWithTag("fs-what-continue").assertIsEnabled()
            if (whole) shot("what-is-this-chosen-en-light")
            rule.onNodeWithTag("fs-what-continue").performClick()

            // Writing down the notes: Cancel asks first, and the answer is still there afterwards.
            waitUntil(20_000) { rule.onAllNodes(hasContentDescription(text(no.brasscribe.play.R.string.transcribe_progress_label)), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
            rule.onNodeWithText(text(no.brasscribe.play.R.string.cancel)).assertHeightIsAtLeast(48.dp).performClick()
            rule.onNodeWithText(w[7]).assertIsDisplayed()
            if (whole) shot("writing-down-cancel-en-light")
            rule.onNodeWithText(w[8]).performClick()
            waitForTag("fs-what-continue", 10_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
            (if (whole) alone else song).assertIsSelected()
            rule.onNodeWithTag("fs-what-continue").assertIsEnabled().performClick()

            // The steps, in Fretscribe's words: a full song is separated first, the bass alone is not.
            val last = steps.getValue(lang).last()
            waitUntil(20_000) { rule.onAllNodesWithText(last).fetchSemanticsNodes().isNotEmpty() }
            // (The fixture computer has a name of its own; a real one shows its address there.)
            val during = shown().replace(no.brasscribe.play.engine.FixtureEngineApi.SERVER_NAME, "")
            steps.getValue(lang).forEach { assertTrue("$it in: $during", during.contains(it)) }
            assertFalse(during, Regex("Brasscribe|brass band|brassband|score|partitur", RegexOption.IGNORE_CASE).containsMatchIn(during))
            assertEquals(whole, !during.contains(if (lang == "en-GB") "Picking out your instrument" else "Plukker ut instrumentet ditt"))
            // What is true while it runs: the player may switch apps (the screen stays on), and no time left that is not known.
            assertTrue(during, during.contains(w[15]))
            assertFalse(during, Regex("minute|minutt|left|igjen|tell you|sier fra").containsMatchIn(during))
            rule.runOnUiThread { assertTrue("the screen stays on", rule.activity.window.decorView.findViewById<android.view.View>(android.R.id.content).let { root ->
                generateSequence(listOf(root)) { vs -> vs.flatMap { v -> (v as? android.view.ViewGroup)?.let { g -> (0 until g.childCount).map(g::getChildAt) }.orEmpty() }.takeIf { it.isNotEmpty() } }
                    .flatten().any { it.keepScreenOn }
            }) }
            val bar = rule.onNode(hasContentDescription(text(no.brasscribe.play.R.string.transcribe_progress_label)), useUnmergedTree = true).fetchSemanticsNode()
            assertTrue(bar.config.contains(SemanticsProperties.ProgressBarRangeInfo))
            shot("writing-down-${lang.take(2)}-light")

            // Check the song: what was heard, each finding one element, and one primary.
            waitForTag("fs-show-tab")
            assertEquals(listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT), vm.screen.value)
            rule.onNode(isHeading() and hasText(w[9])).assertIsDisplayed()
            waitForTag("fs-check-tuning", 10_000)
            rule.onNodeWithTag("fs-check-tuning").assertContentDescriptionEquals(w[10])
            rule.onNodeWithTag("fs-check-key").assertContentDescriptionEquals(w[11])
            // The recorded line has nothing unusual: no octave, reference pitch or doubtful notes, and nothing to change.
            listOf("octave", "reference", "marked", "no-place", "change-tuning", "change-octave").forEach {
                assertTrue(it, rule.onAllNodesWithTag("fs-check-$it").fetchSemanticsNodes().isEmpty())
            }
            rule.onNodeWithTag("fs-show-tab").assert(hasText(w[12])).assertHeightIsAtLeast(48.dp)
            // Nothing here can be changed, so nothing says it can.
            assertTrue(rule.onAllNodesWithText(w[13]).fetchSemanticsNodes().isEmpty())
            checkAccessibility()
            shot("check-the-song-${lang.take(2)}-light")
            rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
            shot("check-the-song-${lang.take(2)}-dark")
            rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }

            // What was sent: the player's instrument, and the answer for this recording.
            val sent = tabOptions(yourInstrumentStore(rule.activity).load(), SongAnswers.of(vm.source.value))
            assertEquals(if (whole) Recording.INSTRUMENT else Recording.SONG, sent.recording)
            assertEquals(listOf("bass-4", "standard", 0, Octave.AUTO), listOf(sent.instrument?.id, sent.tuning, sent.capo, sent.octave))
            val job = runBlocking { container.engine()!!.job(vm.result.value!!.jobId!!) }
            assertEquals("tab", job.profile)
            assertEquals(!whole, job.stages.any { it.name == "stems" })

            // Show the tab opens the tab view.
            rule.onNodeWithTag("fs-show-tab").performClick()
            waitForTag("fs-tab", 30_000)
            assertEquals(Screen.SCORE, vm.screen.value.last())
            // The tab is there: the view says its bars.
            waitUntil(30_000) {
                rule.onNodeWithTag("fs-tab").fetchSemanticsNode().config.getOrNull(SemanticsProperties.ContentDescription)
                    ?.firstOrNull()?.let { d -> Regex("""\d+""").findAll(d).any { it.value.toInt() > 1 } } == true
            }
            if (whole) shot("the-tab-en-light")

            // The song is in Your songs, with its instrument and tuning.
            rule.runOnUiThread { vm.home() }
            waitUntil(10_000) { rule.onAllNodesWithText(w[14], substring = true).fetchSemanticsNodes().isNotEmpty() }
            rule.onAllNodesWithText(w[14], substring = true).onFirst().performScrollTo().assertIsDisplayed()
            if (whole) shot("home-song-en-light")
        }
    }

    @Test
    fun checkTheSongOffersTheTuningThatFitsAndWritesItDownAgain() {
        language("en-GB")
        // The same line, as if it sounded like drop D, an octave up, sharp, with doubtful notes and one with no place.
        computer { tab ->
            val fits = tab.getJSONArray("tuning_suggestions")
            val dropD = (0 until fits.length()).map(fits::getJSONObject).first { it.getString("preset") == "bass-4-drop-d" }
            val rest = (0 until fits.length()).map(fits::getJSONObject).filter { it !== dropD }
            tab.put("tuning_suggestions", org.json.JSONArray(listOf(dropD) + rest))
            tab.put("octave_shift", -12)
            tab.getJSONObject("reference_pitch").put("cents", 30.4).put("retuned", true)
            val notes = tab.getJSONArray("notes")
            (0..2).forEach { notes.getJSONObject(it).put("confidence", 0.2) }
            notes.getJSONObject(3).put("out_of_range", true).put("string", JSONObject.NULL).put("fret", JSONObject.NULL)
        }
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }
        openARecording()
        card("instrument").performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-check-change-tuning")

        rule.onNodeWithTag("fs-check-tuning").assertContentDescriptionEquals("Tuning: Sounds like Drop D. Written for Standard.")
        rule.onNodeWithTag("fs-check-octave").assertContentDescriptionEquals("Octave: Written one octave lower than it was heard.")
        rule.onNodeWithTag("fs-check-reference").assertContentDescriptionEquals("Reference pitch: A little sharp of concert pitch (A = 440): 30 cents. Fretscribe allowed for it.")
        rule.onNodeWithText("You can change this later.").assertIsDisplayed()
        rule.onNodeWithTag("fs-check-marked").performScrollTo().assertContentDescriptionEquals("Notes to check: 3 notes marked ?")
        rule.onNodeWithTag("fs-check-no-place").performScrollTo()
            .assertContentDescriptionEquals("Notes with no place: 1 note with no place on your instrument. Is the tuning right?")
        rule.onNodeWithTag("fs-check-change-octave").performScrollTo().assert(hasText("Write it as it was heard")).assertHeightIsAtLeast(48.dp)
        rule.onNodeWithTag("fs-check-change-tuning").performScrollTo().assert(hasText("Use Drop D")).assertHeightIsAtLeast(48.dp)
        checkAccessibility()
        shot("check-the-song-findings-en-light")
        rule.runOnUiThread { container.updateAppearance(Appearance.DARK) }
        shot("check-the-song-findings-en-dark")
        rule.runOnUiThread { container.updateAppearance(Appearance.LIGHT) }

        // Use Drop D: the recording is written down again for that tuning, and Check the song comes back.
        val first = vm.result.value!!.jobId
        rule.onNodeWithTag("fs-check-change-tuning").performClick()
        waitUntil(20_000) { vm.screen.value.last() == Screen.TRANSCRIBE || vm.result.value?.jobId != first }
        waitUntil(60_000) { vm.result.value?.jobId != first && vm.screen.value == listOf(Screen.HOME, Screen.PROFILE, Screen.OUTPUT) }
        waitForTag("fs-show-tab")
        val sent = tabOptions(yourInstrumentStore(rule.activity).load(), SongAnswers.of(vm.source.value))
        assertEquals(listOf("drop-d", Recording.INSTRUMENT, Octave.AUTO), listOf(sent.tuning, sent.recording, sent.octave))
        assertEquals(2, runBlocking { container.engine()!!.jobs() }.size)
        // The player's usual tuning is as it was, and the song is saved once.
        assertEquals(YourInstrument(no.brasscribe.play.engine.FrettedInstrument.BASS_4), yourInstrumentStore(rule.activity).load())
        waitUntil(10_000) { vm.savedScores.value.size == 1 }
    }

    @Test
    fun withoutTheComputerWhatIsThisSaysSoAndOffersToConnect() {
        language("en-GB")
        rule.runOnUiThread { container.fixtureSource = null; container.updateAppearance(Appearance.LIGHT) }
        openARecording()
        rule.onNodeWithText("Bandroom on your computer writes down the notes.").assertIsDisplayed()
        rule.onNodeWithText("Not connected. Fretscribe needs your computer to write a tab.").assertIsDisplayed()
        card("song").performClick()
        // A choice alone is not enough: the computer comes first.
        rule.onNodeWithText("Connect your computer to continue.").assertIsDisplayed()
        rule.onNodeWithTag("fs-what-continue").assertIsNotEnabled()
        shot("what-is-this-not-connected-en-light")
        rule.onNodeWithText("Connect").assertHeightIsAtLeast(44.dp).performClick()
        waitUntil(5_000) { vm.screen.value.last() == Screen.COMPANION }
        // Back from pairing, the answer is still there.
        rule.runOnUiThread { vm.back() }
        waitForTag("fs-what-continue", 5_000); waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
        card("song").assertIsSelected()
    }

    @Test
    fun at200PercentTextNothingIsClipped() {
        for (lang in listOf("en-GB", "nb-NO")) {
            language(lang)
            computer { tab -> tab.put("octave_shift", -12); tab.getJSONObject("reference_pitch").put("cents", -22.0) }
            textSize(2.0f)
            openARecording()
            assertNoTextIsClipped()
            card("instrument").performScrollTo().assertIsDisplayed()
            card("song").performScrollTo().assertIsDisplayed()
            rule.onNodeWithTag("fs-what-where").performScrollTo().assertIsDisplayed()
            rule.onNodeWithTag("fs-what-continue").assertIsDisplayed()
            card("instrument").performScrollTo()
            shot("what-is-this-200-${lang.take(2)}")
            card("song").performScrollTo().performClick()
            card("song").assertIsSelected()
            rule.onNodeWithTag("fs-what-continue").performClick()
            waitForTag("fs-check-change-octave")
            assertNoTextIsClipped()
            listOf("tuning", "octave", "reference", "key", "change-octave").forEach {
                rule.onNodeWithTag("fs-check-$it").performScrollTo().assertIsDisplayed()
            }
            rule.onNodeWithTag("fs-show-tab").assertIsDisplayed()
            rule.onNodeWithTag("fs-check-tuning").performScrollTo()
            shot("check-the-song-200-${lang.take(2)}")
            textSize(1.0f)
        }
    }

    @Test
    fun theKeyboardAloneGoesFromWhatIsThisToTheTab() {
        language("en-GB")
        computer { tab -> tab.put("octave_shift", -12) }
        openARecording()
        // Tab reaches the way back, both choices and Continue.
        val reached = mutableSetOf<String>()
        repeat(6) { key(KeyEvent.KEYCODE_TAB); reached += focusedWords() }
        listOf("Home", "Just my instrument", "A full song").forEach { w -> assertTrue("$w in $reached", reached.any { it.contains(w) }) }
        // Enter chooses, and Continue can then be reached and pressed.
        tabTo("Just my instrument")
        key(KeyEvent.KEYCODE_ENTER)
        card("instrument").assertIsSelected()
        tabTo("Continue")
        key(KeyEvent.KEYCODE_ENTER)
        waitUntil(20_000) { vm.screen.value.last() == Screen.TRANSCRIBE || vm.screen.value.last() == Screen.OUTPUT }
        // Writing down the notes: Cancel is reached, asks, and Keep going is reached too.
        if (vm.screen.value.last() == Screen.TRANSCRIBE) {
            tabTo("Cancel")
            key(KeyEvent.KEYCODE_ENTER)
            waitUntil(5_000) { rule.onAllNodesWithText("Stop writing down the notes?").fetchSemanticsNodes().isNotEmpty() || vm.screen.value.last() == Screen.OUTPUT }
            if (vm.screen.value.last() == Screen.TRANSCRIBE) {
                tabTo("Keep going")
                key(KeyEvent.KEYCODE_ENTER)
            }
        }
        // Check the song: the row's button, the way back and Show the tab; Enter shows the tab.
        waitForTag("fs-check-change-octave")
        val here = mutableSetOf<String>()
        repeat(6) { key(KeyEvent.KEYCODE_TAB); here += focusedWords() }
        listOf("Back", "Write it as it was heard", "Show the tab").forEach { w -> assertTrue("$w in $here", here.any { it.contains(w) }) }
        tabTo("Show the tab")
        key(KeyEvent.KEYCODE_ENTER)
        waitForTag("fs-tab", 30_000)
        assertEquals(Screen.SCORE, vm.screen.value.last())
    }

    @Test
    fun aBandScoreOnTheComputerOpensInBrasscribeNotHere() {
        language("en-GB")
        computer()
        rule.runOnUiThread { vm.openEntry(ScoreEntry("job:band-1", "Old Hundredth", System.currentTimeMillis(), "brass-band", jobId = "band-1")) }
        waitUntil(5_000) { rule.onAllNodesWithText("This is a band score. Open it in Brasscribe.").fetchSemanticsNodes().isNotEmpty() }
        assertEquals(listOf(Screen.HOME), vm.screen.value)
        assertEquals(null, vm.result.value)
        assertEquals(null, vm.standFromLibrary.value)
        // Its row's menu has none of the actions that would open it; a tab's row has them.
        val now = System.currentTimeMillis()
        assertEquals(listOf("Edit title", "Delete"), menuOf(ScoreEntry("job:band-1", "Old Hundredth", now, "brass-band", jobId = "band-1")))
        assertEquals(listOf("Edit title", "Open on the music stand", "Check the song", "Delete"),
            menuOf(ScoreEntry("job:tab-1", "Bass line", now, "bass-tab", jobId = "tab-1")))
    }

    /** The row menu of [entry], opened: the actions it offers. */
    private fun menuOf(entry: ScoreEntry): List<String> {
        rule.runOnUiThread {
            rule.activity.setContent { no.brasscribe.play.ui.theme.PlayTheme(dark = false, pink = false) { no.brasscribe.play.ui.ScoreOptionsButton(vm, entry) } }
        }
        rule.onNodeWithContentDescription(rule.activity.getString(no.brasscribe.play.R.string.score_options, entry.title)).performClick()
        rule.waitForIdle()
        return listOf(no.brasscribe.play.R.string.edit_title, no.brasscribe.play.R.string.stand_open_from_library, no.brasscribe.play.R.string.check_notes, no.brasscribe.play.R.string.delete)
            .map { rule.activity.getString(it) }.filter { rule.onAllNodesWithText(it).fetchSemanticsNodes().isNotEmpty() }
    }
}
