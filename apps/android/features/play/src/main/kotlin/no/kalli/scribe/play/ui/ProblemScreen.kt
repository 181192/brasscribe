package no.kalli.scribe.play.ui

import no.kalli.scribe.play.R

import no.kalli.scribe.design.R as DesignR

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.semantics.testTag
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.Problem

private class ProblemCopy(val title: Int, val body: Int, val reasons: List<Int>, val note: Int?)

private val COPY = mapOf(
    Problem.FILE_UNREADABLE to ProblemCopy(R.string.problem_file_title, R.string.problem_file_body, listOf(R.string.problem_file_reason), null),
    Problem.NO_SOUND_TRACK to ProblemCopy(R.string.problem_no_sound_title, R.string.problem_no_sound_body, emptyList(), null),
    Problem.NOTHING_HEARD to ProblemCopy(R.string.problem_silent_title, R.string.problem_silent_body,
        listOf(R.string.problem_silent_reason_blocked, R.string.problem_silent_reason_nothing), R.string.problem_silent_note),
    Problem.RECORDING_FAILED to ProblemCopy(R.string.problem_record_title, R.string.problem_record_body, listOf(R.string.problem_record_reason), null),
    Problem.SCORE_FAILED to ProblemCopy(R.string.problem_score_title, R.string.problem_score_body, emptyList(), R.string.problem_score_kept),
    Problem.TOO_LARGE to ProblemCopy(R.string.problem_too_large_title, R.string.problem_too_large_body, listOf(R.string.problem_too_large_reason), null),
    Problem.DRAFT_TOO_LONG to ProblemCopy(R.string.draft_too_long_title, R.string.draft_too_long_body, emptyList(), R.string.draft_too_long_kept),
    Problem.DRAFT_REFUSED to ProblemCopy(R.string.draft_refused_title, R.string.draft_refused_body, emptyList(), R.string.draft_too_long_kept),
    Problem.NO_NOTES to ProblemCopy(R.string.problem_no_notes_title, R.string.problem_no_notes_body, emptyList(), null),
    Problem.SHEET_MUSIC to ProblemCopy(R.string.problem_sheet_music_title, R.string.problem_sheet_music_body, emptyList(), null),
    Problem.OPEN_FAILED to ProblemCopy(R.string.problem_open_title, R.string.problem_open_body, emptyList(), null),
)

/**
 * Errors with a way forward (system.md §5): the title says what happened, the body why in one or two
 * points, and the buttons the way out; the primary is the most likely fix. Technical detail (an
 * engine message) is only under "Details for the band's tech person".
 */
