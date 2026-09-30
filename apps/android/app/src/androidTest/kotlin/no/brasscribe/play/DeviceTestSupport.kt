package no.brasscribe.play

import android.app.KeyguardManager
import android.content.Context
import android.os.PowerManager
import org.junit.Assume.assumeTrue
import java.io.File

/**
 * Tests that play a score need the activity resumed: behind a locked keyguard or a dark screen Compose has no
 * hierarchy and alphaTab's synth thread stalls, so they would fail for the device, not the app. Skips them then.
 */
fun assumeScreenUsable(context: Context) {
    val keyguard = context.getSystemService(KeyguardManager::class.java)
    val power = context.getSystemService(PowerManager::class.java)
    assumeTrue("the screen is off", power.isInteractive)
    assumeTrue("the keyguard is locked", !keyguard.isKeyguardLocked)
}

/**
 * The scores in the app's library when a test starts. Opening a score saves it there, and on a phone that
 * library is the user's: [deleteAdded] removes what the test added and leaves the rest alone.
 */
class LibrarySnapshot(context: Context) {
    private val root = File(context.filesDir, "scores")
    private val library = SavedScoreLibrary(root)
    // folder names, not list(): a score whose save was cut short has no details but is the test's all the same
    private val before = root.list().orEmpty().toSet()

    fun deleteAdded() {
        for (id in root.list().orEmpty()) if (id !in before) library.delete(id)
    }
}
