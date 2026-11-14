package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import no.kalli.scribe.design.R as DesignR

import no.kalli.scribe.tab.PracticeModel
import no.kalli.scribe.tab.PracticeSpeed
import no.kalli.scribe.tab.RecordingState
import no.kalli.scribe.tab.RepeatBars

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.PressInteraction
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import no.kalli.scribe.tab.PracticeSound
import no.kalli.scribe.tab.TabSoundState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.hideFromAccessibility
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import no.kalli.scribe.design.ScribeButtonShape
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.ui.BcIcon
import no.kalli.scribe.play.ui.OutlineButton
import no.kalli.scribe.play.ui.PlainButton
import no.kalli.scribe.play.ui.PracticeChip

/** The transport's targets: reachable with an instrument in the hands (design/brands/fretscribe/system.md §1). */
private val TRANSPORT = 64.dp

/** A phone on its side: the height the player gives up goes to the tab. */
private const val SHORT_SCREEN_DP = 480

/** Under this width the transport's other buttons are a little narrower, so where the song is has room beside them. */
private const val NARROW_SCREEN_DP = 400

/** Under this width a phone on its side has the player in one row only with every part of it at its shortest. */
private const val TIGHT_ROW_DP = 700

/** A control that does nothing where it is looks off as Material draws one: its colour at this opacity. */
private const val DISABLED_ALPHA = 0.38f

