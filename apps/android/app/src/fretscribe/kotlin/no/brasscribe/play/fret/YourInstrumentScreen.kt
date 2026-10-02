package no.brasscribe.play.fret

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeScore
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.AppearanceStore
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.SeatPickerMode
import no.brasscribe.play.connection.PrefsStore
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.ui.BcIcon
import no.brasscribe.play.ui.Lead
import no.brasscribe.play.ui.ListRow
import no.brasscribe.play.ui.PlainButton
import no.brasscribe.play.ui.PlayScaffold
import no.brasscribe.play.ui.PrimaryButton
import no.brasscribe.play.ui.RowDivider
import no.brasscribe.play.ui.RowGroup
import no.brasscribe.play.ui.ScreenTitle

/** The store on this phone: the per-device preferences that hold Appearance too. */
fun yourInstrumentStore(context: Context): YourInstrumentStore =
    YourInstrumentStore(PrefsStore(context.getSharedPreferences(AppearanceStore.PREFS, Context.MODE_PRIVATE)))

@StringRes
private fun instrumentName(i: Instrument): Int = when (i) {
    Instrument.BASS -> R.string.fs_instrument_bass
    Instrument.GUITAR -> R.string.fs_instrument_guitar
    Instrument.UKULELE -> R.string.fs_instrument_ukulele
    Instrument.MANDOLIN -> R.string.fs_instrument_mandolin
}

/** A tuning's name, as shown or as spoken ("BEAD" and "DADGAD" are read letter by letter). An id without words of its own shows as it is. */
@Composable
internal fun tuningName(id: String, spoken: Boolean = false): String = when (id) {
    "standard" -> stringResource(R.string.fs_tuning_standard)
    "eb-standard" -> stringResource(R.string.fs_tuning_eb_standard)
    "d-standard" -> stringResource(R.string.fs_tuning_d_standard)
    "c-standard" -> stringResource(R.string.fs_tuning_c_standard)
    "drop-d" -> stringResource(R.string.fs_tuning_drop_d)
    "drop-c" -> stringResource(R.string.fs_tuning_drop_c)
    "drop-b" -> stringResource(R.string.fs_tuning_drop_b)
    "dadgad" -> stringResource(if (spoken) R.string.fs_tuning_dadgad_spoken else R.string.fs_tuning_dadgad)
    "open-g" -> stringResource(R.string.fs_tuning_open_g)
    "open-d" -> stringResource(R.string.fs_tuning_open_d)
    "open-e" -> stringResource(R.string.fs_tuning_open_e)
    "bead" -> stringResource(if (spoken) R.string.fs_tuning_bead_spoken else R.string.fs_tuning_bead)
    "drop-a" -> stringResource(R.string.fs_tuning_drop_a)
    "high-g" -> stringResource(R.string.fs_tuning_high_g)
    "low-g" -> stringResource(R.string.fs_tuning_low_g)
    else -> id
}

/** An instrument as a song's line and Settings name it: "6-string guitar", "5-string bass", "Ukulele", "Baritone ukulele", "Mandolin". */
@Composable
internal fun kindName(kind: FrettedInstrument): String {
    val strings = YourInstrument.stringsOf(kind)
    return when (Instrument.of(kind)) {
        Instrument.GUITAR -> stringResource(R.string.fs_guitar_with_strings, strings ?: 6)
        Instrument.BASS -> stringResource(R.string.fs_bass_with_strings, strings ?: 4)
        Instrument.UKULELE -> stringResource(if (kind == FrettedInstrument.UKULELE_BARITONE) R.string.fs_ukulele_baritone else R.string.fs_instrument_ukulele)
        Instrument.MANDOLIN -> stringResource(R.string.fs_instrument_mandolin)
        null -> stringResource(R.string.fs_song_tab)
    }
}

/** A kind of [instrument] as its picker lists it: "6 strings" for a guitar or a bass, the size for a ukulele. */
@Composable
private fun kindChoice(instrument: Instrument, kind: FrettedInstrument): String = when (instrument) {
    Instrument.UKULELE -> stringResource(if (kind == FrettedInstrument.UKULELE_BARITONE) R.string.fs_size_baritone else R.string.fs_size_small)
    else -> (YourInstrument.stringsOf(kind) ?: 0).let { pluralStringResource(R.plurals.fs_strings_count, it, it) }
}

@StringRes
private fun handName(h: FrettingHand): Int = when (h) {
    FrettingHand.LEFT -> R.string.fs_hand_left
    FrettingHand.RIGHT -> R.string.fs_hand_right
    FrettingHand.RIGHT_UPSIDE_DOWN -> R.string.fs_hand_right_upside_down
}

