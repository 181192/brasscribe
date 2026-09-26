package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.foundation.focusable
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CollectionInfo
import androidx.compose.ui.semantics.CollectionItemInfo
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.collectionInfo
import androidx.compose.ui.semantics.collectionItemInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.paneTitle
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Where
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.ui.theme.LocalPlayTokens

private data class Choice(val profile: Profile, val title: Int, val desc: Int)

private val CHOICES = listOf(
    Choice(Profile.SOLO, R.string.profile_solo, R.string.profile_solo_desc),
    Choice(Profile.BRASS_BAND, R.string.profile_brass_band, R.string.profile_brass_band_desc),
    Choice(Profile.ORCHESTRA_WITH_SOLOIST, R.string.profile_orchestra, R.string.profile_orchestra_desc),
    Choice(Profile.POP_ROCK, R.string.profile_pop, R.string.profile_pop_desc),
)

/** One radio option with a title and a description, 56 dp tall, announced as "n of m". */
@Composable
fun RadioRow(title: String, desc: String?, selected: Boolean, enabled: Boolean, index: Int, count: Int, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp)
            .selectable(selected = selected, enabled = enabled, role = Role.RadioButton, onClick = onClick)
            .semantics { collectionItemInfo = CollectionItemInfo(index, 1, 0, 1) }
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null, enabled = enabled)
        Column(Modifier.padding(start = 12.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            if (desc != null) Text(desc, style = MaterialTheme.typography.bodyMedium, color = LocalPlayTokens.current.textMuted)
        }
    }
}

@Composable
fun ProfileScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val profile by vm.profile.collectAsState()
    val where by vm.where.collectAsState()
    val source by vm.source.collectAsState()
    val headingFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { headingFocus.requestFocus() } }

    PlayScaffold(title = source?.name ?: stringResource(R.string.profile_title), onBack = vm::back, status = status) {
        Heading(
            stringResource(R.string.profile_title),
            Modifier.focusRequester(headingFocus).focusable(),
        )
        Text(stringResource(R.string.profile_hint))
        Column(Modifier.selectableGroup().semantics { collectionInfo = CollectionInfo(CHOICES.size, 1) }) {
            CHOICES.forEachIndexed { i, c ->
                RadioRow(stringResource(c.title), stringResource(c.desc), profile == c.profile, true, i, CHOICES.size) {
                    vm.chooseProfile(c.profile)
                }
            }
        }
        if (profile != null) {
            SubHeading(stringResource(R.string.where_title))
            val deviceOk = vm.canTranscribeOnDevice()
            val companionOk = vm.container.engine() != null
            // Say why the offline choice is off, once the profile no longer explains it.
            val deviceDesc = when {
                profile != Profile.SOLO -> R.string.where_device_desc
                !vm.container.hasPitchModel -> R.string.where_device_unavailable
                source?.audio == null -> R.string.where_device_no_audio
                else -> R.string.where_device_desc
            }
            Column(Modifier.selectableGroup().semantics { collectionInfo = CollectionInfo(2, 1) }) {
                RadioRow(
                    stringResource(R.string.where_device),
                    stringResource(deviceDesc),
                    where == Where.DEVICE, deviceOk, 0, 2,
                ) { vm.where.value = Where.DEVICE }
                RadioRow(
                    stringResource(R.string.where_companion),
                    if (companionOk) vm.container.engineLabel() else stringResource(R.string.where_companion_missing),
                    where == Where.COMPANION, companionOk, 1, 2,
                ) { vm.where.value = Where.COMPANION }
            }
        }
        val ready = profile != null && ((where == Where.DEVICE && vm.canTranscribeOnDevice()) || (where == Where.COMPANION && vm.container.engine() != null))
        BigButton(stringResource(R.string.continue_label), vm::startTranscription, enabled = ready, modifier = Modifier.semantics { testTag = "continue" })
    }
}

@Composable
fun TranscribeScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val s by vm.transcribe.collectAsState()
    val t = LocalPlayTokens.current
    val percent = (s.fraction * 100).toInt()
    val eta = when {
        s.etaSeconds == null -> stringResource(R.string.eta_unknown)
        s.etaSeconds!! < 60 -> stringResource(R.string.eta_under_minute)
        else -> pluralStringResource(R.plurals.eta_minutes, (s.etaSeconds!! + 30) / 60, (s.etaSeconds!! + 30) / 60)
    }
    val stepText = stringResource(s.step.text)
    // Announce each new step once, politely, rather than every percent.
    LaunchedEffect(s.step) { if (s.running) vm.status.value = no.brasscribe.play.Status(stepText) }

    PlayScaffold(title = stringResource(R.string.transcribe_title), onBack = vm::back, status = status) {
        Heading(stringResource(R.string.transcribe_title))
        Text(s.where, color = t.textMuted)
        Text(stepText, style = MaterialTheme.typography.titleLarge)
        val label = stringResource(R.string.transcribe_progress_label)
        val percentText = stringResource(R.string.progress_percent, percent)
        LinearProgressIndicator(
            progress = { s.fraction.toFloat() },
            modifier = Modifier.fillMaxWidth().heightIn(min = 12.dp).semantics {
                contentDescription = label
                stateDescription = percentText
                progressBarRangeInfo = ProgressBarRangeInfo(s.fraction.toFloat(), 0f..1f)
            },
        )
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text(percentText)
            if (s.stepTotal > 0) Text(stringResource(R.string.step_of, minOf(s.stepIndex + 1, s.stepTotal), s.stepTotal))
        }
        Text(eta)
        s.error?.let { Text(stringResource(R.string.transcribe_failed, it), color = t.error) }
        if (s.running) BigButton(stringResource(R.string.cancel), { vm.cancelTranscription(); vm.back() }, primary = false)
        else if (s.error != null) BigButton(stringResource(R.string.back), { vm.back() }, primary = false)
    }
}
