package no.kalli.fretscribe

import android.content.res.Resources
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.model.Lang
import no.kalli.scribe.play.ui.OutlineButton
import no.kalli.scribe.play.ui.PlainButton
import no.kalli.scribe.play.ui.PlaySheet
import no.kalli.scribe.play.ui.currentLang
import no.kalli.scribe.tab.NoteEdit
import no.kalli.scribe.tab.TabEdits
import no.kalli.scribe.tab.TabIndex
import no.kalli.scribe.tab.TabPiece

/** A place a pitch can be played: the string (1 the highest) and the fret. */
data class FretPlace(val string: Int, val fret: Int)

/** Where the notes of a tab can be played, and which notes share a beat. */
object FixNote {
    /** How far from a fret number's middle a tap still finds it, to each side and above and below: 48 dp across. */
    val REACH = 24.dp

    /** The frets a place is offered up to when the song does not say how many the instrument has. */
    const val FRETS = 24

    /**
     * Every place [pitch] can be played on an instrument whose open strings are [open] (lowest first, as the page's
     * staff is tuned, a capo counted in) with [frets] frets, the highest string first; without the strings [taken] by
     * other notes of the same beat.
     */
    fun places(pitch: Int, open: List<Int>, frets: Int = FRETS, taken: Set<Int> = emptySet()): List<FretPlace> =
        open.indices.reversed().mapNotNull { i ->
            val string = open.size - i
            val fret = pitch - open[i]
            if (fret in 0..frets && string !in taken) FretPlace(string, fret) else null
        }

    /** The notes that start on the beat at [onset] of [bar] on the staff the marks stand on, each as its first piece, in the order they are written. */
    fun at(index: TabIndex, bar: Int, onset: Int): List<TabPiece> =
        index.pieces.filter { it.staff == index.markStaff && it.bar == bar && it.onset == onset && it.first }
}

/** "3rd string, fret 7" for a place; "3rd string, open" at fret 0. */
internal fun placeWords(res: Resources, place: FretPlace): String =
    if (place.fret == 0) res.getString(R.string.fs_fix_place_open, TabWords.ordinal(res, place.string))
    else res.getString(R.string.fs_fix_place, TabWords.ordinal(res, place.string), place.fret)

