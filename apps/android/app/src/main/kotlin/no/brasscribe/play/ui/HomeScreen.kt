package no.brasscribe.play.ui

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import androidx.activity.compose.ManagedActivityResultLauncher
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.focus.focusRequester
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import no.brasscribe.play.audio.TakeSink
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.launch
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.Problem
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.SourceKind
import no.brasscribe.play.capture.CaptureController
import no.brasscribe.play.capture.CaptureKind
import no.brasscribe.play.model.Uncertainty

/**
 * The ways to record: the microphone, or other apps' playback (after the notice and MediaProjection
 * consent). Permissions are asked when first needed, not up front.
 */
class Recorder(val startMicrophone: () -> Unit, val askDevice: () -> Unit)

@Composable
fun rememberRecorder(vm: PlayViewModel): Recorder {
    val context = LocalContext.current
    var showDeviceNotice by remember { mutableStateOf(false) }
    var pendingDevice by remember { mutableStateOf(false) }
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

    if (showDeviceNotice) {
        AlertDialog(
            onDismissRequest = { showDeviceNotice = false },
            title = { Text(stringResource(R.string.device_notice_title)) },
            text = { Text(stringResource(R.string.device_notice)) },
            confirmButton = { PlainButton(stringResource(R.string.device_start), { showDeviceNotice = false; withMic(device = true) }) },
            dismissButton = { PlainButton(stringResource(R.string.cancel), { showDeviceNotice = false }) },
        )
    }
    return remember(vm) { Recorder({ withMic(device = false) }, { showDeviceNotice = true }) }
}

@Composable
fun rememberFilePicker(vm: PlayViewModel): ManagedActivityResultLauncher<Array<String>, android.net.Uri?> =
    rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(vm::importUri) }

val AUDIO_TYPES = arrayOf("audio/*", "video/*")

