package no.kalli.scribe.play.ui

import no.kalli.scribe.play.R

import no.kalli.scribe.design.R as DesignR

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CollectionInfo
import androidx.compose.ui.semantics.CollectionItemInfo
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.collectionInfo
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.collectionItemInfo
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.Step
import no.kalli.scribe.play.Where
import no.kalli.scribe.engine.Profile

/**
 * One choice card: title, one sentence and a radio, announced as "n of m". Chosen cards get a 2 dp
 * ink ring (system.md §5, the chooser), so the state is never colour alone.
 *
 * With a [disabledReason] the card is unavailable but stays focusable, so a screen reader still reaches
 * it: the reason replaces the description line, is its state, and a tap does nothing.
 */
@Composable
fun ChoiceCard(title: String, desc: String?, selected: Boolean, enabled: Boolean, index: Int, disabledReason: String? = null, onClick: () -> Unit) {
    val c = ScribeTheme.colors
    val available = enabled && disabledReason == null
    Row(
        Modifier.fillMaxWidth().heightIn(min = 64.dp)
            .background(c.surfaceRaised, MaterialTheme.shapes.large)
            .border(if (selected) 2.dp else 1.dp, if (selected) c.text else c.borderStrong, MaterialTheme.shapes.large)
            .selectable(selected = selected, enabled = enabled, role = Role.RadioButton, onClick = { if (available) onClick() })
            .semantics {
                collectionItemInfo = CollectionItemInfo(index, 1, 0, 1)
                if (disabledReason != null) { disabled(); stateDescription = disabledReason }
            }
            .padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s3),
        verticalAlignment = Alignment.Top,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = if (available) c.text else c.textMuted)
            val line = disabledReason ?: desc
            // The reason is already the card's state: not read twice.
            if (line != null) Text(line, style = MaterialTheme.typography.bodyMedium, color = c.textMuted,
                modifier = if (disabledReason != null) Modifier.clearAndSetSemantics { } else Modifier)
        }
        // The radio has its own column, top-aligned, so large text never runs under it (review 3, P2-D).
        Box(Modifier.padding(start = ScribeSpace.s2).width(40.dp), contentAlignment = Alignment.TopEnd) {
            RadioButton(selected = selected, onClick = null, enabled = available,
                colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
        }
    }
}

@Composable
fun ChoiceGroup(count: Int, content: @Composable () -> Unit) {
    Column(
        Modifier.selectableGroup().semantics { collectionInfo = CollectionInfo(count, 1) },
        verticalArrangement = Arrangement.spacedBy(ScribeSpace.s3),
    ) { content() }
}

@OptIn(ExperimentalMaterial3Api::class)
/** "4:12" for a duration in seconds. */
fun clock(seconds: Double): String {
    val t = seconds.toInt()
    return "%d:%02d".format(t / 60, t % 60)
}

