package no.brasscribe.play.ui

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
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Step
import no.brasscribe.play.Where
import no.brasscribe.play.engine.Profile

private data class Choice(val profile: Profile, val title: Int, val desc: Int)

private val CHOICES = listOf(
    Choice(Profile.SOLO, R.string.profile_solo, R.string.profile_solo_desc),
    Choice(Profile.BRASS_BAND, R.string.profile_brass_band, R.string.profile_brass_band_desc),
    Choice(Profile.ORCHESTRA_WITH_SOLOIST, R.string.profile_orchestra, R.string.profile_orchestra_desc),
    Choice(Profile.POP_ROCK, R.string.profile_pop, R.string.profile_pop_desc),
)

/**
 * One choice card: title, one sentence and a radio, announced as "n of m". Chosen cards get a 2 dp
 * ink ring (system.md §5, the chooser), so the state is never colour alone.
 *
 * With a [disabledReason] the card is unavailable but stays focusable, so a screen reader still reaches
 * it: the reason replaces the description line, is its state, and a tap does nothing.
 */
@Composable
fun ChoiceCard(title: String, desc: String?, selected: Boolean, enabled: Boolean, index: Int, disabledReason: String? = null, onClick: () -> Unit) {
    val c = BrasscribeTheme.colors
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
            .padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3),
        verticalAlignment = Alignment.Top,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = if (available) c.text else c.textMuted)
            val line = disabledReason ?: desc
            // The reason is already the card's state: not read twice.
            if (line != null) Text(line, style = MaterialTheme.typography.bodyMedium, color = c.textMuted,
                modifier = if (disabledReason != null) Modifier.clearAndSetSemantics { } else Modifier)
        }
        // The radio has its own column, top-aligned, so large text never runs under it (review 3, P2-D).
        Box(Modifier.padding(start = BrasscribeSpace.s2).width(40.dp), contentAlignment = Alignment.TopEnd) {
            RadioButton(selected = selected, onClick = null, enabled = available,
                colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
        }
    }
}