@Composable
fun HomeScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val busy by vm.busy.collectAsState()
    val scores by vm.scores.collectAsState()
    val opening by vm.openingScore.collectAsState()
    val c = BrasscribeTheme.colors
    val pickFile = rememberFilePicker(vm)
    val pickScore = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(vm::openScoreUri) }
    val recorder = rememberRecorder(vm)
    LaunchedEffect(Unit) { vm.refreshComputerScores() }
    // Back from a music stand opened from the library: focus on that score's row (music-stand.md section 6).
    val focusEntry by vm.focusEntry.collectAsState()
    val rowFocus = remember { androidx.compose.ui.focus.FocusRequester() }
    val closed = stringResource(R.string.stand_left)
    LaunchedEffect(focusEntry) {
        if (focusEntry == null) return@LaunchedEffect
        vm.status.value = no.brasscribe.play.Status(closed, quiet = true)
        runCatching { rowFocus.requestFocus() }
        vm.focusEntry.value = null
    }

    Scaffold(containerColor = c.bg) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(horizontal = ScreenMargin),
            verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4),
        ) {
            // The lockup: the mark and the wordmark in the display face, and Settings.
            Row(Modifier.fillMaxWidth().padding(top = BrasscribeSpace.s2), verticalAlignment = Alignment.CenterVertically) {
                BrandMark(36.dp)
                Spacer(Modifier.size(BrasscribeSpace.s2))
                Text(stringResource(R.string.brand_name), style = MaterialTheme.typography.headlineMedium.copy(fontFamily = MaterialTheme.typography.displaySmall.fontFamily),
                    modifier = Modifier.weight(1f))
                IconButton({ vm.navigate(Screen.HELP) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_help, stringResource(R.string.help)) }
                IconButton({ vm.navigate(Screen.SETTINGS) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_settings, stringResource(R.string.settings)) }
            }
            Text(
                buildAnnotatedString {
                    append(stringResource(R.string.home_hero_start))
                    withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = c.brassText)) { append(stringResource(R.string.home_hero_end)) }
                },
                style = MaterialTheme.typography.displaySmall,
                modifier = Modifier.padding(top = BrasscribeSpace.s4).semantics { heading() },
            )
            Lead(stringResource(R.string.home_tagline))
            ConnectionStatusRow(vm)
            StatusLine(status)
            val importProgress by vm.importProgress.collectAsState()
            if (busy) importProgress.let { p ->
                if (p != null && p > 0f) LinearProgressIndicator(progress = { p }, modifier = Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border, drawStopIndicator = {})
                else LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
            }
            PrimaryButton(stringResource(R.string.home_import), { pickFile.launch(AUDIO_TYPES) }, enabled = !busy, icon = R.drawable.ic_bc_import_file)
            RowGroup {
                ListRow(stringResource(R.string.home_record_mic), recorder.startMicrophone, icon = R.drawable.ic_bc_record_mic,
                    subtitle = stringResource(R.string.home_record_mic_desc), enabled = !busy)
                RowDivider()
                ListRow(stringResource(R.string.home_record_device), recorder.askDevice, icon = R.drawable.ic_bc_record_device,
                    subtitle = stringResource(R.string.home_record_device_desc), enabled = !busy)
                RowDivider()
                // Most pickers give MusicXML no type of its own, so the wildcard has to be there too.
                ListRow(stringResource(R.string.home_open_score), {
                    pickScore.launch(arrayOf("application/vnd.recordare.musicxml+xml", "application/vnd.recordare.musicxml", "application/xml", "text/xml", "application/octet-stream", "*/*"))
                }, icon = R.drawable.ic_bc_file, subtitle = stringResource(R.string.home_open_score_desc), enabled = !busy)
            }
            InfoNote(stringResource(R.string.home_links_tip), boxed = false)
            SectionLabel(stringResource(R.string.home_your_scores))
            if (scores.isEmpty()) {
                // Empty state: what will appear here, with the mark.
                Row(Modifier.padding(vertical = BrasscribeSpace.s2), verticalAlignment = Alignment.CenterVertically) {
                    BrandMark(32.dp)
                    Spacer(Modifier.size(BrasscribeSpace.s3))
                    Text(stringResource(R.string.home_scores_empty), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
                }
            } else {
                RowGroup {
                    scores.forEachIndexed { index, entry ->
                        if (index > 0) RowDivider()
                        ListRow(
                            no.brasscribe.play.ScoreTitles.display(entry.title, entry.updated),
                            { vm.openEntry(entry) },
                            if (entry.id == focusEntry) Modifier.focusRequester(rowFocus) else Modifier,
                            subtitle = if (opening == entry.id) stringResource(R.string.opening_score) else scoreSubtitle(entry),
                            icon = if (entry.onComputer) R.drawable.ic_bc_computer else R.drawable.ic_bc_score,
                            chevron = false,
                            enabled = opening == null,
                            trailing = { ScoreOptionsButton(vm, entry) },
                        )
                    }
                }
            }
            Spacer(Modifier.height(BrasscribeSpace.s4))
        }
    }
}

/** First launch only: three points and Get started (system.md §5, onboarding). No carousel. */
@Composable
fun FirstRunScreen(vm: PlayViewModel) {
    val c = BrasscribeTheme.colors
    Scaffold(
        containerColor = c.bg,
        bottomBar = {
            Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s3),
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                InfoNote(stringResource(R.string.first_run_privacy), boxed = false)
                PrimaryButton(stringResource(R.string.first_run_start), vm::finishFirstRun)
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(bottom = padding.calculateBottomPadding()).verticalScroll(rememberScrollState())) {
            Column(
                Modifier.fillMaxWidth().background(c.brassTint).statusBarsPadding().padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s8),
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s6),
            ) {
                BrandMark(56.dp)
                Text(
                    buildAnnotatedString {
                        append(stringResource(R.string.first_run_hero_start))
                        withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = c.brassText)) { append(stringResource(R.string.first_run_hero_end)) }
                    },
                    style = MaterialTheme.typography.displaySmall,
                    modifier = Modifier.semantics { heading() },
                )
            }
            Column(Modifier.padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s6), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s6)) {
                FirstRunPoint(R.drawable.ic_bc_record_mic, R.string.first_run_1_title, R.string.first_run_1_text)
                FirstRunPoint(R.drawable.ic_bc_next_uncertain, R.string.first_run_2_title, R.string.first_run_2_text, tint = c.veryUncertain)
                FirstRunPoint(R.drawable.ic_bc_play_along, R.string.first_run_3_title, R.string.first_run_3_text)
            }
        }
    }
}