/**
 * The player under the tab (design/brands/fretscribe/system.md §4, Practice player), in its order: Play, back to
 * the start (of the repeat), a bar back and a bar on, where the song is, the speed, and the bars to repeat.
 * It wraps onto as many rows as it needs and never clips. When the recording is not on the phone it says
 * so, and offers to get it from the computer when the computer is there. A tab read from printed music
 * ([fromPages]) has no recording: it says that, and offers nothing to get.
 *
 * The tab is what the screen is for, so the player takes no more height than it must. On a small phone on its side
 * it is one row: only Play keeps the 64 dp, the word Speed is left out and Repeat bars is one word or its icon (the
 * bars, when it is on); what is seen is shorter, what is said is the same. With a note open under it ([withNote]),
 * upright, it leaves out where the song is (the note says its own bar) and the word Speed, and is a row lower.
 *
 * [place]: the bar (counted from 0) and the beat the recording is at. [follows]: the tab has the beats to
 * follow the recording by. [soundHere]: the Sound button is the player's last (with large text upright, on a
 * wide screen on its side and in full screen; else the header over the tab or the top bar has it, where there is room).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun PracticeBar(practice: PracticeModel, measures: List<TabMeasure>, place: Pair<Int, Int>?, follows: Boolean, canFetch: Boolean, withNote: Boolean = false, onFetch: () -> Unit,
    soundHere: Boolean = false, onSound: () -> Unit = {}, fromPages: Boolean = false) {
    val c = ScribeTheme.colors
    val state = practice.recording
    // Nothing is said while it is still being found out what there is to play: the recording looked for, the tab's sound made.
    if (follows && (state == RecordingState.LOOKING || (state != RecordingState.HERE && practice.tabSoundState == TabSoundState.LOADING))) return
    Column(Modifier.fillMaxWidth().background(c.bg).testTag("fs-practice")) {
        HorizontalDivider(thickness = 1.dp, color = c.border)
        // Without the recording the tab's own sound plays, and Sound says what became of the recording.
        if (!follows || (state != RecordingState.HERE && !practice.tabSound)) {
            Column(Modifier.fillMaxWidth().padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s3), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
                RecordingNote(state, follows, canFetch, onFetch, fromPages)
            }
            return@Column
        }
        var choosing by rememberSaveable { mutableStateOf(false) }
        val repeat = practice.repeat
        fun number(bar: Int) = measures.getOrNull(bar)?.number ?: (bar + 1).toString()
        val screen = LocalConfiguration.current
        val short = screen.screenHeightDp < SHORT_SCREEN_DP
        // A small phone on its side: one row only with everything at its shortest.
        val tight = short && screen.screenWidthDp < TIGHT_ROW_DP
        val largeText = LocalDensity.current.fontScale >= 1.3f
        // Play is always 64 dp. The three beside it are too where there is room, and never under 48 dp.
        val beside = when {
            tight -> 48.dp
            !short && screen.screenWidthDp < NARROW_SCREEN_DP -> 56.dp
            else -> TRANSPORT
        }
        // Upright with large text the chip is its icon beside the transport, so the player is two rows, not three.
        val early = !short && largeText
        val repeatChip: @Composable () -> Unit = {
            // The chip's words are its name: what is seen is what is said.
            val shown = when {
                repeat == null -> stringResource(R.string.fs_practice_repeat)
                repeat.first == repeat.last -> stringResource(R.string.fs_practice_repeat_on_one, number(repeat.first))
                else -> stringResource(R.string.fs_practice_repeat_on, number(repeat.first), number(repeat.last))
            }
            // On a small phone on its side the chip is as short as it can be: Repeat (its icon alone with large text), or the bars when it
            // is on. Its name is the whole of it either way.
            val brief = when {
                repeat == null -> if (largeText) "" else stringResource(R.string.fs_practice_repeat_brief)
                repeat.first == repeat.last -> number(repeat.first)
                else -> stringResource(R.string.fs_practice_repeat_bars_brief, number(repeat.first), number(repeat.last))
            }
            if (tight || early) PracticeChip(brief, repeat != null, { choosing = true }, Modifier.widthIn(min = 48.dp).testTag("fs-practice-repeat"),
                icon = DesignR.drawable.ic_bc_loop, role = Role.Button, accessibleName = shown)
            else PracticeChip(shown, repeat != null, { choosing = true }, Modifier.testTag("fs-practice-repeat"), icon = DesignR.drawable.ic_bc_loop, role = Role.Button)
        }
        FlowRow(
            Modifier.fillMaxWidth().padding(horizontal = ScribeSpace.s3, vertical = ScribeSpace.s2),
            horizontalArrangement = Arrangement.spacedBy(if (tight) ScribeSpace.s2 else ScribeSpace.s3), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                FilledIconButton(practice::toggle, Modifier.size(TRANSPORT).testTag("fs-practice-play"), shape = CircleShape,
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.primary, contentColor = c.onPrimary)) {
                    BcIcon(if (practice.playing) DesignR.drawable.ic_bc_pause else DesignR.drawable.ic_bc_play, stringResource(if (practice.playing) R.string.pause else R.string.play))
                }
                IconButton(practice::toStart, Modifier.size(beside).testTag("fs-practice-start")) {
                    BcIcon(DesignR.drawable.ic_bc_restart, stringResource(if (repeat != null) R.string.fs_practice_to_repeat_start else R.string.fs_practice_to_start))
                }
                IconButton({ practice.step(-1) }, Modifier.size(beside).testTag("fs-practice-previous")) { BcIcon(DesignR.drawable.ic_bc_previous_bar, stringResource(R.string.action_prev_bar)) }
                // In the last bar there is no bar on: Next bar says so and looks off, but it stays where it is in the focus
                // order and keeps the focus (a button that is switched off would lose it). While the recording plays the
                // bar changes on its own, so the reason is only given once it stops, the way the place is only said then.
                val noBarOn = place != null && !practice.hasBarOn(place.first)
                val last = stringResource(if (repeat != null) R.string.fs_practice_last_bar_of_repeat else R.string.fs_practice_last_bar)
                val still = !practice.playing
                IconButton({ practice.step(1) }, Modifier.size(beside).testTag("fs-practice-next").semantics {
                    if (noBarOn) { disabled(); if (still) stateDescription = last }
                }) {
                    BcIcon(DesignR.drawable.ic_bc_next_bar, stringResource(R.string.action_next_bar),
                        tint = if (noBarOn) LocalContentColor.current.copy(alpha = DISABLED_ALPHA) else Color.Unspecified)
                }
            }
            if (early) repeatChip()
            // Where the song is. It changes with every beat while the recording plays, so it is only announced when the
            // player moved it: a bar back or on, or back to the start.
            val measure = place?.let { measures.getOrNull(it.first) }
            val where = when {
                place == null || measure == null -> ""
                measure.pickup -> stringResource(R.string.fs_practice_pickup_beat, place.second)
                else -> stringResource(R.string.fs_practice_bar_beat, measure.number, place.second)
            }
            val quiet = practice.playing
            // When the recording stops, the place it stopped at is said once: the text under a screen reader's finger did
            // not change at that moment, so nothing else would say it.
            val view = LocalView.current
            val said by rememberUpdatedState(where)
            var wasPlaying by remember { mutableStateOf(false) }
            LaunchedEffect(practice.playing) {
                if (wasPlaying && !practice.playing && said.isNotEmpty()) view.announceForAccessibility(said)
                wasPlaying = practice.playing
            }
            // (With a note open the place would take a row of its own upright: the note says its bar, and where the song
            // stops is still said.)
            if (!withNote || short) Text(where, style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold), color = c.text,
                modifier = Modifier.testTag("fs-practice-place").semantics { if (!quiet) liveRegion = LiveRegionMode.Polite })
            Row(verticalAlignment = Alignment.CenterVertically) {
                val speed = stringResource(R.string.speed_chip, practice.speed)
                // The word is for the eye: the value's own name already says "Speed 100 %". With large text, on a narrow
                // phone, on a small phone on its side and with a note open it is left out, as the top bar leaves out the
                // back button's word: the player would take another row for it.
                if (!largeText && !tight && !withNote && screen.screenWidthDp >= NARROW_SCREEN_DP) Text(stringResource(R.string.fs_practice_speed), style = MaterialTheme.typography.bodyLarge, color = c.textMuted,
                    modifier = Modifier.padding(end = ScribeSpace.s1).testTag("fs-practice-speed-label").semantics { hideFromAccessibility() })
                StepButton("−", stringResource(R.string.fs_practice_slower), "fs-practice-slower", practice.speed > PracticeSpeed.MIN, repeats = true, onClick = practice::slower)
                Text(stringResource(R.string.speed_value, practice.speed), style = MaterialTheme.typography.bodyLarge, color = c.text, textAlign = TextAlign.Center,
                    modifier = Modifier.widthIn(min = 56.dp).testTag("fs-practice-speed").semantics { contentDescription = speed; liveRegion = LiveRegionMode.Polite })
                StepButton("+", stringResource(R.string.fs_practice_faster), "fs-practice-faster", practice.speed < PracticeSpeed.MAX, repeats = true, onClick = practice::faster)
            }
            if (!early) repeatChip()
            if (soundHere && practice.tabSoundState >= TabSoundState.READY) SoundButton(practice, onSound)
        }
        if (choosing) RepeatDialog(measures, repeat, place?.first ?: 0, { practice.repeat(it); choosing = false }) { choosing = false }
    }
}

/**
 * Sound: what is heard, with the count-in and the metronome behind it. One small button, so the tab keeps the room;
 * its name says what is on, and it is filled when anything but the recording alone is.
 */
