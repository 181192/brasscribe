package no.brasscribe.play

import android.net.Uri
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.fret.ComputerProfiles
import no.brasscribe.play.fret.TabPlaces
import no.brasscribe.play.fret.TabScreenProbe
import no.brasscribe.play.fret.YourInstrument
import no.brasscribe.play.fret.yourInstrumentStore
import no.brasscribe.play.screen.ScreenCatalogue
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.runner.RunWith

/** Fretscribe's screens (see [ScreenCatalogue]), on the fixture computer that answers as the engine did for a short bass line. */
@RunWith(AndroidJUnit4::class)
class FretscribeScreensTest : ScreenCatalogue() {
    override val shots = "fretscribe"

    @Before
    fun aBass() {
        yourInstrumentStore(rule.activity).save(YourInstrument(FrettedInstrument.BASS_4))
    }

    @After
    fun asItWas() {
        yourInstrumentStore(rule.activity).save(YourInstrument.DEFAULT)
        TabPlaces.forget()
        rule.runOnUiThread { container.firstRunDone = true }
    }

    /** The computer: the bass line with notes to check, as if it sounded like drop D, an octave up and a little sharp. */
    private fun theComputer() = computer("bass-line-marks") { name, bytes ->
        if (name != "tab.json" || bytes == null) bytes else JSONObject(String(bytes)).also { tab ->
            tab.put("octave_shift", -12)
            tab.getJSONObject("reference_pitch").put("cents", 30.4).put("retuned", true)
        }.toString().toByteArray()
    }

    private fun whatIsThis() {
        theComputer()
        val file = recording()
        rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(file)) }
        waitForTag("fs-what-continue", 20_000)
        waitUntil(20_000) { ComputerProfiles.answer?.asking != true }
    }

    private fun checkTheSong() {
        whatIsThis()
        rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-instrument"))).performScrollTo().performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
    }

    private fun theTab() {
        checkTheSong()
        rule.onNodeWithTag("fs-show-tab").performClick()
        waitForTag("fs-tab", 30_000)
        waitUntil(30_000) { TabScreenProbe.view?.let { it.engraving.value != null && it.scale == TabScreenProbe.wanted } == true }
        rest()
    }

    private fun go(vararg to: Screen) = rule.runOnUiThread { to.forEach(vm::navigate) }

    override val screens = listOf(
        Entry("first-run") { rule.runOnUiThread { container.firstRunDone = false; vm.navigate(Screen.FIRST_RUN) } },
        Entry("your-instrument") { rule.runOnUiThread { vm.navigate(Screen.SETTINGS); vm.openSeatPicker(SeatPickerMode.SETTINGS) }; waitForTag("fs-keep", 5_000) },
        Entry("home") { },
        Entry("home-with-a-song") { checkTheSong(); waitUntil(10_000) { vm.savedScores.value.isNotEmpty() }; rule.runOnUiThread { vm.home() }; rest() },
        Entry("what-is-this") { whatIsThis() },
        Entry("writing-down", steady = false) {
            whatIsThis()
            rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
                hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-song"))).performScrollTo().performClick()
            rule.onNodeWithTag("fs-what-continue").performClick()
            waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE }
        },
        Entry("check-the-song") { checkTheSong() },
        Entry("tab") { theTab() },
        Entry("tab-note") { theTab(); rule.onNodeWithTag("fs-tab-mark-0").performScrollTo().performClick(); waitForTag("fs-tab-note", 5_000); rest() },
        Entry("settings") { go(Screen.SETTINGS) },
        Entry("computer") { go(Screen.SETTINGS, Screen.COMPANION) },
        Entry("about") { go(Screen.SETTINGS, Screen.ABOUT) },
        Entry("help") { go(Screen.HELP) },
        Entry("problem") { rule.runOnUiThread { vm.showProblem(Problem.FILE_UNREADABLE) } },
    )
}