@Composable
private fun FirstRunPoint(icon: Int, title: Int, text: Int, tint: androidx.compose.ui.graphics.Color = androidx.compose.ui.graphics.Color.Unspecified) {
    Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4), modifier = Modifier.semantics(mergeDescendants = true) {}) {
        IconWell(icon, 44.dp, tint)
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
            Text(stringResource(title), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(text), style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
        }
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
    val t = BrasscribeTheme.colors
    val device = kind == CaptureKind.DEVICE
    val started = stringResource(R.string.record_started)
    LaunchedEffect(state.recording) { if (state.recording) vm.status.value = no.brasscribe.play.Status(started) }
    LaunchedEffect(failed) { if (failed) vm.showProblem(Problem.RECORDING_FAILED) }

    val levelWord = stringResource(
        when {
            state.level < 0.001f -> R.string.level_silent
            state.level < 0.05f -> R.string.level_low
            state.level < 0.9f -> R.string.level_good
            else -> R.string.level_loud
        },
    )
    var stopping by remember { mutableStateOf(false) }
    fun finish() {
        if (stopping) return
        stopping = true
        scope.launch {
            val silent = device && state.silentFor >= state.seconds - 1.0
            val take = CaptureController.stop(context) ?: return@launch
            if (silent) { take.file.delete(); vm.showProblem(Problem.NOTHING_HEARD) }
            else vm.recorded(take, if (device) SourceKind.DEVICE else SourceKind.MICROPHONE)
        }
    }
    // At the length limit the take ends as if Stop was pressed.
    LaunchedEffect(state.full) { if (state.full) finish() }
    PlayScaffold(
        title = null,
        onBack = { scope.launch { CaptureController.discard(context) }; vm.back() },
        backLabel = stringResource(R.string.home),
        status = status,
        bottom = {
            PrimaryButton(stringResource(R.string.record_stop), { finish() }, enabled = state.recording && !stopping, icon = R.drawable.ic_bc_stop)
        },
    ) {
        ScreenTitle(stringResource(if (device) R.string.record_title_device else R.string.record_title_mic))
        Text(
            vm.durationText(state.seconds),
            style = no.brasscribe.design.BrasscribeNumericStyle.copy(fontSize = MaterialTheme.typography.headlineMedium.fontSize),
            modifier = Modifier.semantics { contentDescription = vm.durationText(state.seconds) },
        )
        val hours = (TakeSink.MAX_TAKE_SECONDS / 3600).toInt()
        Text(androidx.compose.ui.res.pluralStringResource(R.plurals.record_limit, hours, hours), color = t.textMuted)
        val label = stringResource(R.string.record_level)
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
            Text(label, style = MaterialTheme.typography.titleMedium)
            LinearProgressIndicator(
                progress = { state.level.coerceIn(0f, 1f) },
                color = t.brass, trackColor = t.border,
                modifier = Modifier.fillMaxWidth().heightIn(min = 8.dp).semantics {
                    contentDescription = label
                    stateDescription = levelWord
                    progressBarRangeInfo = ProgressBarRangeInfo(state.level.coerceIn(0f, 1f), 0f..1f)
                },
            )
            Text(levelWord, color = t.textMuted)
        }
        // Past what the phone holds in memory the take is kept on disk only: the engine makes its score.
        if (state.recording && !state.fitsPhone && vm.container.hasPitchModel) {
            val minutes = phoneMinutes()
            InfoNote(androidx.compose.ui.res.pluralStringResource(R.plurals.record_past_phone_limit, minutes, minutes),
                Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        }
        if (device && state.recording && state.silentFor > 5.0) {
            InfoNote(stringResource(R.string.device_silent), Modifier.semantics { liveRegion = LiveRegionMode.Assertive }, icon = R.drawable.ic_bc_error)
        }
    }
}

/** Whole minutes of a 48 kHz take the phone keeps in memory to make its score itself. */
fun phoneMinutes(): Int = (no.brasscribe.play.audio.AudioDecoder.maxSamplesInMemory / (48_000L * 60)).toInt()