@Composable
internal fun SoundButton(practice: PracticeModel, onClick: () -> Unit) {
    val c = ScribeTheme.colors
    val name = (listOf(stringResource(R.string.fs_practice_sound_chip, stringResource(soundName(practice.hears)))) + listOfNotNull(
        stringResource(R.string.fs_practice_count_in).takeIf { practice.countIn && practice.tabSound },
        stringResource(R.string.fs_practice_metronome).takeIf { practice.metronome && practice.tabSound },
    )).joinToString(", ")
    val on = practice.tabSound && (practice.hears != PracticeSound.RECORDING || practice.countIn || practice.metronome)
    Box(
        Modifier.size(48.dp).testTag("fs-practice-sound")
            .background(if (on) c.secondary else c.surfaceRaised, ScribeButtonShape)
            .border(if (on) 1.5.dp else 1.dp, if (on) c.text else c.borderStrong, ScribeButtonShape)
            .clickable(role = Role.Button, onClick = onClick)
            .semantics { contentDescription = name },
        contentAlignment = Alignment.Center,
    ) { BcIcon(R.drawable.ic_fs_sound, null, Modifier.size(24.dp)) }
}

private fun soundName(sound: PracticeSound): Int = when (sound) {
    PracticeSound.RECORDING -> R.string.fs_sound_recording
    PracticeSound.TAB -> R.string.fs_sound_tab
    PracticeSound.BOTH -> R.string.fs_sound_both
}

