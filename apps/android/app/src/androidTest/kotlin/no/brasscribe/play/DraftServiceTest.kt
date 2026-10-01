package no.brasscribe.play

import android.app.NotificationManager
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The service that holds the app in front while a band draft is made. A service started with
 * startForegroundService must reach startForeground before it stops, or the system ends the app.
 */
@RunWith(AndroidJUnit4::class)
class DraftServiceTest {
    // The app must be in front to start a foreground service.
    @get:Rule
    val rule = ActivityScenarioRule(MainActivity::class.java)

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private fun notification() = context.getSystemService(NotificationManager::class.java).activeNotifications
        .firstOrNull { it.notification.channelId == "draft" }

    // Without the permission the system keeps the notification out of sight, and out of the list read here.
    @org.junit.Before
    fun allowNotifications() {
        if (android.os.Build.VERSION.SDK_INT >= 33)
            instrumentation.uiAutomation.grantRuntimePermission(context.packageName, android.Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun waitFor(ms: Long, what: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (what()) return true; Thread.sleep(100) }
        return what()
    }

    @Test
    fun aDraftStoppedAtOnceDoesNotEndTheApp() {
        // Start and stop in one turn of the main thread, as a draft that is refused or cancelled at once does.
        instrumentation.runOnMainSync {
            DraftService.start(context)
            DraftService.stop(context)
        }
        // The system's limit for reaching the foreground is about ten seconds; the test dies with the app.
        Thread.sleep(15_000)
        assertTrue("the notification is gone", waitFor(2_000) { notification() == null })
    }

    @Test
    fun theNotificationOpensTheApp() {
        instrumentation.runOnMainSync { DraftService.start(context) }
        try {
            // The system may hold a foreground service's notification back for its first ten seconds.
            assertTrue("the draft notification shows", waitFor(15_000) { notification() != null })
            val intent = notification()!!.notification.contentIntent
            assertNotNull("tapping it opens the app", intent)
            assertTrue(intent.isActivity && intent.creatorPackage == context.packageName)
        } finally {
            instrumentation.runOnMainSync { DraftService.stop(context) }
        }
        assertTrue("stopped with the draft", waitFor(5_000) { notification() == null })
    }
}
