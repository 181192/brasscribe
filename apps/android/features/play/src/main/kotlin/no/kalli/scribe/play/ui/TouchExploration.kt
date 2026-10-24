package no.kalli.scribe.play.ui

import android.view.accessibility.AccessibilityManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.produceState
import androidx.compose.ui.platform.LocalContext

/**
 * Touch exploration alone (TalkBack and the like): a screen is then read from its top, in order. Switch
 * Access and a service that only speaks are used with the screen in sight, and do not count here. Tests
 * set [override] in place of a real screen reader.
 */
@Composable
fun rememberTouchExploration(override: Boolean?): Boolean {
    val context = LocalContext.current
    val state = produceState(initialValue = override ?: false, override) {
        if (override != null) { value = override; return@produceState }
        val am = context.getSystemService(AccessibilityManager::class.java) ?: return@produceState
        value = am.isTouchExplorationEnabled
        val touch = AccessibilityManager.TouchExplorationStateChangeListener { value = it }
        am.addTouchExplorationStateChangeListener(touch)
        awaitDispose { am.removeTouchExplorationStateChangeListener(touch) }
    }
    return state.value
}