/** What became of the recording when it is not played: where it is, getting it, and how that went; with the button that gets it. */
@Composable
private fun RecordingNote(state: RecordingState, follows: Boolean, canFetch: Boolean, onFetch: () -> Unit, fromPages: Boolean = false) {
    val c = ScribeTheme.colors
    val words = stringResource(when {
        // Read from printed music: there never was a recording, and nothing to get.
        fromPages -> R.string.fs_practice_from_pages
        !follows -> R.string.fs_practice_no_beats
        state == RecordingState.GETTING -> R.string.fs_practice_getting
        state == RecordingState.GONE -> R.string.fs_practice_gone
        state == RecordingState.NO_ANSWER -> R.string.fs_practice_no_answer
        state == RecordingState.UPDATE_APP -> R.string.conn_update_app
        state == RecordingState.UPDATE_COMPUTER -> R.string.conn_update_computer
        state == RecordingState.NO_ROOM -> R.string.fs_practice_no_room
        state == RecordingState.TOO_LARGE -> R.string.fs_practice_too_large
        state == RecordingState.UNPLAYABLE -> R.string.fs_practice_unplayable
        canFetch -> R.string.fs_practice_not_here
        else -> R.string.fs_practice_not_here_alone
    })
    // What became of the recording is said once when it changes: getting it, and how that went.
    Text(words, style = MaterialTheme.typography.bodyLarge, color = c.text,
        modifier = Modifier.testTag("fs-practice-says").semantics { liveRegion = LiveRegionMode.Polite })
    if (follows && state == RecordingState.GETTING) LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brand, trackColor = c.border)
    if (follows && !fromPages && canFetch && (state == RecordingState.NOT_HERE || state == RecordingState.NO_ANSWER || state == RecordingState.NO_ROOM)) OutlineButton(
        stringResource(if (state == RecordingState.NOT_HERE) R.string.fs_practice_get else R.string.retry), onFetch,
        Modifier.testTag("fs-practice-get"), icon = DesignR.drawable.ic_bc_download, fill = false)
}

/**
 * Sound: what is heard (the recording, the tab's own notes, or both), whether a bar is counted in before the song
 * plays, and whether the beats tick. A choice is heard at once and the dialog stays open, so it can be tried.
 * Without the recording on the phone only the tab's notes can be heard, and the dialog says how to get the recording.
 */
@Composable
internal fun SoundDialog(practice: PracticeModel, canFetch: Boolean, onFetch: () -> Unit, fromPages: Boolean = false, close: () -> Unit) {
    val c = ScribeTheme.colors
    val here = practice.recording == RecordingState.HERE
    val tab = practice.tabSound
    AlertDialog(
        onDismissRequest = close,
        title = { Text(stringResource(R.string.fs_practice_sound), Modifier.semantics { heading() }) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1)) {
                Column(Modifier.selectableGroup()) {
                    PracticeSound.entries.forEach { sound ->
                        val on = practice.hears == sound
                        val can = if (sound == PracticeSound.RECORDING) here else tab && (here || sound == PracticeSound.TAB)
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                .selectable(selected = on, enabled = can, role = Role.RadioButton) { practice.hear(sound) }
                                .testTag("fs-sound-${sound.id}").padding(horizontal = ScribeSpace.s2, vertical = ScribeSpace.s1),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
                        ) {
                            RadioButton(selected = on, onClick = null, enabled = can,
                                colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
                            Text(stringResource(soundName(sound)), Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge,
                                color = if (can) c.text else c.text.copy(alpha = DISABLED_ALPHA))
                        }
                    }
                }
                if (!here) Column(Modifier.fillMaxWidth().padding(vertical = ScribeSpace.s2), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
                    RecordingNote(practice.recording, follows = true, canFetch, onFetch, fromPages)
                }
                // The tab's notes, the count-in and the metronome are one sound: without it they are off, and it says why.
                if (!tab) Text(stringResource(R.string.fs_sound_failed), style = MaterialTheme.typography.bodyLarge, color = c.text,
                    modifier = Modifier.padding(vertical = ScribeSpace.s2).testTag("fs-sound-failed").semantics { liveRegion = LiveRegionMode.Polite })
                HorizontalDivider(thickness = 1.dp, color = c.border)
                SwitchRow(stringResource(R.string.fs_practice_count_in), stringResource(R.string.fs_practice_count_in_tip), practice.countIn, "fs-sound-count-in", tab, practice::countIn)
                SwitchRow(stringResource(R.string.fs_practice_metronome), stringResource(R.string.fs_practice_metronome_tip), practice.metronome, "fs-sound-metronome", tab, practice::metronome)
            }
        },
        confirmButton = { PlainButton(stringResource(R.string.fs_practice_sound_done), close, Modifier.testTag("fs-sound-done")) },
    )
}

