package no.brasscribe.play

import android.net.Uri
import android.os.Looper
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Collections

/**
 * A recording is opened: the file is read on a worker, and how far it has got reaches the screen's state
 * on the main thread only. A listener that is called where the state is set (as a screen under test is)
 * sees every change there, and the progress is gone when the import is.
 */
@RunWith(AndroidJUnit4::class)
class ImportProgressTest : ScreenTest() {
    @Test
    fun theProgressOfAnImportIsSetOnTheMainThread() {
        val main = Looper.getMainLooper().thread
        val threads = Collections.synchronizedSet(mutableSetOf<Thread>())
        val progress = Collections.synchronizedList(mutableListOf<Float?>())
        // Unconfined: called on the thread that sets the value, with nothing in between.
        val listening = CoroutineScope(Dispatchers.Unconfined)
        listening.launch { vm.importProgress.collect { threads += Thread.currentThread(); progress += it } }
        listening.launch { vm.status.collect { threads += Thread.currentThread() } }
        listening.launch { vm.busy.collect { threads += Thread.currentThread() } }
        try {
            val file = recording()
            rule.runOnUiThread { vm.home(); vm.importUri(Uri.fromFile(file)) }
            waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE && !vm.busy.value }
        } finally {
            listening.cancel()
        }
        assertEquals("the threads the import's state was set on", setOf(main), threads.toSet())
        assertTrue("the progress was shown: $progress", progress.any { it != null })
        assertEquals("no progress is left when the import is over", null, vm.importProgress.value)
    }
}