@StringRes
private fun readsName(r: Reads): Int = when (r) {
    Reads.TAB -> R.string.fs_reads_tab
    Reads.TAB_AND_NOTATION -> R.string.fs_reads_tab_and_notation
    Reads.NOTATION -> R.string.fs_reads_notation
}

/** Settings' value for the row: "6-string guitar · Standard · Tab". */
@Composable
fun yourInstrumentValue(): String {
    val context = LocalContext.current
    val value = remember { yourInstrumentStore(context).load() }
    return stringResource(R.string.fs_instrument_value, kindName(value.kind),
        tuningName(value.tuning), stringResource(readsName(value.reads)))
}

/** One choice of a picker: its id, the words shown and the words spoken. */
internal class Choice(val id: String, val label: String, val spoken: String = label)

/**
 * "Your instrument" (design/fretscribe/flows.md §2, system.md §5): one question per row, each a picker
 * row that shows its answer. Asked once after the first run, where Not now leaves the defaults, and
 * opened again from Settings. Nothing is kept until Continue or Save (WCAG 3.2.2), and songs already
 * written are never changed by it.
 *
 * [visit] numbers this opening of the screen. The choices being made are kept under it across a
 * rotation or a restore of the app, and an earlier visit's choices are never picked up again.
 */
@Composable
fun YourInstrumentScreen(vm: PlayViewModel, visit: Int = 0) {
    val status by vm.status.collectAsState()
    val context = LocalContext.current
    val store = remember { yourInstrumentStore(context) }
    val firstRun = vm.seatPicker == SeatPickerMode.FIRST_RUN
    val start = remember { store.load() }
    var kind by rememberSaveable(key = "your-instrument-$visit-kind") { mutableStateOf(start.kind) }
    var tuning by rememberSaveable(key = "your-instrument-$visit-tuning") { mutableStateOf(start.tuning) }
    var hand by rememberSaveable(key = "your-instrument-$visit-hand") { mutableStateOf(start.hand) }
    var reads by rememberSaveable(key = "your-instrument-$visit-reads") { mutableStateOf(start.reads) }
    val chosen = YourInstrument(kind, tuning, hand, reads)
    val instrument = chosen.instrument

    fun keep() {
        store.save(chosen)
        // The first run ends on Home; from Settings the focus goes back to the row that opened this.
        if (firstRun) vm.skipSeat() else { vm.focusSeatRow.value = true; vm.back() }
    }

    PlayScaffold(
        title = null,
        onBack = if (firstRun) null else ({ vm.back() }),
        backLabel = stringResource(R.string.settings),
        status = status,
        actions = { if (firstRun) PlainButton(stringResource(R.string.seat_skip), vm::skipSeat, Modifier.testTag("fs-not-now")) },
        bottom = {
            PrimaryButton(stringResource(if (firstRun) R.string.continue_label else R.string.save), ::keep, Modifier.testTag("fs-keep"))
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            ScreenTitle(stringResource(R.string.fs_instrument_title))
            Lead(stringResource(if (firstRun) R.string.fs_instrument_body else R.string.fs_instrument_body_settings))
        }
        RowGroup {
            PickerRow(
                stringResource(R.string.fs_instrument), "instrument", instrument.id,
                Instrument.entries.map { Choice(it.id, stringResource(instrumentName(it))) },
            ) { id ->
                // Another instrument starts in its own usual tuning.
                val next = chosen.withInstrument(Instrument.entries.first { it.id == id })
                kind = next.kind
                tuning = next.tuning
            }
            RowDivider()
            // A mandolin comes in one kind: nothing to ask.
            if (instrument.kinds.size > 1) {
                PickerRow(
                    stringResource(if (instrument == Instrument.UKULELE) R.string.fs_size else R.string.fs_strings), "strings", kind.id.orEmpty(),
                    instrument.kinds.map { Choice(it.id.orEmpty(), kindChoice(instrument, it)) },
                ) { id ->
                    // A tuning the new kind doesn't have goes back to its usual one.
                    val next = chosen.withKind(instrument.kinds.first { it.id == id })
                    kind = next.kind
                    tuning = next.tuning
                }
                RowDivider()
            }
            PickerRow(
                stringResource(R.string.fs_tuning), "tuning", tuning,
                chosen.tunings.map { Choice(it, tuningName(it), tuningName(it, spoken = true)) },
            ) { tuning = it }
            RowDivider()
            PickerRow(
                stringResource(R.string.fs_hand), "hand", hand.id,
                FrettingHand.entries.map { Choice(it.id, stringResource(handName(it))) },
                note = stringResource(R.string.fs_hand_note),
            ) { id -> hand = FrettingHand.entries.first { it.id == id } }
            RowDivider()
            PickerRow(
                stringResource(R.string.fs_reads), "reads", reads.id,
                Reads.entries.map { Choice(it.id, stringResource(readsName(it))) },
            ) { id -> reads = Reads.entries.first { it.id == id } }
        }
    }
}

