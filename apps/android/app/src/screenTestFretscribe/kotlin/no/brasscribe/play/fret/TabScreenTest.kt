package no.brasscribe.play.fret

import android.net.Uri
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import no.brasscribe.play.R
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.screen.ScreenTest
import org.json.JSONObject
import org.junit.After
import org.junit.Before

/** A test of the tab view: the way to it on a fixture computer, and the engraving once alphaTab has laid it out. */
abstract class TabScreenTest : ScreenTest() {
    @Before
    fun aSixStringGuitar() {
        yourInstrumentStore(rule.activity).save(YourInstrument.DEFAULT)
    }

    @After
    fun forgetThePlaces() {
        TabPlaces.forget()
    }

    /** The computer of the tests: what [folder] of apps/fixtures holds, with tab.json changed on the way when [tab] is given, or missing. */
    protected fun computer(folder: String, withTab: Boolean = true, page: String = "tab", tab: ((JSONObject) -> Unit)? = null) {
        container.fixtureSource = FixtureSource { name ->
            // [page]: the fixture's page in another layout, served as the job's tab.musicxml.
            val file = if (name == "tab.musicxml") "$page.musicxml" else name
            val bytes = ScreenDevice.fixture("$folder/$file")
            when {
                name != "tab.json" || bytes == null -> bytes
                !withTab && showing -> null
                tab != null -> JSONObject(String(bytes)).also(tab).toString().toByteArray()
                else -> bytes
            }
        }
    }

    /** The tab view is on screen (Check the song has read the tab's facts before that). */
    @Volatile protected var showing = false


    /** The computer has a long song: the second fixture's bars fourteen times over (224 bars), with the marks of the page itself (the computer's notes are for the 16 bars). */
    protected fun longSong() {
        container.fixtureSource = FixtureSource { name ->
            val bytes = ScreenDevice.fixture("bass-line-marks/$name")
            when {
                name == "tab.musicxml" && bytes != null -> long(String(bytes), 14).toByteArray()
                name == "tab.json" && showing -> null
                else -> bytes
            }
        }
    }

    /** Home, a recording, What is this?, the notes written down, Check the song, Show the tab: the tab is engraved. */
    protected fun showTheTab(): TabView {
        showing = false
        val file = recording()
        openFromHome(file)
        waitForTag("fs-what-continue", 20_000)
        rule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.RadioButton) and
            hasAnyAncestor(SemanticsMatcher.expectValue(SemanticsProperties.TestTag, "fs-what-instrument"))).performClick()
        rule.onNodeWithTag("fs-what-continue").performClick()
        waitForTag("fs-show-tab")
        rule.onNode(isHeading() and androidx.compose.ui.test.hasText(text(R.string.fs_check_title))).assertIsDisplayed()
        showing = true
        rule.onNodeWithTag("fs-show-tab").performClick()
        return engraved()
    }

    protected fun engraved(): TabView {
        waitForTag("fs-tab", 30_000)
        // Until the view of the size the screen wants is there (a new size is a new view, a moment later), engraved and laid out.
        fun now() = TabScreenProbe.view?.let { Triple(it, it.engravings, it.engraving.value) }
        var seen: Triple<TabView, Int, TabEngraving?>?
        do {
            waitUntil(30_000) { TabScreenProbe.view?.let { it.engraving.value != null && it.scale == TabScreenProbe.wanted } == true }
            seen = now()
            settle()
        } while (now() != seen)
        return seen!!.first
    }

    protected fun turn(landscape: Boolean) = ScreenDevice.turn(rule, landscape)

    /** The second fixture's bars [times] over, renumbered: a long song. */
    protected fun long(xml: String, times: Int): String {
        val part = Regex("""(<part\s+id="[^"]+"\s*>)(.*?)(</part>)""", RegexOption.DOT_MATCHES_ALL)
        val measure = Regex("""<measure\b[^>]*>.*?</measure>""", RegexOption.DOT_MATCHES_ALL)
        return part.replace(xml) { m ->
            val bars = measure.findAll(m.groupValues[2]).map { it.value }.toList()
            var n = 0
            val body = (0 until times).joinToString("\n") { round ->
                bars.joinToString("\n") { b ->
                    n++
                    // The first measure's attributes and header are said once.
                    val bar = if (round > 0 && b === bars[0]) b.replace(Regex("""<attributes>.*?</attributes>""", RegexOption.DOT_MATCHES_ALL), "").replace(Regex("""<direction\b.*?</direction>""", RegexOption.DOT_MATCHES_ALL), "") else b
                    bar.replaceFirst(Regex("""number="[^"]*""""), "number=\"$n\"")
                }
            }
            m.groupValues[1] + body + m.groupValues[3]
        }
    }
}
