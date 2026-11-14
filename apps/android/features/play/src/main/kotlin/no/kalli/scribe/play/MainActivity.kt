package no.kalli.scribe.play

import no.kalli.scribe.connection.LocalNetwork

import no.kalli.scribe.engine.Wire
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.SideEffect
import androidx.activity.viewModels
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import no.kalli.scribe.play.ui.theme.PlayTheme
import no.kalli.scribe.design.systemHighContrast


class MainActivity : ComponentActivity() {
    private val vm: PlayViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        edgeToEdge()
        if (savedInstanceState == null) handleIntent(intent)
        setContent {
            // Settings › Display › Appearance: read before the first frame, so there is no flash.
            val appearance = vm.container.appearance
            val dark = appearance.isDark(isSystemInDarkTheme())
            val highContrast = systemHighContrast()
            SideEffect { applyWindowTheme(dark, appearance.isPink, highContrast) }
            PlayTheme(dark = dark, pink = appearance.isPink) { vm.container.product.Root(vm) }
            AskForLocalNetwork(vm)
        }
    }

    /**
     * The window behind Compose and the system bar icons follow the app's appearance, not the phone's
     * night mode, and the phone's high contrast as the theme does. Nothing is recreated, so playback and
     * the score position stay as they are.
     */
    private var windowTheme: Triple<Boolean, Boolean, Boolean>? = null
    private fun applyWindowTheme(dark: Boolean, pink: Boolean, highContrast: Boolean) {
        val theme = Triple(dark, pink, highContrast)
        if (windowTheme == theme) return
        windowTheme = theme
        androidx.core.view.WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
        window.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(getColor(vm.container.product.windowColors.pick(dark, pink, highContrast))))
    }

    /**
     * The app draws behind the status and navigation bars, and the bars have no ground of their own: the page is seen
     * through them. Set on the window itself, once: androidx's enableEdgeToEdge keeps the style of its first call and
     * puts it back at every turn of the phone, the system's own scrim behind the navigation bar with it.
     */
    private fun edgeToEdge() {
        // (The window reads its theme when its decor is made, and would take the theme's word after ours: made first.)
        window.decorView
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        window.attributes = window.attributes.apply { layoutInDisplayCutoutMode = android.view.WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS }
        @Suppress("DEPRECATION")
        run {
            window.statusBarColor = android.graphics.Color.TRANSPARENT
            window.navigationBarColor = android.graphics.Color.TRANSPARENT
        }
        window.isStatusBarContrastEnforced = false
        window.isNavigationBarContrastEnforced = false
    }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    // The heartbeat runs while the app is in front (contract: presence); leaving it also stops a bar playing.
    override fun onStart() {
        super.onStart()
        AppInFront.started()
        JobNotices.clearDone(this)
        // (A network the player opened in the phone's settings meanwhile is found here: start runs the check again.)
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

    // Back from the phone's question (answered, or left): no question of the app's is on screen now.
    override fun onResume() {
        super.onResume()
        LocalNetwork.asking = false
    }

    override fun onStop() {
        super.onStop()
        AppInFront.stopped()
        vm.connection.stop()
        vm.stopListening(announce = false)
        networkCallback?.let { cb -> runCatching { getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(cb) } }
        networkCallback = null
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    /**
     * Share sheet (ACTION_SEND) and "Open with" (ACTION_VIEW) both import the file: a recording, or, from the share
     * sheet, printed music as a picture or a PDF (several shared at once, ACTION_SEND_MULTIPLE, are its pages in
     * order); scribe://pair pairs; a tap on "ready" opens that job's score or tab.
     */
    fun handleIntent(intent: Intent?) {
        if (intent?.action == JobNotices.ACTION_OPEN_JOB) {
            // The activity is exported: only an id of the engine's shape is opened.
            intent.getStringExtra(JobNotices.EXTRA_JOB)?.takeIf(JobNotices::isJobId)?.let(vm::openFinishedJob)
            return
        }
        if (intent?.action == Intent.ACTION_VIEW && intent.data?.scheme == Wire.PAIR_SCHEME) {
            vm.openPairLink(intent.data.toString())
            return
        }
        val uris: List<Uri> = when (intent?.action) {
            Intent.ACTION_SEND -> listOfNotNull(intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java))
            Intent.ACTION_SEND_MULTIPLE -> intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java).orEmpty()
            Intent.ACTION_VIEW -> listOfNotNull(intent.data)
            else -> emptyList()
        }
        if (uris.isNotEmpty()) {
            vm.home()
            vm.importUris(uris)
        }
    }
}

/**
 * A paired phone that may not reach the local network (Android 17: the app was updated to ask, or the player took
 * the leave back) is asked when the app opens, so the computer is found again. A phone that is not paired is asked
 * on the pairing screen, which asks for itself.
 */
@Composable
private fun AskForLocalNetwork(vm: PlayViewModel) {
    val context = LocalContext.current
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        LocalNetwork.asking = false
        if (LocalNetwork.allowed(context)) vm.connection.networkChanged()
    }
    LaunchedEffect(Unit) {
        if (!vm.container.computerInReach() && vm.screen.value.last() != Screen.COMPANION && !LocalNetwork.asking) {
            LocalNetwork.asking = true
            ask.launch(LocalNetwork.PERMISSION)
        }
    }
}
