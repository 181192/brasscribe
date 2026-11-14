package no.kalli.brasscribe

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.play.Screen
import no.kalli.scribe.play.Source
import no.kalli.scribe.play.SourceKind
import no.kalli.scribe.play.Where
import no.kalli.scribe.play.screen.ScreenDevice
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The score of a recording says where the part shown comes from ("From the recording") on a button that explains it.
 * The keyboard reaches that button with everything else a finger can act on, on the screen upright and in the top
 * bar's menu on a phone on its side.
 */
@RunWith(AndroidJUnit4::class)
class ScoreSourceKeyboardTest : ScreenTest() {
    @After
    fun clean() = rule.runOnUiThread { vm.home() }

    /** [inMenu]: where the part comes from is not on the screen but in the top bar's menu. */
    private fun theKeyboardReachesIt(how: String, inMenu: Boolean? = null) {
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        computer("old-hundredth")
        rule.runOnUiThread {
            vm.home()
            vm.setSource(Source("Old Hundredth.wav", SourceKind.FILE, 67.0))
            vm.navigate(Screen.PROFILE)
            vm.chooseProfile(Profile.ORCHESTRA_WITH_SOLOIST)
            vm.where.value = Where.COMPANION
            vm.startTranscription()
        }
        waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW && vm.result.value != null }
        rule.runOnUiThread { vm.navigate(Screen.SCORE) }
        waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && (vm.scoreController?.renders?.value ?: 0) > 0 }
        rest()
        // (Only what is placed: a part of the screen that is composed and not placed is not there for a finger or a key.)
        fun sources() = rule.onAllNodes(androidx.compose.ui.test.SemanticsMatcher("a part's source") {
            it.config.getOrNull(SemanticsProperties.TestTag)?.startsWith("source-") == true && it.layoutInfo.isPlaced
        }).fetchSemanticsNodes()
        // On a phone on its side the score has the screen, and what stands over it upright is in the top bar's menu; so
        // is where the part comes from wherever it would take a line of its own.
        if (inMenu != null) assertEquals("where the part comes from is ${if (inMenu) "in the menu" else "on the screen"}", inMenu, sources().isEmpty())
        if (sources().isEmpty()) {
            rule.onNodeWithTag("top-more").performClick()
            waitUntil(5_000) { sources().isNotEmpty() }
            rest()
        }
        val sources = sources()
        assertEquals("the score says where the part comes from", 1, sources.size)
        shot("score-source-$how")
        val reached = tabThrough()
        assertTrue("the keyboard reaches it; it goes ${reached.map { it.config.getOrNull(SemanticsProperties.TestTag) ?: it.id }}", reached.any { it.id == sources.single().id })
        // (The dimmed screen behind a sheet closes it for a finger; the keyboard has Escape and Back for that. Its name is
        // Material's own, in the phone's language.)
        val closeSheet = rule.activity.resources.getIdentifier("close_sheet", "string", rule.activity.packageName)
            .takeIf { it != 0 }?.let { rule.activity.getString(it) } ?: "Close sheet"
        assertEquals("nothing a finger can act on is left out", emptyList<Control>(), missedByTheKeyboard(reached).filter { it.words != closeSheet })
    }

    @Test
    fun theKeyboardReachesWhereThePartComesFrom() = theKeyboardReachesIt("upright")

    @Test
    fun onItsSideToo() {
        ScreenDevice.turn(rule, sideways = true)
        try { theKeyboardReachesIt("on-its-side") } finally { ScreenDevice.turn(rule, sideways = false) }
    }

    @Test
    fun onASmallPhoneWithLargerTextToo() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(1.3f)
        language("nb-NO")
        theKeyboardReachesIt("small", inMenu = true)
    }

    @Test
    fun withTheLargestTextToo() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 360, 640))
        textSize(2f)
        theKeyboardReachesIt("small-200", inMenu = true)
    }

    @Test
    fun onACommonPhoneItIsBesideThePartPicker() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 412, 915))
        theKeyboardReachesIt("common", inMenu = false)
    }

    @Test
    fun onASmallPhoneOnItsSideToo() {
        assumeTrue("this device keeps its own size", ScreenDevice.size(rule, 640, 360))
        theKeyboardReachesIt("small-on-its-side")
    }
}
