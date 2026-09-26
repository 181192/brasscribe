package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CollectionInfo
import androidx.compose.ui.semantics.collectionInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.update
import no.brasscribe.play.Difficulty
import no.brasscribe.play.Lineup
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.ui.theme.LocalPlayTokens

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OutputScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val options by vm.output.collectAsState()
    val result by vm.result.collectAsState()
    var expanded by remember { mutableStateOf(false) }
    val t = LocalPlayTokens.current
    // Lineup, difficulty and key are arranged by the Rust core (on-device results) or by the engine
    // (a new job with the options); without either only the display-only choices remain.
    val r = result
    val canArrange = r != null && ((r.onDevice && vm.container.core.name.startsWith("rust")) || (!r.onDevice && r.audioId != null))
    val lineups = if (canArrange) listOf(Lineup.FULL, Lineup.MINIMAL, Lineup.SOLO) else listOf(Lineup.FULL, Lineup.SOLO)
    val busy by vm.busy.collectAsState()

    PlayScaffold(title = stringResource(R.string.output_title), onBack = vm::back, status = status) {
        Heading(stringResource(R.string.output_title))
        ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
            OutlinedTextField(
                value = stringResource(options.lineup.label),
                onValueChange = {},
                readOnly = true,
                label = { Text(stringResource(R.string.lineup)) },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
            )
            ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                lineups.forEach { l ->
                    DropdownMenuItem(
                        text = { Text(stringResource(l.label)) },
                        onClick = { vm.output.update { it.copy(lineup = l) }; expanded = false },
                        modifier = Modifier.heightIn(min = 48.dp),
                    )
                }
            }
        }
        SubHeading(stringResource(R.string.difficulty))
        Column(Modifier.selectableGroup().semantics { collectionInfo = CollectionInfo(3, 1) }) {
            Difficulty.entries.forEachIndexed { i, d ->
                // Only "faithful" exists in this engine version; the others are shown, disabled, with the reason.
                RadioRow(stringResource(d.label), null, options.difficulty == d, canArrange || d == Difficulty.FAITHFUL, i, 3) {
                    vm.output.update { it.copy(difficulty = d) }
                }
            }
        }
        if (!canArrange) Text(stringResource(R.string.difficulty_unsupported), color = t.textMuted)
        if (busy) androidx.compose.material3.LinearProgressIndicator(Modifier.fillMaxWidth())
        SubHeading(stringResource(R.string.key_label))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = { vm.output.update { it.copy(keyShift = (it.keyShift - 1).coerceAtLeast(-6)) } }, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(stringResource(R.string.key_down))
            }
            Text(
                if (options.keyShift == 0) stringResource(R.string.key_as_recorded)
                else (if (options.keyShift > 0) "+" else "−") + pluralStringResource(R.plurals.key_shift, kotlin.math.abs(options.keyShift), kotlin.math.abs(options.keyShift)),
            )
            OutlinedButton(onClick = { vm.output.update { it.copy(keyShift = (it.keyShift + 1).coerceAtMost(6)) } }, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(stringResource(R.string.key_up))
            }
        }
        BigButton(stringResource(R.string.output_apply), { vm.applyOutput { vm.navigate(Screen.SCORE) } }, enabled = !busy)
    }
}
