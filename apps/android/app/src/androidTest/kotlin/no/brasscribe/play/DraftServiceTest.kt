package no.brasscribe.play

import android.app.NotificationManager
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import no.brasscribe.play.test.DeviceOnly

/**
 * The service that holds the app in front while a band draft is made. A service started with
 * startForegroundService must reach startForeground before it stops, or the system ends the app.
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
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

    /** The phone refuses the foreground: the service stops, says so, and the app goes on living. */
    @Test
    fun aRefusedForegroundStopsTheDraft() {
        val real = DraftService.enterForeground
        var refused = false
        // A refusal from the system itself: it does not accept a service without a type.
        DraftService.enterForeground = { s, id, n, _ -> s.startForeground(id, n, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_NONE) }
        try {
            instrumentation.runOnMainSync { DraftService.start(context) { refused = true } }
            assertTrue("the draft is told", waitFor(5_000) { refused })
            Thread.sleep(15_000)
            assertTrue(notification() == null)
        } finally {
            DraftService.enterForeground = real
            instrumentation.runOnMainSync { DraftService.stop(context) }
        }
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

    /**
     * A whole draft on this device, from a band recording put there by hand (not in git):
     * `adb push mix.wav /sdcard/Android/data/no.brasscribe.play/files/band-mix.wav`. Skipped without it. The draft it saves is
     * removed again, so Your scores is left as it was.
     */
    @Test
    fun aDraftOfARecordingIsMadeUnderTheService() {
        val mix = java.io.File(context.getExternalFilesDir(null), "band-mix.wav")
        org.junit.Assume.assumeTrue("no recording at $mix", mix.canRead())
        val container = (context.applicationContext as PlayApplication).container
        org.junit.Assume.assumeTrue("the listening files are not in this build", container.hasBandModels)
        lateinit var vm: PlayViewModel
        rule.scenario.onActivity { vm = androidx.lifecycle.ViewModelProvider(it)[PlayViewModel::class.java] }
        val before = container.scoreLibrary.list().map { it.id }.toSet()
        try {
            instrumentation.runOnMainSync { vm.home(); vm.importUri(android.net.Uri.fromFile(mix)) }
            assertTrue("the recording is read", waitFor(60_000) { vm.screen.value.last() == Screen.PROFILE })
            instrumentation.runOnMainSync {
                vm.chooseProfile(no.brasscribe.play.engine.Profile.BRASS_BAND)
                vm.where.value = Where.DEVICE
                vm.startTranscription()
            }
            assertTrue("the draft is made: ${vm.screen.value}, ${vm.problemDetail}", waitFor(300_000) { vm.screen.value.last() != Screen.TRANSCRIBE })
            assertEquals(Screen.REVIEW, vm.screen.value.last())
            assertTrue(vm.result.value?.draft == true)
            assertTrue("the service stops with the draft", waitFor(15_000) { notification() == null })
        } finally {
            instrumentation.runOnMainSync { vm.cancelTranscription(); vm.home() }
            Thread.sleep(1_000)
            (container.scoreLibrary.list().map { it.id }.toSet() - before).forEach { container.scoreLibrary.delete(it) }
        }
    }
}