/**
 * The family's keyboard focus ring: a 2 dp line in the focus colour (ink, paper in dark), 2 dp inside the
 * element's edge, drawn only while the element has the keyboard's focus.
 */
internal fun Modifier.focusRing(focused: Boolean, colour: Color): Modifier = if (!focused) this else drawWithContent {
    drawContent()
    val width = BrasscribeScore.focusWidth.toPx()
    val inset = BrasscribeScore.focusGap.toPx() + width / 2
    drawRoundRect(
        colour, Offset(inset, inset), Size(size.width - 2 * inset, size.height - 2 * inset),
        CornerRadius(BrasscribeSpace.s2.toPx()), Stroke(width),
    )
}

/**
 * A picker row: the question, its answer under it, and the system's dialog of radio choices on a tap or
 * on Enter. The row is one element whose name is the question and the answer; [note] is one more line of
 * the same row.
 */
@Composable
private fun PickerRow(
    label: String, tag: String, selected: String, choices: List<Choice>,
    note: String? = null, onPick: (String) -> Unit,
) {
    var open by rememberSaveable { mutableStateOf(false) }
    val c = BrasscribeTheme.colors
    val current = choices.firstOrNull { it.id == selected }
    val spoken = listOfNotNull(label, current?.spoken, note).joinToString(", ")
    val interaction = remember { MutableInteractionSource() }
    val focused by interaction.collectIsFocusedAsState()
    val rowFocus = remember { FocusRequester() }
    // When the dialog closes, the keyboard's focus is back on the row that opened it.
    fun close() {
        open = false
        runCatching { rowFocus.requestFocus() }
    }
    // The outer box is the one element: it takes the click, the keyboard's focus and the name. The shared
    // row inside only draws, so its texts and the mark are not read a second time.
    Box(
        Modifier.fillMaxWidth()
            // Outside the click's own focus tint, so the ring is drawn over it in its own colour.
            .focusRing(focused, c.focus)
            .focusRequester(rowFocus)
            .clickable(interactionSource = interaction, indication = LocalIndication.current, role = Role.DropdownList) { open = true }
            .semantics { contentDescription = spoken }
            .testTag("fs-row-$tag"),
    ) {
        ListRow(
            label, null,
            modifier = Modifier.clearAndSetSemantics { },
            subtitle = listOfNotNull(current?.label, note).joinToString("\n"),
            trailing = { BcIcon(R.drawable.ic_bc_choose, null, tint = c.textMuted) },
        )
    }
    if (open) PickerDialog(label, tag, selected, choices, ::close, onPick)
}

/**
 * The dialog of a picker: [choices] as one radio group under the question, the chosen one marked, each a
 * full-size target with the keyboard's focus ring. A choice picks and closes; Cancel and Back close.
 */
@Composable
internal fun PickerDialog(label: String, tag: String, selected: String, choices: List<Choice>, close: () -> Unit, onPick: (String) -> Unit) {
    val c = BrasscribeTheme.colors
    AlertDialog(
        onDismissRequest = close,
        title = { Text(label) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()).selectableGroup()) {
                choices.forEach { choice ->
                    val on = choice.id == selected
                    val source = remember { MutableInteractionSource() }
                    val onKeys by source.collectIsFocusedAsState()
                    // With a keyboard, the dialog opens on the chosen one, and the arrows move from there.
                    val start = remember { FocusRequester() }
                    // (Asked for once the dialog's window has the focus; before that there is nothing to focus in.)
                    val inFront = LocalWindowInfo.current.isWindowFocused
                    if (on) LaunchedEffect(inFront) { if (inFront) runCatching { start.requestFocus() } }
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            .focusRing(onKeys, c.focus)
                            .then(if (on) Modifier.focusRequester(start) else Modifier)
                            .selectable(selected = on, interactionSource = source, indication = LocalIndication.current, role = Role.RadioButton) {
                                onPick(choice.id); close()
                            }
                            .semantics { contentDescription = choice.spoken }
                            .testTag("fs-$tag-${choice.id}")
                            .padding(horizontal = BrasscribeSpace.s2, vertical = BrasscribeSpace.s1),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4),
                    ) {
                        RadioButton(selected = on, onClick = null,
                            colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
                        Text(choice.label, Modifier.weight(1f).clearAndSetSemantics { }, style = MaterialTheme.typography.bodyLarge, color = c.text)
                    }
                }
            }
        },
        confirmButton = { PlainButton(stringResource(R.string.cancel), close) },
    )
}
