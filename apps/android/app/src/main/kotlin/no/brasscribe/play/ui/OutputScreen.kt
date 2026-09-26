package no.brasscribe.play.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.update
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.Difficulty
import no.brasscribe.play.Lineup
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.model.Lang

/** Tonic names by pitch class, flats first as brass bands read them; nb has B for B♭ and H for B. */
private val TONIC_EN = listOf("C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")
private val TONIC_NB = listOf("C", "Dess", "D", "Ess", "E", "F", "Fiss", "G", "Ass", "A", "B", "H")

/** "D major" for a key signature (fifths) and mode, moved by [shift] semitones. */
@Composable
fun keyName(fifths: Int, minor: Boolean, shift: Int, lang: Lang): String {
    val majorPc = Math.floorMod(fifths * 7, 12)
    val pc = Math.floorMod(majorPc + (if (minor) 9 else 0) + shift, 12)
    val tonic = (if (lang == Lang.NB) TONIC_NB else TONIC_EN)[pc]
    val name = if (lang == Lang.NB && minor) tonic.lowercase() else tonic
    return stringResource(if (minor) R.string.key_minor else R.string.key_major, name)
}

/**
 * How should the score be? (mockups/png/choose-output-*): Which band?, How hard? with its tip, and
 * Key, then Show the score. Full and Small band map to the arranger's full and minimal lineups; the
 * three difficulty segments to faithful, standard and easier.
 */
@Composable
fun OutputScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val options by vm.output.collectAsState()
    val result by vm.result.collectAsState()
    val busy by vm.busy.collectAsState()
    val c = BrasscribeTheme.colors
    val lang = currentLang()
    // Band and difficulty are arranged by the Rust core (on-device results) or by Brasscribe on the
    // computer (a new run with the choices); without either only the key remains.
    val r = result
    val canArrange = r != null && ((r.onDevice && vm.container.core.name.startsWith("rust")) || (!r.onDevice && r.audioId != null))
    val lineups = listOf(Lineup.FULL, Lineup.MINIMAL)
    val key = r?.composition?.keys?.firstOrNull()

    PlayScaffold(
        title = null, onBack = vm::back, backLabel = r?.composition?.title?.ifBlank { null } ?: stringResource(R.string.back), status = status,
        bottom = {
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
            PrimaryButton(stringResource(R.string.output_apply), { vm.applyOutput { vm.navigate(Screen.SCORE) } }, enabled = !busy)
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            ScreenTitle(stringResource(R.string.output_title))
            Lead(stringResource(R.string.output_lead))
        }
        SubHeading(stringResource(R.string.lineup))
        ChoiceGroup(lineups.size) {
            lineups.forEachIndexed { i, l ->
                ChoiceCard(stringResource(l.label), stringResource(l.desc), options.lineup == l, canArrange || l == Lineup.FULL, i) {
                    vm.output.update { it.copy(lineup = l) }
                }
            }
        }
        SubHeading(stringResource(R.string.difficulty))
        val levels = listOf(Difficulty.EASIER, Difficulty.STANDARD, Difficulty.FAITHFUL)
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            levels.forEachIndexed { i, d ->
                SegmentedButton(
                    selected = options.difficulty == d, onClick = { vm.output.update { it.copy(difficulty = d) } },
                    shape = SegmentedButtonDefaults.itemShape(i, levels.size), enabled = canArrange || d == Difficulty.FAITHFUL,
                    colors = SegmentedButtonDefaults.colors(
                        activeContainerColor = c.surfaceRaised, activeContentColor = c.text, activeBorderColor = c.borderStrong,
                        inactiveContainerColor = c.secondary, inactiveContentColor = c.textMuted, inactiveBorderColor = c.border,
                    ),
                    icon = {},
                    modifier = Modifier.heightIn(min = 48.dp),
                ) { Text(stringResource(d.label), maxLines = 2) }
            }
        }
        InfoNote(stringResource(if (canArrange) R.string.difficulty_tip else R.string.difficulty_unsupported), boxed = false)
        SubHeading(stringResource(R.string.key_label))
        val shiftText = if (options.keyShift == 0) stringResource(R.string.key_as_recorded)
        else stringResource(R.string.key_shifted, (if (options.keyShift > 0) "+" else "−") +
            pluralStringResource(R.plurals.key_shift, kotlin.math.abs(options.keyShift), kotlin.math.abs(options.keyShift)))
        Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3), verticalAlignment = Alignment.CenterVertically) {
            val down = stringResource(R.string.key_down)
            val up = stringResource(R.string.key_up)
            FilledTonalIconButton({ vm.output.update { it.copy(keyShift = (it.keyShift - 1).coerceAtLeast(-6)) } },
                Modifier.size(56.dp).semantics { contentDescription = down }, shape = BrasscribeButtonShape,
                colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = c.secondary, contentColor = c.text)) { Text("−", style = MaterialTheme.typography.titleLarge) }
            Column(
                Modifier.weight(1f).heightIn(min = 56.dp).border(1.dp, c.borderStrong, BrasscribeButtonShape)
                    .padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s2)
                    .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
            ) {
                if (key != null) Text(keyName(key.fifths, key.mode == "minor", options.keyShift, lang), style = MaterialTheme.typography.titleMedium)
                Text(shiftText, style = MaterialTheme.typography.bodyMedium, color = if (key != null) c.textMuted else c.text)
            }
            FilledTonalIconButton({ vm.output.update { it.copy(keyShift = (it.keyShift + 1).coerceAtMost(6)) } },
                Modifier.size(56.dp).semantics { contentDescription = up }, shape = BrasscribeButtonShape,
                colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = c.secondary, contentColor = c.text)) { Text("+", style = MaterialTheme.typography.titleLarge) }
        }
    }
}
