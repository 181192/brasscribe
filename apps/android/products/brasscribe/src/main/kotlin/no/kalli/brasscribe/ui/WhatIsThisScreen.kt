package no.kalli.brasscribe.ui

import no.kalli.scribe.play.*

import no.kalli.brasscribe.R
import no.kalli.scribe.play.ui.*
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

private data class Choice(val profile: Profile, val title: Int, val desc: Int)

private val CHOICES = listOf(
    Choice(Profile.SOLO, R.string.profile_solo, R.string.profile_solo_desc),
    Choice(Profile.BRASS_BAND, R.string.profile_brass_band, R.string.profile_brass_band_desc),
    Choice(Profile.ORCHESTRA_WITH_SOLOIST, R.string.profile_orchestra, R.string.profile_orchestra_desc),
    Choice(Profile.POP_ROCK, R.string.profile_pop, R.string.profile_pop_desc),
)


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
    // With another interface version on the computer nothing goes there, and the card says which of the two to update.
    val connection by vm.connection.state.collectAsState()
    val update = (connection as? no.kalli.scribe.connection.ConnectionState.NeedsUpdate)?.takeIf { !vm.container.usingFixture }
    val companionOk = vm.container.engine() != null && update == null
    val companionMissing = stringResource(update?.let { no.kalli.scribe.play.ErrorWords.update(it.update) } ?: R.string.where_companion_missing)
    // A drummer's solo take is no drum part: One instrument is refused for the percussion seat, with why and what to do.
    val drummer = no.kalli.scribe.play.percussionSeat(vm.container.seat, vm.container.seats)
    val ready = profile != null && !(drummer && profile == Profile.SOLO) &&
        ((where == Where.DEVICE && deviceOk) || (where == Where.COMPANION && companionOk))

    PlayScaffold(
        title = source?.let { s -> if (s.durationS > 0) "${s.name} · ${clock(s.durationS)}" else s.name },
        onBack = vm::back, backLabel = stringResource(R.string.home), status = status,
        bottom = {
            if (profile == null) Text(stringResource(R.string.profile_choose_one), style = MaterialTheme.typography.bodyMedium,
                color = ScribeTheme.colors.textMuted)
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
            OutlineButton(stringResource(R.string.change_what_i_play), { vm.openSeatPicker(no.kalli.scribe.play.SeatPickerMode.SETTINGS) })
        }
        Text(stringResource(R.string.profile_not_sure), style = MaterialTheme.typography.bodyMedium, color = ScribeTheme.colors.textMuted)
        if (profile != null) {
            val onPhone = where == Where.DEVICE
            RowGroup {
                ListRow(
                    stringResource(no.kalli.scribe.play.OnDeviceRouting.whereTitle(profile, where)),
                    onClick = null,
                    icon = if (onPhone) DesignR.drawable.ic_bc_record_mic else DesignR.drawable.ic_bc_computer,
                    subtitle = if (onPhone) stringResource(no.kalli.scribe.play.OnDeviceRouting.deviceSubtitle(profile))
                    else if (companionOk) stringResource(R.string.where_companion_desc, vm.container.engineLabel())
                    else companionMissing,
                    chevron = false,
                    trailing = if (largeText()) null else ({ OutlineButton(stringResource(R.string.change), { changeWhere = true }, fill = false) }),
                )
                // Large text: Change goes under the card's text so the text keeps its width.
                if (largeText()) OutlineButton(stringResource(R.string.change), { changeWhere = true },
                    Modifier.padding(start = ScribeSpace.s4, end = ScribeSpace.s4, bottom = ScribeSpace.s3))
            }
        }
    }

    if (changeWhere) {
        PlaySheet({ changeWhere = false }, ScribeTheme.colors.surfaceRaised, dragHandle = false) {
            Column(Modifier.padding(horizontal = ScreenMargin).padding(bottom = ScribeSpace.s6),
                verticalArrangement = Arrangement.spacedBy(ScribeSpace.s3)) {
                SubHeading(stringResource(R.string.where_title))
                val deviceDesc = no.kalli.scribe.play.OnDeviceRouting.deviceCard(profile, vm.container.hasPitchModel,
                    vm.container.hasBandModels, source?.audio != null)
                ChoiceGroup(2) {
                    // A take too long to hold in memory is kept on disk only; the phone cannot make its score.
                    val deviceText = deviceDesc?.let { stringResource(it) } ?: phoneMinutes().let { androidx.compose.ui.res.pluralStringResource(R.plurals.where_device_too_long, it, it) }
                    ChoiceCard(stringResource(R.string.where_device), deviceText, where == Where.DEVICE, deviceOk, 0) {
                        vm.where.value = Where.DEVICE; changeWhere = false
                    }
                    ChoiceCard(
                        stringResource(R.string.where_companion),
                        if (companionOk) stringResource(R.string.where_companion_desc, vm.container.engineLabel()) else companionMissing,
                        where == Where.COMPANION, companionOk, 1,
                    ) { vm.where.value = Where.COMPANION; changeWhere = false }
                }
            }
        }
    }
}