/** A switch with its name and a line about it: the whole row is the switch. */
@Composable
private fun SwitchRow(label: String, tip: String, on: Boolean, tag: String, enabled: Boolean, set: (Boolean) -> Unit) {
    val c = ScribeTheme.colors
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).toggleable(value = on, enabled = enabled, role = Role.Switch, onValueChange = set).testTag(tag)
            .padding(horizontal = ScribeSpace.s2, vertical = ScribeSpace.s1),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s3),
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge, color = if (enabled) c.text else c.text.copy(alpha = DISABLED_ALPHA))
            Text(tip, style = MaterialTheme.typography.bodyMedium, color = if (enabled) c.textMuted else c.textMuted.copy(alpha = DISABLED_ALPHA))
        }
        Switch(checked = on, onCheckedChange = null, enabled = enabled, colors = SwitchDefaults.colors(
            checkedTrackColor = c.primary, checkedThumbColor = c.onPrimary, uncheckedTrackColor = c.surfaceRaised, uncheckedThumbColor = c.borderStrong, uncheckedBorderColor = c.borderStrong))
    }
}

/** How long a step button is held before it steps again on its own, and how often it then steps, in milliseconds. */
internal const val STEP_HOLD_MS = 400L
internal const val STEP_REPEAT_MS = 100L

/**
 * A step down or up: a 48 dp button with a plain sign, named by what it does. A tap is one step. With [repeats],
 * holding it down steps again every [STEP_REPEAT_MS] after [STEP_HOLD_MS], until it is let go or can step no further;
 * letting go after that adds no step of its own.
 */
@Composable
private fun StepButton(sign: String, name: String, tag: String, enabled: Boolean, repeats: Boolean = false, onClick: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    var held by remember { mutableStateOf(false) }
    if (repeats) {
        val step by rememberUpdatedState(onClick)
        val can by rememberUpdatedState(enabled)
        LaunchedEffect(source) {
            // A new press, a release or a cancel ends the steps of the press before it.
            source.interactions.collectLatest { i ->
                // A press that was cancelled (the finger slid off, the page scrolled) is followed by no click to swallow.
                if (i is PressInteraction.Cancel) held = false
                if (i !is PressInteraction.Press) return@collectLatest
                held = false
                delay(STEP_HOLD_MS)
                while (can) {
                    held = true
                    step()
                    delay(STEP_REPEAT_MS)
                }
            }
        }
    }
    // Held to the end, the button is off when it is let go: no click comes, and the next one (a tap, or a screen
    // reader's, switch's or voice's press) must step.
    LaunchedEffect(enabled) { if (!enabled) held = false }
    IconButton({ if (held) held = false else onClick() }, Modifier.size(48.dp).testTag(tag).semantics { contentDescription = name },
        enabled = enabled, interactionSource = source) {
        Text(sign, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.clearAndSetSemantics { })
    }
}

