package no.brasscribe.play

import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.IntentCompat
import no.brasscribe.play.ui.AboutScreen
import no.brasscribe.play.ui.CompanionScreen
import no.brasscribe.play.ui.ExportScreen
import no.brasscribe.play.ui.FirstRunScreen
import no.brasscribe.play.ui.ProblemScreen
import no.brasscribe.play.ui.SettingsScreen
import no.brasscribe.play.ui.HomeScreen
import no.brasscribe.play.ui.OutputScreen
import no.brasscribe.play.ui.ProfileScreen
import no.brasscribe.play.ui.RecordScreen
import no.brasscribe.play.ui.ReviewScreen
import no.brasscribe.play.ui.ScoreScreen
import no.brasscribe.play.ui.TranscribeScreen
import no.brasscribe.play.ui.theme.PlayTheme

class MainActivity : ComponentActivity() {
    private val vm: PlayViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) handleIntent(intent)
        setContent { PlayTheme { PlayRoot(vm) } }
    }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    // The heartbeat runs while the app is in front (contract: presence); leaving it also stops a bar playing.
    override fun onStart() {
        super.onStart()
        vm.connection.start()
        val cm = getSystemService(ConnectivityManager::class.java) ?: return
        val cb = object : ConnectivityManager.NetworkCallback() {
            // Registering reports the current network at once: that is not a change, so it is skipped.
            private var first = true
            override fun onAvailable(network: Network) {
                if (first) { first = false; return }
                runOnUiThread { vm.connection.networkChanged() }
            }
        }
        runCatching { cm.registerDefaultNetworkCallback(cb) }.onSuccess { networkCallback = cb }
    }

    override fun onStop() {
        super.onStop()
        vm.connection.stop()
        vm.stopListening(announce = false)
        networkCallback?.let { cb -> runCatching { getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(cb) } }
        networkCallback = null
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    /** Share sheet (ACTION_SEND) and "Open with" (ACTION_VIEW) both import the file; brasscribe://pair pairs. */
    private fun handleIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_VIEW && intent.data?.scheme == no.brasscribe.play.engine.PairLink.SCHEME) {
            vm.openPairLink(intent.data.toString())
            return
        }
        val uri: Uri? = when (intent?.action) {
            Intent.ACTION_SEND -> IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
            Intent.ACTION_VIEW -> intent.data
            else -> null
        }
        if (uri != null) {
            vm.home()
            vm.importUri(uri)
        }
    }
}

@Composable
fun PlayRoot(vm: PlayViewModel) {
    val stack by vm.screen.collectAsState()
    BackHandler(enabled = stack.size > 1) { vm.back() }
    when (stack.last()) {
        Screen.FIRST_RUN -> FirstRunScreen(vm)
        Screen.HOME -> HomeScreen(vm)
        Screen.RECORD -> RecordScreen(vm)
        Screen.PROFILE -> ProfileScreen(vm)
        Screen.TRANSCRIBE -> TranscribeScreen(vm)
        Screen.REVIEW -> ReviewScreen(vm)
        Screen.OUTPUT -> OutputScreen(vm)
        Screen.SCORE -> ScoreScreen(vm)
        Screen.EXPORT -> ExportScreen(vm)
        Screen.COMPANION -> CompanionScreen(vm)
        Screen.ABOUT -> AboutScreen(vm)
        Screen.SETTINGS -> SettingsScreen(vm)
        Screen.HELP -> no.brasscribe.play.ui.HelpScreen(vm)
        Screen.PROBLEM -> ProblemScreen(vm)
    }
}
