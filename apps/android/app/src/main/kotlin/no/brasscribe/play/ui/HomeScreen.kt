package no.brasscribe.play.ui

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.launch
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.SourceKind
import no.brasscribe.play.capture.CaptureController
import no.brasscribe.play.capture.CaptureKind
import no.brasscribe.play.ui.theme.LocalPlayTokens

@Composable
fun HomeScreen(vm: PlayViewModel) {
    val context = LocalContext.current
    val status by vm.status.collectAsState()
    val busy by vm.busy.collectAsState()
    var showDeviceNotice by remember { mutableStateOf(false) }
    var pendingDevice by remember { mutableStateOf(false) }

    val pickFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(vm::importUri) }
    val pickScore = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(vm::openScoreUri) }
    val projectionConsent = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val data = r.data
        if (r.resultCode == Activity.RESULT_OK && data != null) {
            CaptureController.startDevice(context, r.resultCode, data)
            vm.navigate(Screen.RECORD)
        } else vm.say(R.string.device_consent_denied)
    }
    val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) { vm.say(R.string.record_permission_needed); return@rememberLauncherForActivityResult }
        if (pendingDevice) {
            pendingDevice = false
            projectionConsent.launch(context.getSystemService(MediaProjectionManager::class.java).createScreenCaptureIntent())
        } else {
            CaptureController.startMicrophone(context)
            vm.navigate(Screen.RECORD)
        }
    }

    fun withMic(device: Boolean) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        pendingDevice = device
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            if (device) {
                pendingDevice = false
                projectionConsent.launch(context.getSystemService(MediaProjectionManager::class.java).createScreenCaptureIntent())
            } else {
                CaptureController.startMicrophone(context)
                vm.navigate(Screen.RECORD)
            }
        } else micPermission.launch(Manifest.permission.RECORD_AUDIO)
    }

    PlayScaffold(title = stringResource(R.string.app_name), onBack = null, status = status) {
        Text(stringResource(R.string.home_tagline), style = MaterialTheme.typography.bodyLarge)
        if (busy) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        BigButton(stringResource(R.string.home_import), { pickFile.launch(arrayOf("audio/*", "video/*")) }, enabled = !busy)
        BigButton(stringResource(R.string.home_record_mic), { withMic(device = false) }, enabled = !busy)
        BigButton(stringResource(R.string.home_record_device), { showDeviceNotice = true }, enabled = !busy)
        // Most pickers give MusicXML no type of its own, so the wildcard has to be there too.
        BigButton(
            stringResource(R.string.home_open_score),
            { pickScore.launch(arrayOf("application/vnd.recordare.musicxml+xml", "application/vnd.recordare.musicxml", "application/xml", "text/xml", "application/octet-stream", "*/*")) },
            enabled = !busy,
            primary = false,
        )
        if (vm.container.hasFixtures) BigButton(stringResource(R.string.home_sample), vm::openSample, enabled = !busy, primary = false)
        Spacer(Modifier.height(8.dp))
        SubHeading(stringResource(R.string.home_companion))
        Text(
            when {
                vm.container.usingFixture -> stringResource(R.string.companion_status_fixture)
                vm.container.settings.paired -> stringResource(R.string.companion_status_connected, vm.container.engineLabel())
                else -> stringResource(R.string.companion_status_none)
            },
        )
        BigButton(stringResource(R.string.companion_title), { vm.navigate(Screen.COMPANION) }, primary = false)
        BigButton(stringResource(R.string.home_about), { vm.navigate(Screen.ABOUT) }, primary = false)
    }

    if (showDeviceNotice) {
        AlertDialog(
            onDismissRequest = { showDeviceNotice = false },
            title = { Text(stringResource(R.string.device_notice_title)) },
            text = { Text(stringResource(R.string.device_notice)) },
            confirmButton = {
                TextButton(onClick = { showDeviceNotice = false; withMic(device = true) }, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text(stringResource(R.string.device_start))
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeviceNotice = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.cancel)) }
            },
        )
    }
}

@Composable
fun RecordScreen(vm: PlayViewModel) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by CaptureController.state.collectAsState()
    val kind by CaptureController.kind.collectAsState()
    val failed by CaptureController.failed.collectAsState()
    val status by vm.status.collectAsState()
    val t = LocalPlayTokens.current
    val device = kind == CaptureKind.DEVICE
    val started = stringResource(R.string.record_started)
    androidx.compose.runtime.LaunchedEffect(state.recording) { if (state.recording) vm.status.value = no.brasscribe.play.Status(started) }

    val levelWord = stringResource(
        when {
            state.level < 0.001f -> R.string.level_silent
            state.level < 0.05f -> R.string.level_low
            state.level < 0.9f -> R.string.level_good
            else -> R.string.level_loud
        },
    )
    PlayScaffold(
        title = stringResource(if (device) R.string.record_title_device else R.string.record_title_mic),
        onBack = { scope.launch { CaptureController.stop(context) }; vm.back() },
        status = status,
    ) {
        if (failed) {
            Text(stringResource(R.string.record_failed), color = t.error)
            return@PlayScaffold
        }
        Text(
            vm.durationText(state.seconds),
            style = MaterialTheme.typography.displaySmall,
            modifier = Modifier.semantics { contentDescription = vm.durationText(state.seconds) },
        )
        val label = stringResource(R.string.record_level)
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label)
            LinearProgressIndicator(
                progress = { state.level.coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth().height(12.dp).semantics {
                    contentDescription = label
                    stateDescription = levelWord
                    progressBarRangeInfo = ProgressBarRangeInfo(state.level.coerceIn(0f, 1f), 0f..1f)
                },
            )
            Text(levelWord, color = t.textMuted)
        }
        if (device && state.recording && state.silentFor > 5.0) {
            Text(
                stringResource(R.string.device_silent),
                color = t.error,
                modifier = Modifier.padding(vertical = 8.dp).semantics { liveRegion = LiveRegionMode.Assertive },
            )
        }
        if (!state.recording && !failed) CircularProgressIndicator()
        BigButton(stringResource(R.string.record_stop), {
            scope.launch {
                val audio = CaptureController.stop(context) ?: return@launch
                vm.recorded(audio, if (device) SourceKind.DEVICE else SourceKind.MICROPHONE)
            }
        }, enabled = state.recording)
    }
}
