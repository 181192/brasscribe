package no.brasscribe.play.screen

import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The accessibility checks the screen tests run are live where they run: a screen made to fail them fails
 * them, for each kind of finding the screens are checked for.
 */
@RunWith(AndroidJUnit4::class)
class ScreenAccessibilityTest : ScreenTest() {
    // (Each test ends on a screen made to fail the checks.)
    override val checksTheLastScreen = false

    /** What the checks say about [content], or null when they find nothing. */
    private fun findings(content: @androidx.compose.runtime.Composable () -> Unit): String? {
        rule.runOnUiThread { rule.activity.setContent { Column { content() } } }
        rule.waitForIdle()
        return runCatching { checkAccessibility() }.exceptionOrNull()?.message
    }

    @Test
    fun aTargetTooSmallToTouchIsFound() {
        val said = findings { Text("Go", Modifier.size(20.dp).clickable { }) }
        assertTrue("$said", said.orEmpty().contains("touch target", ignoreCase = true))
    }

    @Test
    fun aButtonWithoutANameIsFound() {
        val said = findings { androidx.compose.foundation.layout.Box(Modifier.size(56.dp).clickable { }) }
        assertTrue("$said", said.orEmpty().contains("speakable text", ignoreCase = true) || said.orEmpty().contains("label", ignoreCase = true))
    }

    @Test
    fun textTooFaintToReadIsFound() {
        val said = findings { Text("Hard to read", Modifier.background(Color.White), color = Color(0xFFEEEEEE), fontSize = 14.sp) }
        assertTrue("$said", said.orEmpty().contains("contrast", ignoreCase = true))
    }

    @Test
    fun aScreenThatPassesHasNothingFound() {
        val said = findings { Text("Plain words", Modifier.background(Color.White), color = Color.Black) }
        assertTrue("$said", said == null)
    }
}