@Composable
fun TranscribeScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val s by vm.transcribe.collectAsState()
    val source by vm.source.collectAsState()
    val c = ScribeTheme.colors
    var confirmCancel by remember { mutableStateOf(false) }
    val percent = (s.fraction * 100).toInt()
    val onPhone = s.where == stringResource(R.string.transcribe_where_device) || s.where == stringResource(R.string.transcribe_where_device_draft)
    // The step and the percentage only, where the estimate would be wrong: for a product whose jobs it is wrong
    // for, and for a job on the computer, whose stages differ too much in length (it only moves when one ends).
    val eta = when {
        !vm.container.product.timeLeft || !onPhone -> null
        s.etaSeconds == null -> stringResource(R.string.eta_unknown)
        s.etaSeconds!! < 60 -> stringResource(R.string.eta_under_minute)
        else -> pluralStringResource(R.plurals.eta_minutes, (s.etaSeconds!! + 30) / 60, (s.etaSeconds!! + 30) / 60)
    }
    val stepText = stringResource(s.step.text)
    val steps = s.steps.ifEmpty { listOf(s.step) }
    val current = steps.indexOf(s.step).coerceAtLeast(0)
    // Where the product asks for it (Product.keepOpenWhileWriting), the screen stays on while this runs. A draft on
    // the phone goes on in its service when the player leaves the app, so the screen may sleep.
    if (vm.container.product.keepOpenWhileWriting && s.running && !s.draft) {
        val view = androidx.compose.ui.platform.LocalView.current
        androidx.compose.runtime.DisposableEffect(view) {
            view.keepScreenOn = true
            onDispose { view.keepScreenOn = false }
        }
    }
    // A job on the computer goes on when the player leaves the app, and the app says when it is done: notifications are
    // asked for here, at the first such job (never at the first run), once.
    val onComputer = s.running && !onPhone && !s.draft
    val context = androidx.compose.ui.platform.LocalContext.current
    var notifies by remember { mutableStateOf(no.kalli.scribe.play.JobNotices.allowed(context)) }
    val askToNotify = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission(),
    ) { notifies = no.kalli.scribe.play.JobNotices.allowed(context) }
    // One question at a time: while the phone asks about the local network, a second question would be dropped unseen.
    val otherQuestion = no.kalli.scribe.connection.LocalNetwork.asking
    LaunchedEffect(onComputer, otherQuestion) {
        if (!onComputer || notifies || otherQuestion || vm.container.notificationsAsked) return@LaunchedEffect
        vm.container.notificationsAsked = true
        askToNotify.launch(android.Manifest.permission.POST_NOTIFICATIONS)
    }
    // Announce each new step once, politely, rather than every percent.
    LaunchedEffect(s.step) { if (s.running) vm.status.value = no.kalli.scribe.play.Status(stepText) }
    // Back (the gesture or the top bar's button) asks first, as Cancel does: a stray swipe never ends a job of minutes.
    fun leave() { if (s.running) confirmCancel = true else vm.back() }
    androidx.activity.compose.BackHandler(enabled = s.running) { leave() }

    PlayScaffold(
        // The step title is the live region here; the status line would only repeat it.
        title = source?.name?.substringBeforeLast('.'), onBack = ::leave, backLabel = stringResource(R.string.home), status = null,
        bottom = {
            val leave = when {
                s.draft -> R.string.transcribe_leave_draft
                onPhone -> R.string.transcribe_leave
                notifies -> R.string.transcribe_leave_computer
                else -> R.string.transcribe_leave_computer_quiet
            }
            InfoNote(stringResource(leave, s.where),
                icon = if (onPhone) DesignR.drawable.ic_bc_info else DesignR.drawable.ic_bc_computer)
            OutlineButton(stringResource(R.string.cancel), { confirmCancel = true }, enabled = s.running)
        },
    ) {
        BrandMark(48.dp)
        Column(verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1)) {
            SectionLabel(stringResource(R.string.step_of, current + 1, steps.size))
            ScreenTitle(stepText, Modifier.semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite })
        }
        val label = stringResource(R.string.transcribe_progress_label)
        val percentText = stringResource(R.string.progress_percent, percent)
        LinearProgressIndicator(
            progress = { s.fraction.toFloat() },
            color = c.brand, trackColor = c.border, drawStopIndicator = {},
            modifier = Modifier.fillMaxWidth().heightIn(min = 8.dp).semantics {
                contentDescription = label
                stateDescription = percentText
                progressBarRangeInfo = ProgressBarRangeInfo(s.fraction.toFloat(), 0f..1f)
            },
        )
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text(percentText, style = no.kalli.scribe.design.ScribeNumericStyle, color = c.textMuted)
            if (eta != null) Text(eta, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(ScribeSpace.s4)) {
            steps.forEachIndexed { i, step ->
                StepRow(stringResource(step.text), done = i < current, now = i == current)
            }
        }
    }

    if (confirmCancel) {
        AlertDialog(
            onDismissRequest = { confirmCancel = false },
            title = { Text(stringResource(R.string.transcribe_cancel_title)) },
            text = { Text(stringResource(if (vm.container.product.keepsRecordings) R.string.transcribe_cancel_text_kept else R.string.transcribe_cancel_text)) },
            confirmButton = { PlainButton(stringResource(R.string.transcribe_cancel_confirm), { confirmCancel = false; vm.cancelTranscription(); vm.back() }) },
            dismissButton = { PlainButton(stringResource(R.string.transcribe_cancel_keep), { confirmCancel = false }) },
        )
    }
}

@Composable
private fun StepRow(text: String, done: Boolean, now: Boolean) {
    val c = ScribeTheme.colors
    val state = stringResource(when { done -> R.string.step_done; now -> R.string.step_now; else -> R.string.step_waiting })
    Row(
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s3),
        modifier = Modifier.semantics(mergeDescendants = true) { stateDescription = state },
    ) {
        Box(
            Modifier.size(24.dp)
                .background(if (done) c.text else c.bg, androidx.compose.foundation.shape.CircleShape)
                .border(2.dp, if (done || now) c.text else c.borderStrong, androidx.compose.foundation.shape.CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            if (done) BcIcon(DesignR.drawable.ic_bc_done, null, Modifier.size(16.dp), tint = c.bg)
            else if (now) Box(Modifier.size(10.dp).background(c.text, androidx.compose.foundation.shape.CircleShape))
        }
        Text(text, style = MaterialTheme.typography.bodyLarge.copy(fontWeight = if (now) FontWeight.SemiBold else FontWeight.Normal),
            color = if (now) c.text else c.textMuted)
    }
}