@Composable
fun ChoiceGroup(count: Int, content: @Composable () -> Unit) {
    Column(
        Modifier.selectableGroup().semantics { collectionInfo = CollectionInfo(count, 1) },
        verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
    ) { content() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val profile by vm.profile.collectAsState()
    val where by vm.where.collectAsState()
    val source by vm.source.collectAsState()
    val headingFocus = remember { FocusRequester() }
    var changeWhere by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { runCatching { headingFocus.requestFocus() } }
    val deviceOk = vm.canTranscribeOnDevice()
    val companionOk = vm.container.engine() != null
    // A drummer's solo take is no drum part: One instrument is refused for the percussion seat, with why and what to do.
    val drummer = no.brasscribe.play.percussionSeat(vm.container.seat, vm.container.seats)
    val ready = profile != null && !(drummer && profile == Profile.SOLO) &&
        ((where == Where.DEVICE && deviceOk) || (where == Where.COMPANION && companionOk))

    PlayScaffold(
        title = source?.let { s -> if (s.durationS > 0) "${s.name} · ${clock(s.durationS)}" else s.name },
        onBack = vm::back, backLabel = stringResource(R.string.home), status = status,
        bottom = {
            if (profile == null) Text(stringResource(R.string.profile_choose_one), style = MaterialTheme.typography.bodyMedium,
                color = BrasscribeTheme.colors.textMuted)
            PrimaryButton(stringResource(R.string.continue_label), vm::startTranscription, enabled = ready, modifier = Modifier.semantics { testTag = "continue" })
        },
    ) {
        ScreenTitle(stringResource(R.string.profile_title), Modifier.focusRequester(headingFocus).focusable())
        Lead(stringResource(R.string.profile_hint))
        ChoiceGroup(CHOICES.size) {
            CHOICES.forEachIndexed { i, c ->
                val refused = drummer && c.profile == Profile.SOLO
                ChoiceCard(stringResource(c.title), stringResource(c.desc), profile == c.profile, true, i,
                    stringResource(R.string.profile_solo_percussion).takeIf { refused }) { vm.chooseProfile(c.profile) }
            }
        }
        if (drummer) {
            InfoNote(stringResource(R.string.percussion_solo_refused), Modifier.semantics { testTag = "percussion-solo" })
            OutlineButton(stringResource(R.string.change_what_i_play), { vm.openSeatPicker(no.brasscribe.play.SeatPickerMode.SETTINGS) })
        }
        Text(stringResource(R.string.profile_not_sure), style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
        if (profile != null) {
            val onPhone = where == Where.DEVICE
            RowGroup {
                ListRow(
                    stringResource(if (onPhone) R.string.where_device else R.string.where_companion),
                    onClick = null,
                    icon = if (onPhone) R.drawable.ic_bc_record_mic else R.drawable.ic_bc_computer,
                    subtitle = if (onPhone) stringResource(R.string.where_device_desc)
                    else if (companionOk) stringResource(R.string.where_companion_desc, vm.container.engineLabel())
                    else stringResource(R.string.where_companion_missing),
                    chevron = false,
                    trailing = if (largeText()) null else ({ OutlineButton(stringResource(R.string.change), { changeWhere = true }, fill = false) }),
                )
                // Large text: Change goes under the card's text so the text keeps its width.
                if (largeText()) OutlineButton(stringResource(R.string.change), { changeWhere = true },
                    Modifier.padding(start = BrasscribeSpace.s4, end = BrasscribeSpace.s4, bottom = BrasscribeSpace.s3))
            }
        }
    }

    if (changeWhere) {
        PlaySheet({ changeWhere = false }, BrasscribeTheme.colors.surfaceRaised, dragHandle = false) {
            Column(Modifier.padding(horizontal = ScreenMargin).padding(bottom = BrasscribeSpace.s6),
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                SubHeading(stringResource(R.string.where_title))
                val deviceDesc = when {
                    profile != Profile.SOLO -> R.string.where_device_solo_only
                    !vm.container.hasPitchModel -> R.string.where_device_unavailable
                    source?.audio == null -> null
                    else -> R.string.where_device_desc
                }
                ChoiceGroup(2) {
                    // A take too long to hold in memory is kept on disk only; the phone cannot make its score.
                    val deviceText = deviceDesc?.let { stringResource(it) } ?: phoneMinutes().let { androidx.compose.ui.res.pluralStringResource(R.plurals.where_device_too_long, it, it) }
                    ChoiceCard(stringResource(R.string.where_device), deviceText, where == Where.DEVICE, deviceOk, 0) {
                        vm.where.value = Where.DEVICE; changeWhere = false
                    }
                    ChoiceCard(
                        stringResource(R.string.where_companion),
                        if (companionOk) stringResource(R.string.where_companion_desc, vm.container.engineLabel()) else stringResource(R.string.where_companion_missing),
                        where == Where.COMPANION, companionOk, 1,
                    ) { vm.where.value = Where.COMPANION; changeWhere = false }
                }
            }
        }
    }
}

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
    val c = BrasscribeTheme.colors
    var confirmCancel by remember { mutableStateOf(false) }
    val percent = (s.fraction * 100).toInt()
    val eta = when {
        s.etaSeconds == null -> stringResource(R.string.eta_unknown)
        s.etaSeconds!! < 60 -> stringResource(R.string.eta_under_minute)
        else -> pluralStringResource(R.plurals.eta_minutes, (s.etaSeconds!! + 30) / 60, (s.etaSeconds!! + 30) / 60)
    }
    val stepText = stringResource(s.step.text)
    val steps = s.steps.ifEmpty { listOf(s.step) }
    val current = steps.indexOf(s.step).coerceAtLeast(0)
    // Announce each new step once, politely, rather than every percent.
    LaunchedEffect(s.step) { if (s.running) vm.status.value = no.brasscribe.play.Status(stepText) }

    PlayScaffold(
        // The step title is the live region here; the status line would only repeat it.
        title = source?.name?.substringBeforeLast('.'), onBack = vm::back, backLabel = stringResource(R.string.home), status = null,
        bottom = {
            InfoNote(stringResource(R.string.transcribe_leave, s.where), icon = if (s.where == stringResource(R.string.transcribe_where_device)) R.drawable.ic_bc_info else R.drawable.ic_bc_computer)
            OutlineButton(stringResource(R.string.cancel), { confirmCancel = true }, enabled = s.running)
        },
    ) {
        BrandMark(48.dp)
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
            SectionLabel(stringResource(R.string.step_of, current + 1, steps.size))
            ScreenTitle(stepText, Modifier.semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite })
        }
        val label = stringResource(R.string.transcribe_progress_label)
        val percentText = stringResource(R.string.progress_percent, percent)
        LinearProgressIndicator(
            progress = { s.fraction.toFloat() },
            color = c.brass, trackColor = c.border, drawStopIndicator = {},
            modifier = Modifier.fillMaxWidth().heightIn(min = 8.dp).semantics {
                contentDescription = label
                stateDescription = percentText
                progressBarRangeInfo = ProgressBarRangeInfo(s.fraction.toFloat(), 0f..1f)
            },
        )
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text(percentText, style = no.brasscribe.design.BrasscribeNumericStyle, color = c.textMuted)
            Text(eta, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4)) {
            steps.forEachIndexed { i, step ->
                StepRow(stringResource(step.text), done = i < current, now = i == current)
            }
        }
    }

    if (confirmCancel) {
        AlertDialog(
            onDismissRequest = { confirmCancel = false },
            title = { Text(stringResource(R.string.transcribe_cancel_title)) },
            text = { Text(stringResource(R.string.transcribe_cancel_text)) },
            confirmButton = { PlainButton(stringResource(R.string.transcribe_cancel_confirm), { confirmCancel = false; vm.cancelTranscription(); vm.back() }) },
            dismissButton = { PlainButton(stringResource(R.string.transcribe_cancel_keep), { confirmCancel = false }) },
        )
    }
}

@Composable
private fun StepRow(text: String, done: Boolean, now: Boolean) {
    val c = BrasscribeTheme.colors
    val state = stringResource(when { done -> R.string.step_done; now -> R.string.step_now; else -> R.string.step_waiting })
    Row(
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
        modifier = Modifier.semantics(mergeDescendants = true) { stateDescription = state },
    ) {
        Box(
            Modifier.size(24.dp)
                .background(if (done) c.text else c.bg, androidx.compose.foundation.shape.CircleShape)
                .border(2.dp, if (done || now) c.text else c.borderStrong, androidx.compose.foundation.shape.CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            if (done) BcIcon(R.drawable.ic_bc_done, null, Modifier.size(16.dp), tint = c.bg)
            else if (now) Box(Modifier.size(10.dp).background(c.text, androidx.compose.foundation.shape.CircleShape))
        }
        Text(text, style = MaterialTheme.typography.bodyLarge.copy(fontWeight = if (now) FontWeight.SemiBold else FontWeight.Normal),
            color = if (now) c.text else c.textMuted)
    }
}
