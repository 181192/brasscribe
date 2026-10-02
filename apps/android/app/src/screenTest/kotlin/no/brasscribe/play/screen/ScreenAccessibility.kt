package no.brasscribe.play.screen

import com.google.android.apps.common.testing.accessibility.framework.integrations.espresso.AccessibilityValidator

/**
 * The Accessibility Test Framework's checks, as every screen test runs them: on the whole window after each
 * action (touch target size, a missing or repeated name, contrast, a link in text that can't be reached,
 * an element that traps the screen reader). An error fails the test.
 */
object ScreenAccessibility {
    fun validator(): AccessibilityValidator = AccessibilityValidator().setRunChecksFromRootView(true)
}
