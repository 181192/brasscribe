package no.brasscribe.play.screen

import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The checks the screen catalogues make find what they are for: a control the keyboard cannot reach, and a
 * text cut by the box it is in. Each is shown with a screen made to fail, and one made to pass.
 */
@RunWith(AndroidJUnit4::class)
class ScreenChecksTest : ScreenTest() {
    // (The screens here are made by the test, not the app's.)
    override val checksTheLastScreen = false

    private fun show(content: @androidx.compose.runtime.Composable () -> Unit) {
        rule.runOnUiThread { rule.activity.setContent { Column { content() } } }
        rule.waitForIdle()
    }

    @Test
    fun aControlTheKeyboardCannotReachIsFound() {
        show {
            Button({}) { Text("Reached") }
            Box(Modifier.size(56.dp).focusProperties { canFocus = false }.clickable { }.semantics { contentDescription = "Out of reach" })
        }
        assertEquals(listOf("Out of reach"), missedByTheKeyboard(tabThrough()))
    }

    @Test
    fun whenEveryControlIsReachedNothingIsMissed() {
        show {
            Button({}) { Text("One") }
            Button({}) { Text("Two") }
        }
        assertEquals(emptyList<String>(), missedByTheKeyboard(tabThrough()))
    }

    @Test
    fun aTextCutByTheBoxItIsInIsFound() {
        show { Box(Modifier.size(200.dp, 20.dp).clipToBounds()) { Text("Half out of its box", Modifier.offset(y = 12.dp)) } }
        val said = runCatching { assertNoTextIsClipped() }.exceptionOrNull()?.message.orEmpty()
        assertTrue(said, said.contains("Half out of its box"))
    }

    @Test
    fun aTextThatFitsItsBoxIsNotCut() {
        show { Box(Modifier.size(200.dp, 40.dp).clipToBounds()) { Text("Whole") } }
        assertNoTextIsClipped()
    }
}
