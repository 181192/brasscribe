package no.brasscribe.play.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.ui.theme.LocalPlayTokens

@Composable
fun CompanionScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val state by vm.companionState.collectAsState()
    val settings = vm.container.settings
    var url by rememberSaveable { mutableStateOf(settings.url) }
    var code by rememberSaveable { mutableStateOf("") }
    var fixture by rememberSaveable { mutableStateOf(vm.container.usingFixture) }

    PlayScaffold(title = stringResource(R.string.companion_title), onBack = vm::back, status = status) {
        Heading(stringResource(R.string.companion_title))
        Text(stringResource(R.string.companion_explain))
        OutlinedTextField(url, { url = it.trim() }, label = { Text(stringResource(R.string.companion_address)) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(code, { code = it.trim() }, label = { Text(stringResource(R.string.companion_code)) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
        BigButton(stringResource(R.string.companion_connect), { fixture = false; vm.connect(url, code) }, enabled = url.startsWith("http"))
        state?.let { Text(it, color = LocalPlayTokens.current.text) }
        var heavy by rememberSaveable { mutableStateOf(settings.allowHeavy) }
        ToggleRow(stringResource(R.string.companion_allow_heavy), heavy) { heavy = it; settings.allowHeavy = it }
        Text(stringResource(R.string.companion_allow_heavy_desc), color = LocalPlayTokens.current.textMuted)
        if (vm.container.hasFixtures) {
            ToggleRow(stringResource(R.string.companion_use_fixture), fixture) { fixture = it; vm.useFixture(it) }
            Text(stringResource(R.string.companion_use_fixture_desc), color = LocalPlayTokens.current.textMuted)
        }
    }
}

@Composable
fun AboutScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    PlayScaffold(title = stringResource(R.string.about_title), onBack = vm::back, status = status) {
        Heading(stringResource(R.string.about_title))
        Text(stringResource(R.string.about_text))
        Text("CoreBridge: ${vm.container.core.name}", color = LocalPlayTokens.current.textMuted)
    }
}