/**
 * Fix a note (design/brands/fretscribe/flows.md §10), in a first form: the notes of the beat that was tapped, each
 * with every place its pitch can be played (a tap moves it there), whether it is a ghost note, and what can be done
 * with it: keep a doubtful note as it is, leave the note out, or take it back to what Fretscribe wrote. Every change
 * is on the page at once and is saved with the song ([change] is given the song's file with the fix in it).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun FixNoteSheet(sheet: TabSheet, bar: Int, onset: Int, change: (String) -> Unit, close: () -> Unit) {
    val c = ScribeTheme.colors
    val res = LocalResources.current
    val bokmal = currentLang() == Lang.NB
    val notes = FixNote.at(sheet.index, bar, onset)
    if (notes.isEmpty()) { close(); return }
    val open = SongFacts.openStrings(sheet.raw)
    val frets = sheet.tab?.instrument?.frets?.takeIf { it > 0 } ?: FixNote.FRETS
    PlaySheet(onDismiss = close, containerColor = c.bg) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = ScribeSpace.s4).testTag("fs-fix"),
            verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
            Text(stringResource(R.string.fs_fix_title), style = MaterialTheme.typography.titleLarge, color = c.text, modifier = Modifier.semantics { heading() })
            notes.forEachIndexed { n, piece ->
                val edit = TabEdits.of(sheet.raw, piece.note)
                if (n > 0) HorizontalDivider(thickness = 1.dp, color = c.border)
                // Which note: where it is on the page and how it is played now.
                Text(TabWords.barBeat(res, piece) + " " + TabWords.place(res, piece, bokmal), style = MaterialTheme.typography.bodyLarge, color = c.text,
                    modifier = Modifier.testTag("fs-fix-note-${piece.note}"))
                if (edit.was != null) Text(stringResource(R.string.fs_fix_was, placeWords(res, FretPlace(edit.was!!.first, edit.was!!.second))),
                    style = MaterialTheme.typography.bodyMedium, color = c.textMuted, modifier = Modifier.testTag("fs-fix-was-${piece.note}"))
                val string = piece.string
                val fret = piece.fret
                if (string != null && fret != null && open.isNotEmpty()) {
                    val taken = notes.filter { it.note != piece.note }.mapNotNull { it.string }.toSet()
                    val places = FixNote.places(piece.pitch, open, frets, taken)
                    if (places.size > 1) {
                        Text(stringResource(R.string.fs_fix_where), style = MaterialTheme.typography.titleMedium, color = c.text, modifier = Modifier.semantics { heading() })
                        Column(Modifier.selectableGroup()) {
                            places.forEach { place ->
                                val on = place.string == string && place.fret == fret
                                Row(
                                    Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                        .selectable(selected = on, role = Role.RadioButton) { if (!on) change(TabEdits.place(sheet.raw, piece.note, place.string, place.fret)) }
                                        .testTag("fs-fix-place-${piece.note}-${place.string}").padding(horizontal = ScribeSpace.s2, vertical = ScribeSpace.s1),
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
                                ) {
                                    RadioButton(selected = on, onClick = null, colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
                                    Text(placeWords(res, place), Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge, color = c.text)
                                }
                            }
                        }
                    } else {
                        Text(stringResource(R.string.fs_fix_one_place), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                    }
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 56.dp)
                            .toggleable(value = edit.ghost, role = Role.Switch) { change(TabEdits.ghost(sheet.raw, piece.note, it)) }
                            .testTag("fs-fix-ghost-${piece.note}").padding(horizontal = ScribeSpace.s2, vertical = ScribeSpace.s1),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s3),
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(stringResource(R.string.fs_fix_ghost), style = MaterialTheme.typography.bodyLarge, color = c.text)
                            Text(stringResource(R.string.fs_fix_ghost_tip), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                        }
                        Switch(checked = edit.ghost, onCheckedChange = null, colors = SwitchDefaults.colors(
                            checkedTrackColor = c.primary, checkedThumbColor = c.onPrimary, uncheckedTrackColor = c.surfaceRaised, uncheckedThumbColor = c.borderStrong, uncheckedBorderColor = c.borderStrong))
                    }
                }
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s2), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s1)) {
                    if (piece.confidence != null) OutlineButton(stringResource(R.string.fs_fix_keep), { change(TabEdits.keep(sheet.raw, piece.note)) },
                        Modifier.testTag("fs-fix-keep-${piece.note}"), fill = false)
                    OutlineButton(stringResource(R.string.fs_fix_leave_out), { change(TabEdits.leaveOut(sheet.raw, piece.note)); if (notes.size == 1) close() },
                        Modifier.testTag("fs-fix-leave-out-${piece.note}"), fill = false)
                    if (edit.changed) OutlineButton(stringResource(R.string.fs_fix_revert), { change(TabEdits.revert(sheet.raw, piece.note)) },
                        Modifier.testTag("fs-fix-revert-${piece.note}"), fill = false)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                PlainButton(stringResource(R.string.fs_practice_sound_done), close, Modifier.testTag("fs-fix-done"))
            }
        }
    }
}

/** The notes left out of the tab, each with Put back: a note that is not on the page cannot be tapped. */
@Composable
internal fun LeftOutDialog(sheet: TabSheet, change: (String) -> Unit, close: () -> Unit) {
    val c = ScribeTheme.colors
    val res = LocalResources.current
    val bokmal = currentLang() == Lang.NB
    val out = sheet.leftOut
    if (out.isEmpty()) { close(); return }
    AlertDialog(
        onDismissRequest = close,
        title = { Text(pluralStringResource(R.plurals.fs_fix_left_out, out.size, out.size), Modifier.semantics { heading() }) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
                out.forEach { piece ->
                    val words = TabWords.barBeat(res, piece) + " " + TabWords.place(res, piece, bokmal)
                    val back = stringResource(R.string.fs_fix_put_back)
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
                        Text(words, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge, color = c.text)
                        // Named with its note: several of them would otherwise all say "Put back".
                        OutlineButton(back, { change(TabEdits.leaveOut(sheet.raw, piece.note, out = false)) },
                            Modifier.testTag("fs-fix-put-back-${piece.note}").semantics { contentDescription = "$back. $words" }, fill = false)
                    }
                }
            }
        },
        confirmButton = { PlainButton(stringResource(R.string.fs_practice_sound_done), close, Modifier.testTag("fs-fix-left-out-done")) },
    )
}
