package no.brasscribe.play.fret

import androidx.compose.foundation.background
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
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.R
import no.brasscribe.play.ui.BcIcon
import no.brasscribe.play.ui.OutlineButton
import no.brasscribe.play.ui.PlainButton
import no.brasscribe.play.ui.PracticeChip

/** The transport's targets: reachable with an instrument in the hands (design/fretscribe/system.md §1). */
private val TRANSPORT = 64.dp

/** A control that does nothing where it is looks off as Material draws one: its colour at this opacity. */
private const val DISABLED_ALPHA = 0.38f

/**
 * The player under the tab (design/fretscribe/system.md §4, Practice player), in its order: Play, back to
 * the start (of the repeat), a bar back and a bar on, where the song is, the speed, and the bars to repeat.
 * It wraps onto as many rows as it needs and never clips. When the recording is not on the phone it says
 * so, and offers to get it from the computer when the computer is there.
 *
 * [place]: the bar (counted from 0) and the beat the recording is at. [follows]: the tab has the beats to
 * follow the recording by.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun PracticeBar(practice: PracticeModel, measures: List<TabMeasure>, place: Pair<Int, Int>?, follows: Boolean, canFetch: Boolean, onFetch: () -> Unit) {
    val c = BrasscribeTheme.colors
    val state = practice.recording
    if (follows && state == RecordingState.LOOKING) return
    Column(Modifier.fillMaxWidth().background(c.bg).testTag("fs-practice")) {
        HorizontalDivider(thickness = 1.dp, color = c.border)
        if (!follows || state != RecordingState.HERE) {
            val words = stringResource(when {
                !follows -> R.string.fs_practice_no_beats
                state == RecordingState.GETTING -> R.string.fs_practice_getting
                state == RecordingState.GONE -> R.string.fs_practice_gone
                state == RecordingState.NO_ANSWER -> R.string.fs_practice_no_answer
                state == RecordingState.NO_ROOM -> R.string.fs_practice_no_room
                state == RecordingState.TOO_LARGE -> R.string.fs_practice_too_large
                state == RecordingState.UNPLAYABLE -> R.string.fs_practice_unplayable
                canFetch -> R.string.fs_practice_not_here
                else -> R.string.fs_practice_not_here_alone
            })
            Column(Modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                // What became of the recording is said once when it changes: getting it, and how that went.
                Text(words, style = MaterialTheme.typography.bodyLarge, color = c.text,
                    modifier = Modifier.testTag("fs-practice-says").semantics { liveRegion = LiveRegionMode.Polite })
                if (follows && state == RecordingState.GETTING) LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
                if (follows && canFetch && (state == RecordingState.NOT_HERE || state == RecordingState.NO_ANSWER || state == RecordingState.NO_ROOM)) OutlineButton(
                    stringResource(if (state == RecordingState.NOT_HERE) R.string.fs_practice_get else R.string.retry), onFetch,
                    Modifier.testTag("fs-practice-get"), icon = R.drawable.ic_bc_download, fill = false)
            }
            return@Column
        }
        var choosing by rememberSaveable { mutableStateOf(false) }
        val repeat = practice.repeat
        fun number(bar: Int) = measures.getOrNull(bar)?.number ?: (bar + 1).toString()
        FlowRow(
            Modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s3, vertical = BrasscribeSpace.s2),
            horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                FilledIconButton(practice::toggle, Modifier.size(TRANSPORT).testTag("fs-practice-play"), shape = CircleShape,
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.primary, contentColor = c.onPrimary)) {
                    BcIcon(if (practice.playing) R.drawable.ic_bc_pause else R.drawable.ic_bc_play, stringResource(if (practice.playing) R.string.pause else R.string.play))
                }
                IconButton(practice::toStart, Modifier.size(TRANSPORT).testTag("fs-practice-start")) {
                    BcIcon(R.drawable.ic_bc_restart, stringResource(if (repeat != null) R.string.fs_practice_to_repeat_start else R.string.fs_practice_to_start))
                }
                IconButton({ practice.step(-1) }, Modifier.size(TRANSPORT).testTag("fs-practice-previous")) { BcIcon(R.drawable.ic_bc_previous_bar, stringResource(R.string.action_prev_bar)) }
                // In the last bar there is no bar on: Next bar says so and looks off, but it stays where it is in the focus
                // order and keeps the focus (a button that is switched off would lose it). While the recording plays the
                // bar changes on its own, so the reason is only given once it stops, the way the place is only said then.
                val noBarOn = place != null && !practice.hasBarOn(place.first)
                val last = stringResource(if (repeat != null) R.string.fs_practice_last_bar_of_repeat else R.string.fs_practice_last_bar)
                val still = !practice.playing
                IconButton({ practice.step(1) }, Modifier.size(TRANSPORT).testTag("fs-practice-next").semantics {
                    if (noBarOn) { disabled(); if (still) stateDescription = last }
                }) {
                    BcIcon(R.drawable.ic_bc_next_bar, stringResource(R.string.action_next_bar),
                        tint = if (noBarOn) LocalContentColor.current.copy(alpha = DISABLED_ALPHA) else Color.Unspecified)
                }
            }
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
            Text(where, style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold), color = c.text,
                modifier = Modifier.testTag("fs-practice-place").semantics { if (!quiet) liveRegion = LiveRegionMode.Polite })
            Row(verticalAlignment = Alignment.CenterVertically) {
                val speed = stringResource(R.string.speed_chip, practice.speed)
                StepButton("−", stringResource(R.string.fs_practice_slower), "fs-practice-slower", practice.speed > PracticeSpeed.MIN, practice::slower)
                Text(stringResource(R.string.speed_value, practice.speed), style = MaterialTheme.typography.bodyLarge, color = c.text, textAlign = TextAlign.Center,
                    modifier = Modifier.widthIn(min = 56.dp).testTag("fs-practice-speed").semantics { contentDescription = speed; liveRegion = LiveRegionMode.Polite })
                StepButton("+", stringResource(R.string.fs_practice_faster), "fs-practice-faster", practice.speed < PracticeSpeed.MAX, practice::faster)
            }
            // The chip's words are its name: what is seen is what is said.
            val shown = when {
                repeat == null -> stringResource(R.string.fs_practice_repeat)
                repeat.first == repeat.last -> stringResource(R.string.fs_practice_repeat_on_one, number(repeat.first))
                else -> stringResource(R.string.fs_practice_repeat_on, number(repeat.first), number(repeat.last))
            }
            PracticeChip(shown, repeat != null, { choosing = true }, Modifier.testTag("fs-practice-repeat"), icon = R.drawable.ic_bc_loop, role = Role.Button)
        }
        if (choosing) RepeatDialog(measures, repeat, place?.first ?: 0, { practice.repeat(it); choosing = false }) { choosing = false }
    }
}

/** A step down or up: a 48 dp button with a plain sign, named by what it does. */
@Composable
private fun StepButton(sign: String, name: String, tag: String, enabled: Boolean, onClick: () -> Unit) {
    IconButton(onClick, Modifier.size(48.dp).testTag(tag).semantics { contentDescription = name }, enabled = enabled) {
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
    val c = BrasscribeTheme.colors
    val last = measures.lastIndex.coerceAtLeast(0)
    var from by rememberSaveable { mutableIntStateOf((repeat?.first ?: bar).coerceIn(0, last)) }
    var to by rememberSaveable { mutableIntStateOf((repeat?.last ?: (bar + 3)).coerceIn(from, last)) }
    fun number(i: Int) = measures.getOrNull(i)?.number ?: (i + 1).toString()
    AlertDialog(
        onDismissRequest = close,
        title = { Text(stringResource(R.string.fs_practice_repeat), Modifier.semantics { heading() }) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                Text(stringResource(R.string.fs_practice_repeat_tip), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                BarStepper(stringResource(R.string.loop_from), number(from), "from", from > 0, from < last,
                    { from--; }, { from++; if (to < from) to = from })
                BarStepper(stringResource(R.string.loop_to), number(to), "to", to > 0, to < last,
                    { to--; if (from > to) from = to }, { to++ })
                if (measures.firstOrNull()?.pickup == true) Text(stringResource(R.string.fs_practice_repeat_pickup), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                // The buttons scroll with the rest: with large text on a phone on its side the dialog is taller than the screen.
                Button({ onSet(RepeatBars(from, to)) }, Modifier.fillMaxWidth().padding(top = BrasscribeSpace.s2).heightIn(min = 52.dp).testTag("fs-practice-repeat-set"), shape = BrasscribeButtonShape) {
                    Text(if (from == to) stringResource(R.string.fs_practice_repeat_set_one, number(from)) else stringResource(R.string.fs_practice_repeat_set, number(from), number(to)),
                        style = MaterialTheme.typography.labelLarge, textAlign = TextAlign.Center)
                }
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2, Alignment.End)) {
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
private fun BarStepper(label: String, value: String, tag: String, canGoDown: Boolean, canGoUp: Boolean, down: () -> Unit, up: () -> Unit) {
    val c = BrasscribeTheme.colors
    val spoken = stringResource(R.string.fs_practice_bar_value, label, value)
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f).clearAndSetSemantics { }, style = MaterialTheme.typography.bodyLarge, color = c.text)
        StepButton("−", stringResource(R.string.fs_practice_bar_earlier, label), "fs-practice-$tag-down", canGoDown, down)
        Text(value, style = MaterialTheme.typography.titleMedium, color = c.text, textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(min = 40.dp).testTag("fs-practice-$tag").semantics { contentDescription = spoken; liveRegion = LiveRegionMode.Polite })
        StepButton("+", stringResource(R.string.fs_practice_bar_later, label), "fs-practice-$tag-up", canGoUp, up)
    }
}