/**
 * The bars to repeat, chosen by their numbers with a step down and a step up each (nothing is dragged, WCAG
 * 2.5.7). It opens on the repeat there is, or on four bars from the bar the song is in.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RepeatDialog(measures: List<TabMeasure>, repeat: RepeatBars?, bar: Int, onSet: (RepeatBars?) -> Unit, close: () -> Unit) {
    val c = ScribeTheme.colors
    val last = measures.lastIndex.coerceAtLeast(0)
    var from by rememberSaveable { mutableIntStateOf((repeat?.first ?: bar).coerceIn(0, last)) }
    var to by rememberSaveable { mutableIntStateOf((repeat?.last ?: (bar + 3)).coerceIn(from, last)) }
    fun number(i: Int) = measures.getOrNull(i)?.number ?: (i + 1).toString()
    AlertDialog(
        onDismissRequest = close,
        title = { Text(stringResource(R.string.fs_practice_repeat), Modifier.semantics { heading() }) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
                Text(stringResource(R.string.fs_practice_repeat_tip), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                val fromBar: @Composable (Modifier) -> Unit = { m ->
                    BarStepper(stringResource(R.string.loop_from), number(from), "from", from > 0, from < last,
                        { from--; }, { from++; if (to < from) to = from }, m)
                }
                val toBar: @Composable (Modifier) -> Unit = { m ->
                    BarStepper(stringResource(R.string.loop_to), number(to), "to", to > 0, to < last,
                        { to--; if (from > to) from = to }, { to++ }, m)
                }
                // On a phone on its side the two ends share a row, so the button under them is in view without scrolling.
                if (LocalConfiguration.current.screenHeightDp < SHORT_SCREEN_DP && LocalDensity.current.fontScale < 1.3f)
                    Row(horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s6)) { fromBar(Modifier.weight(1f)); toBar(Modifier.weight(1f)) }
                else { fromBar(Modifier.fillMaxWidth()); toBar(Modifier.fillMaxWidth()) }
                if (measures.firstOrNull()?.pickup == true) Text(stringResource(R.string.fs_practice_repeat_pickup), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                // The buttons scroll with the rest: with large text on a phone on its side the dialog is taller than the screen.
                Button({ onSet(RepeatBars(from, to)) }, Modifier.fillMaxWidth().padding(top = ScribeSpace.s2).heightIn(min = 52.dp).testTag("fs-practice-repeat-set"), shape = ScribeButtonShape) {
                    Text(if (from == to) stringResource(R.string.fs_practice_repeat_set_one, number(from)) else stringResource(R.string.fs_practice_repeat_set, number(from), number(to)),
                        style = MaterialTheme.typography.labelLarge, textAlign = TextAlign.Center)
                }
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s2, Alignment.End)) {
                    if (repeat != null) PlainButton(stringResource(R.string.loop_clear), { onSet(null) }, Modifier.testTag("fs-practice-repeat-stop"))
                    PlainButton(stringResource(R.string.cancel), close, Modifier.testTag("fs-practice-repeat-cancel"))
                }
            }
        },
        confirmButton = {},
    )
}

/** One end of the repeat: its name, a bar earlier, the bar's number (said when it changes), a bar later. */
@Composable
private fun BarStepper(label: String, value: String, tag: String, canGoDown: Boolean, canGoUp: Boolean, down: () -> Unit, up: () -> Unit, modifier: Modifier = Modifier) {
    val c = ScribeTheme.colors
    val spoken = stringResource(R.string.fs_practice_bar_value, label, value)
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f).clearAndSetSemantics { }, style = MaterialTheme.typography.bodyLarge, color = c.text)
        StepButton("−", stringResource(R.string.fs_practice_bar_earlier, label), "fs-practice-$tag-down", canGoDown, onClick = down)
        Text(value, style = MaterialTheme.typography.titleMedium, color = c.text, textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(min = 40.dp).testTag("fs-practice-$tag").semantics { contentDescription = spoken; liveRegion = LiveRegionMode.Polite })
        StepButton("+", stringResource(R.string.fs_practice_bar_later, label), "fs-practice-$tag-up", canGoUp, onClick = up)
    }
}
