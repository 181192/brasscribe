package no.brasscribe.play.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R

/**
 * Pairing with Brasscribe on your computer. The copy has no commands; the command and the address
 * details are under "Details for the band's tech person" (brand.md, Apple pairing).
 */
@Composable
fun CompanionScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val state by vm.companionState.collectAsState()
    val settings = vm.container.settings
    val c = BrasscribeTheme.colors
    var url by rememberSaveable { mutableStateOf(settings.url) }
    var code by rememberSaveable { mutableStateOf("") }
    var fixture by rememberSaveable { mutableStateOf(vm.container.usingFixture) }
    var details by rememberSaveable { mutableStateOf(false) }
    var heavy by rememberSaveable { mutableStateOf(settings.allowHeavy) }

    PlayScaffold(
        title = null, onBack = vm::back, backLabel = stringResource(R.string.settings), status = status,
        bottom = { PrimaryButton(stringResource(R.string.companion_connect), { fixture = false; vm.connect(url, code) }, enabled = url.startsWith("http")) },
    ) {
        ScreenTitle(stringResource(R.string.companion_title))
        Lead(stringResource(R.string.companion_explain))
        OutlinedTextField(code, { code = it.trim() }, label = { Text(stringResource(R.string.companion_code)) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(url, { url = it.trim() }, label = { Text(stringResource(R.string.companion_address)) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        state?.let { Text(it, color = c.text, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) }
        PlainButton(stringResource(if (details) R.string.details_hide else R.string.details_show), { details = !details })
        if (details) {
            Text(stringResource(R.string.companion_tech_details), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            RowGroup {
                ListRow(stringResource(R.string.companion_allow_heavy), null, subtitle = stringResource(R.string.companion_allow_heavy_desc), chevron = false,
                    trailing = { PracticeChip(stringResource(if (heavy) R.string.on else R.string.off), heavy, { heavy = !heavy; settings.allowHeavy = heavy },
                        accessibleName = stringResource(R.string.companion_allow_heavy)) })
                if (vm.container.hasFixtures) {
                    RowDivider()
                    ListRow(stringResource(R.string.companion_use_fixture), null, subtitle = stringResource(R.string.companion_use_fixture_desc), chevron = false,
                        trailing = { PracticeChip(stringResource(if (fixture) R.string.on else R.string.off), fixture, { fixture = !fixture; vm.useFixture(fixture) },
                            accessibleName = stringResource(R.string.companion_use_fixture)) })
                }
            }
        }
    }
}

@Composable
fun AboutScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    PlayScaffold(title = null, onBack = vm::back, backLabel = stringResource(R.string.settings), status = status) {
        BrandMark(androidx.compose.ui.unit.Dp(56f))
        ScreenTitle(stringResource(R.string.about_title))
        Text(stringResource(R.string.about_text), style = MaterialTheme.typography.bodyLarge)
        Text(stringResource(R.string.about_font), style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
        Text("CoreBridge: ${vm.container.core.name}", style = MaterialTheme.typography.bodySmall, color = BrasscribeTheme.colors.textMuted)
    }
}