@Composable
fun ProblemScreen(vm: PlayViewModel) {
    val problem by vm.problem.collectAsState()
    val p = problem ?: Problem.SCORE_FAILED
    val copy = COPY.getValue(p)
    val c = ScribeTheme.colors
    val pickFile = rememberFilePicker(vm)
    val recorder = rememberRecorder(vm)
    var details by rememberSaveable { mutableStateOf(false) }
    // A take too long for a draft: the computer is the way forward, as soon as it is there. Back goes to
    // What is this?, where the recording still is.
    val tooLong = p == Problem.DRAFT_TOO_LONG
    // The phone would not let the draft run: later, or on the computer. Its recording is still there too.
    val draft = tooLong || p == Problem.DRAFT_REFUSED
    val connection by vm.connection.state.collectAsState()
    val source by vm.source.collectAsState()
    val computerThere = vm.container.usingFixture || no.kalli.scribe.play.OnDeviceRouting.computerThere(connection)
    val primary = Modifier.semantics { testTag = "problem-primary" }
    // Nothing is paired: trying again sends the recording to no computer, so connecting it is the way forward.
    val connectFirst = !computerThere && !vm.container.settings.paired
    val connect = @androidx.compose.runtime.Composable {
        PrimaryButton(stringResource(R.string.problem_connect_computer), { vm.navigate(no.kalli.scribe.play.Screen.COMPANION) }, primary, icon = DesignR.drawable.ic_bc_computer)
    }

    // Trying to open the score again says so when there is no computer to ask.
    val status by vm.status.collectAsState()
    PlayScaffold(
        title = null, onBack = { if (draft) vm.back() else vm.home() },
        backLabel = stringResource(if (draft) R.string.back else R.string.home), status = status.takeIf { p == Problem.OPEN_FAILED },
        bottom = {
            when (p) {
                Problem.DRAFT_REFUSED -> {
                    if (computerThere) {
                        PrimaryButton(stringResource(R.string.draft_make_on_computer), vm::makeOnComputer, primary, icon = DesignR.drawable.ic_bc_computer)
                        SecondaryButton(stringResource(R.string.retry), vm::retryTranscription, icon = DesignR.drawable.ic_bc_retry)
                    } else PrimaryButton(stringResource(R.string.retry), vm::retryTranscription, primary, icon = DesignR.drawable.ic_bc_retry)
                }
                Problem.DRAFT_TOO_LONG -> {
                    if (computerThere) PrimaryButton(stringResource(R.string.draft_make_on_computer), vm::makeOnComputer, primary, icon = DesignR.drawable.ic_bc_computer)
                    else if (connectFirst) connect()
                    SecondaryButton(stringResource(R.string.problem_choose_another_recording), { pickFile.launch(AUDIO_TYPES) }, icon = DesignR.drawable.ic_bc_import_file)
                }
                // The score needed the computer and none is paired: connect it first; Try again once it is.
                Problem.SCORE_FAILED -> if (connectFirst && vm.problemWhy == R.string.where_companion_missing) {
                    connect()
                    SecondaryButton(stringResource(R.string.retry), vm::retryTranscription, icon = DesignR.drawable.ic_bc_retry)
                } else {
                    PrimaryButton(stringResource(R.string.retry), vm::retryTranscription, primary, icon = DesignR.drawable.ic_bc_retry)
                    SecondaryButton(stringResource(R.string.back_home), vm::home)
                }
                // A score on the computer that could not be fetched: Try again opens it again.
                Problem.OPEN_FAILED -> {
                    PrimaryButton(stringResource(R.string.retry), vm::retryOpen, primary, icon = DesignR.drawable.ic_bc_retry)
                    SecondaryButton(stringResource(R.string.back_home), vm::home)
                }
                // Trying the same again finds the same: no Retry. The computer only when the phone wrote it down.
                Problem.NO_NOTES -> {
                    if (no.kalli.scribe.play.noNotesOffersComputer(vm.noNotesOnPhone, computerThere))
                        PrimaryButton(stringResource(R.string.draft_make_on_computer), vm::makeOnComputer, primary, icon = DesignR.drawable.ic_bc_computer)
                    else PrimaryButton(stringResource(R.string.problem_choose_another_recording), { pickFile.launch(AUDIO_TYPES) }, primary, icon = DesignR.drawable.ic_bc_import_file)
                    SecondaryButton(stringResource(no.kalli.scribe.play.noNotesRecordWords(source?.kind)), { vm.home(); recorder.startMicrophone() }, icon = DesignR.drawable.ic_bc_record_mic)
                }
                Problem.NOTHING_HEARD -> {
                    PrimaryButton(stringResource(R.string.problem_import_instead), { pickFile.launch(AUDIO_TYPES) }, primary, icon = DesignR.drawable.ic_bc_import_file)
                    SecondaryButton(stringResource(R.string.home_record_mic), { vm.home(); recorder.startMicrophone() }, icon = DesignR.drawable.ic_bc_record_mic)
                }
                // Nothing was wrong with the file: the ways forward are the two Home starts with.
                Problem.SHEET_MUSIC -> {
                    PrimaryButton(stringResource(R.string.home_import), { pickFile.launch(AUDIO_TYPES) }, primary, icon = DesignR.drawable.ic_bc_import_file)
                    SecondaryButton(stringResource(R.string.home_record_mic), { vm.home(); recorder.startMicrophone() }, icon = DesignR.drawable.ic_bc_record_mic)
                }
                else -> {
                    PrimaryButton(stringResource(R.string.problem_choose_another), { pickFile.launch(AUDIO_TYPES) }, primary, icon = DesignR.drawable.ic_bc_import_file)
                    SecondaryButton(stringResource(R.string.problem_record_instead), { vm.home(); recorder.startMicrophone() }, icon = DesignR.drawable.ic_bc_record_mic)
                }
            }
        },
    ) {
        Box(
            Modifier.size(56.dp).background(c.surface, MaterialTheme.shapes.large).border(1.dp, c.border, MaterialTheme.shapes.large),
            contentAlignment = Alignment.Center,
        ) { BcIcon(DesignR.drawable.ic_bc_error, null, tint = c.error) }
        ScreenTitle(stringResource(copy.title), Modifier.semantics { liveRegion = LiveRegionMode.Assertive })
        // Without the computer the words say how to get it: open Brasscribe there, and pair first when nothing is paired.
        // Nothing ran: the recording needed the computer, and none is paired.
        val needsComputer = vm.problemWhy == R.string.where_companion_missing
        val body = when {
            p == Problem.SCORE_FAILED && needsComputer && connectFirst -> R.string.problem_score_body_unpaired
            !draft || computerThere -> copy.body
            !tooLong -> R.string.draft_refused_body_away
            vm.container.settings.paired -> R.string.draft_too_long_body_away
            else -> R.string.draft_too_long_body_unpaired
        }
        Text(stringResource(body), style = MaterialTheme.typography.bodyLarge)
        if (copy.reasons.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
            copy.reasons.forEach { reason ->
                Row(horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
                    Text("•", style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
                    Text(stringResource(reason), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
                }
            }
        }
        // The note says the recording is kept only when there is one, and that it is in Your scores only once it is
        // (a score that could not be opened has no recording; a keep that failed left it where it was).
        val source by vm.source.collectAsState()
        val kept by vm.keptRecordings.collectAsState()
        val recording = source?.file?.takeIf { source?.kind != no.kalli.scribe.play.SourceKind.SCORE }
        val inYourScores = recording != null && kept.any { it.file == recording }
        val note = when (copy.note) {
            R.string.problem_score_kept -> if (inYourScores) R.string.problem_score_kept_scores else R.string.problem_score_kept.takeIf { recording != null }
            R.string.draft_too_long_kept -> if (inYourScores) R.string.draft_too_long_kept_scores else R.string.draft_too_long_kept
            else -> copy.note
        }
        note?.let { InfoNote(stringResource(it)) }
        // Once the computer is there (paired from here), "connect it first" is no longer true.
        vm.problemWhy?.takeIf { !(needsComputer && computerThere) }?.let { InfoNote(stringResource(it), Modifier.semantics { testTag = "problem-why" }) }
        val detail = vm.problemDetail
        if (!detail.isNullOrBlank()) {
            PlainButton(stringResource(if (details) R.string.details_hide else R.string.details_show), { details = !details })
            if (details) Text(detail, style = MaterialTheme.typography.bodySmall, color = c.textMuted)
        }
    }
}

/**
 * Settings (system.md §5): Brasscribe on your computer; Sound; Display (language, text size and
 * reduced motion, which are the phone's own settings); Help and About.
 */
@Composable
fun SettingsScreen(vm: PlayViewModel, beforeDisplay: @Composable () -> Unit = {}, afterDisplay: @Composable () -> Unit = {}) {
    val status by vm.status.collectAsState()
    val context = androidx.compose.ui.platform.LocalContext.current
    val connection by vm.connection.state.collectAsState()
    fun open(action: String, withPackage: Boolean = false) = runCatching {
        context.startActivity(android.content.Intent(action).apply {
            if (withPackage) data = android.net.Uri.fromParts("package", context.packageName, null)
        })
    }
    PlayScaffold(title = null, onBack = vm::back, backLabel = stringResource(R.string.home), status = status) {
        ScreenTitle(stringResource(R.string.settings))
        // Your instrument (my-instrument §3.2): first, above everything else. The picker is the first run's.
        if (vm.container.seats.isNotEmpty()) {
            val seatRow = androidx.compose.runtime.remember { androidx.compose.ui.focus.FocusRequester() }
            val focusRow by vm.focusSeatRow.collectAsState()
            androidx.compose.runtime.LaunchedEffect(focusRow) {
                if (focusRow) { kotlinx.coroutines.delay(100); runCatching { seatRow.requestFocus() }; vm.focusSeatRow.value = false }
            }
            SectionLabel(stringResource(R.string.settings_you))
            val value = vm.container.product.instrumentValue(vm)
            RowGroup {
                ListRow(stringResource(R.string.settings_seat), { vm.openSeatPicker(no.kalli.scribe.play.SeatPickerMode.SETTINGS) },
                    Modifier.focusRequester(seatRow).semantics { testTag = "setting-seat" },
                    subtitle = value, icon = DesignR.drawable.ic_bc_parts)
            }
            Text(stringResource(R.string.settings_seat_caption), style = MaterialTheme.typography.bodyMedium,
                color = no.kalli.scribe.design.ScribeTheme.colors.textMuted, modifier = Modifier.padding(horizontal = ScribeSpace.s4))
        }
        RowGroup {
            ListRow(
                stringResource(R.string.companion_title), { vm.navigate(no.kalli.scribe.play.Screen.COMPANION) }, icon = DesignR.drawable.ic_bc_computer,
                subtitle = connectionText(vm, connection),
            )
        }
        // The product's own sections above the display, such as the choice of sound.
        beforeDisplay()
        SectionLabel(stringResource(R.string.settings_display))
        RowGroup {
            AppearanceRow(vm)
            RowDivider()
            // Per-app language is a system setting.
            ListRow(stringResource(R.string.settings_language), { open(android.provider.Settings.ACTION_APP_LOCALE_SETTINGS, withPackage = true) },
                icon = DesignR.drawable.ic_bc_info, subtitle = stringResource(R.string.settings_language_desc))
            RowDivider()
            ListRow(stringResource(R.string.settings_text_motion), { open(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS) },
                icon = DesignR.drawable.ic_bc_text_size, subtitle = stringResource(R.string.settings_text_motion_desc))
        }
        // The product's own sections below the display, such as the music stand's.
        afterDisplay()
        // Recordings are large: what the ones kept in Your scores take, and where they are deleted.
        val keptBytes by vm.keptBytes.collectAsState()
        if (keptBytes > 0) Text(stringResource(R.string.kept_storage, android.text.format.Formatter.formatShortFileSize(context, keptBytes)),
            style = MaterialTheme.typography.bodyMedium, color = ScribeTheme.colors.textMuted,
            modifier = Modifier.padding(horizontal = ScribeSpace.s4).semantics { testTag = "kept-storage" })
        RowGroup {
            ListRow(stringResource(R.string.help), { vm.navigate(no.kalli.scribe.play.Screen.HELP) }, icon = DesignR.drawable.ic_bc_help)
            RowDivider()
            ListRow(stringResource(R.string.about_title), { vm.navigate(no.kalli.scribe.play.Screen.ABOUT) }, icon = DesignR.drawable.ic_bc_info)
        }
    }
}

/** Help: the flow in the band room's words, one short section each. */
@Composable
fun HelpScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val c = ScribeTheme.colors
    PlayScaffold(title = null, onBack = vm::back, backLabel = stringResource(R.string.back), status = status) {
        ScreenTitle(stringResource(R.string.help))
        listOf(
            R.string.help_1_title to R.string.help_1_text, R.string.help_2_title to R.string.help_2_text,
            R.string.help_3_title to R.string.help_3_text, R.string.help_4_title to R.string.help_4_text,
            R.string.help_5_title to R.string.help_5_text, R.string.help_6_title to R.string.help_6_text,
        ).forEach { (t, body) ->
            Column(verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1)) {
                SubHeading(stringResource(t))
                Text(stringResource(body), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
            }
            // After the computer's part: where to get the program.
            if (t == R.string.help_5_title) GetBandroom({ vm.say(R.string.bandroom_no_browser) })
        }
        // The music stand: page turners, and how to keep a tablet one way up (it has no Lock rotation).
        Column(verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1)) {
            SubHeading(stringResource(R.string.help_stand_title))
            Text(stringResource(R.string.help_stand_pedal), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
            if (androidx.compose.ui.platform.LocalConfiguration.current.smallestScreenWidthDp >= 600)
                Text(stringResource(R.string.help_stand_tablet_lock), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
        }
    }
}

/** A setting that is on or off: the whole row is the switch, at least 60 dp tall. */
@Composable
fun SwitchRow(title: String, subtitle: String?, checked: Boolean, tag: String, onChange: (Boolean) -> Unit) {
    val c = ScribeTheme.colors
    androidx.compose.foundation.layout.Row(
        Modifier.fillMaxWidth().heightIn(min = 60.dp)
            .toggleable(value = checked, role = androidx.compose.ui.semantics.Role.Switch, onValueChange = onChange)
            .semantics { testTag = tag }
            .padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s3),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = c.text)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        androidx.compose.material3.Switch(checked, null, colors = androidx.compose.material3.SwitchDefaults.colors(
            checkedTrackColor = c.primary, checkedThumbColor = c.onPrimary, uncheckedBorderColor = c.borderStrong,
            uncheckedTrackColor = c.surfaceRaised, uncheckedThumbColor = c.borderStrong))
    }
}
