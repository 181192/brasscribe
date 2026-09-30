package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.design.systemHighContrast
import no.brasscribe.play.Appearance
import no.brasscribe.play.AppearanceStore
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R

@Composable
fun appearanceLabel(a: Appearance): String = stringResource(
    when (a) {
        Appearance.SYSTEM -> R.string.appearance_system
        Appearance.LIGHT -> R.string.appearance_light
        Appearance.DARK -> R.string.appearance_dark
        Appearance.PINK_LIGHT -> R.string.appearance_pink_light
        Appearance.PINK_DARK -> R.string.appearance_pink_dark
    },
)

/**
 * Settings › Display › Appearance (design/system.md §10): a row showing the current choice that opens
 * a single-choice dialog (the ListPreference pattern). Choosing applies at once and closes the dialog;
 * focus goes back to the row. With the phone's high contrast on, one line says that it decides.
 */
@Composable
fun AppearanceRow(vm: PlayViewModel) {
    val current = vm.container.appearance
    var open by rememberSaveable { mutableStateOf(false) }
    val value = appearanceLabel(current)
    ListRow(
        stringResource(R.string.settings_appearance), { open = true },
        modifier = Modifier.semantics { stateDescription = value }.testTag("setting-appearance"),
        subtitle = value, icon = R.drawable.ic_appearance, chevron = false, role = Role.DropdownList,
    )
    if (systemHighContrast()) {
        Text(
            stringResource(R.string.appearance_contrast_note),
            Modifier.padding(start = BrasscribeSpace.s4, end = BrasscribeSpace.s4, bottom = BrasscribeSpace.s3),
            style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted,
        )
    }
    if (open) {
        AlertDialog(
            onDismissRequest = { open = false },
            title = { Text(stringResource(R.string.settings_appearance)) },
            text = {
                Column(Modifier.selectableGroup()) {
                    AppearanceStore.choices(vm.container.pinkUnlocked).forEach { a ->
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                .selectable(selected = a == current, role = Role.RadioButton) {
                                    vm.container.updateAppearance(a); open = false
                                }
                                .testTag("appearance-${a.key}"),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4),
                        ) {
                            RadioButton(selected = a == current, onClick = null)
                            Text(appearanceLabel(a), style = MaterialTheme.typography.bodyLarge)
                        }
                    }
                }
            },
            confirmButton = { TextButton({ open = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}
