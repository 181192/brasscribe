package no.brasscribe.play.screen

import com.google.android.apps.common.testing.accessibility.framework.AccessibilityCheckResult.AccessibilityCheckResultType
import com.google.android.apps.common.testing.accessibility.framework.AccessibilityViewCheckResult
import com.google.android.apps.common.testing.accessibility.framework.checks.ImageContrastCheck
import com.google.android.apps.common.testing.accessibility.framework.checks.TextContrastCheck
import com.google.android.apps.common.testing.accessibility.framework.integrations.espresso.AccessibilityValidator
import com.google.android.apps.common.testing.accessibility.framework.uielement.ViewHierarchyElement
import org.hamcrest.BaseMatcher
import org.hamcrest.Description

/**
 * The Accessibility Test Framework's checks, as every screen test runs them, on the whole window: touch
 * target size, a missing or repeated name, a link in text that can't be reached, an element that traps the
 * screen reader, and contrast. An error fails the test, and so does text or an image whose contrast is
 * too low (the framework calls those warnings: it estimates the colours from a picture of the screen).
 *
 * [known] is the list of findings that are not real: each says why. It is kept short on purpose; a finding
 * that is real is fixed, not listed.
 */
object ScreenAccessibility {
    /** A finding that is not a real one, and why. */
    class Known(val why: String, val matches: (AccessibilityViewCheckResult) -> Boolean)

    val known: List<Known> = listOf(
        Known("the faint label of a button that is turned off (Continue before a choice is made): WCAG 1.4.3 leaves inactive controls out of its contrast rule") { r ->
            r.sourceCheckClass == TextContrastCheck::class.java &&
                generateSequence<ViewHierarchyElement>(r.element) { it.parentView }.any { it.isEnabled == false }
        },
    )

    private val contrast = setOf(TextContrastCheck::class.java, ImageContrastCheck::class.java)

    fun validator(): AccessibilityValidator = AccessibilityValidator()
        .setRunChecksFromRootView(true)
        .setThrowExceptionFor(AccessibilityCheckResultType.WARNING)
        .setSuppressingResultMatcher(object : BaseMatcher<AccessibilityViewCheckResult>() {
            override fun matches(item: Any?): Boolean {
                val result = item as? AccessibilityViewCheckResult ?: return false
                // Of the warnings, contrast fails a test; the others are advice.
                if (result.type == AccessibilityCheckResultType.WARNING && result.sourceCheckClass !in contrast) return true
                return known.any { it.matches(result) }
            }

            override fun describeTo(description: Description) {
                description.appendText("warnings other than contrast, and the findings known not to be real")
            }
        })
}
