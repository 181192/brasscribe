package no.brasscribe.play.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PinkUnlock
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.connection.ConnectionState
import no.brasscribe.play.engine.PairLink

/**
 * Brasscribe on your computer: the connection status, then the ways to pair (scan the QR code, type
 * the code, or ask the computer to allow this phone). A pairing link from outside the app waits here
 * for Connect. Addresses, the server id and errors are under "Details for the band's tech person".
 */
@Composable
fun CompanionScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val state by vm.companionState.collectAsState()
    val link by vm.pendingLink.collectAsState()
    val match by vm.matchCode.collectAsState()
    val askAgain by vm.askAgain.collectAsState()
    val connection by vm.connection.state.collectAsState()
    val lastAnswered by vm.connection.lastAnswered.collectAsState()
    val settings = vm.container.settings
    val c = BrasscribeTheme.colors
    val context = LocalContext.current
    var url by rememberSaveable { mutableStateOf(settings.url) }
    var code by rememberSaveable { mutableStateOf("") }
    var details by rememberSaveable { mutableStateOf(false) }
    var heavy by rememberSaveable { mutableStateOf(settings.allowHeavy) }
    val discovery = vm.container.discovery
    val found by discovery.engines.collectAsState()
    DisposableEffect(discovery) {
        discovery.start()
        // Asking the computer survives rotation; the view model ends it when the user leaves this place.
        onDispose { discovery.stop() }
    }

    fun scan() {
        // The system code scanner (Google Play services): no camera permission, and nothing bundled.
        val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
        runCatching {
            GmsBarcodeScanning.getClient(context, options).startScan()
                .addOnSuccessListener { b ->
                    val text = b.rawValue.orEmpty()
                    val parsed = PairLink.parse(text)
                    if (parsed == null) vm.say(R.string.pair_link_invalid) else vm.pairWithLink(parsed)
                }
                .addOnFailureListener { vm.say(R.string.pair_scan_unavailable) }
        }.onFailure { vm.say(R.string.pair_scan_unavailable) }
    }

    val pending = link
    PlayScaffold(
        title = null, onBack = vm::back, backLabel = stringResource(R.string.settings), status = status,
        bottom = {
            when {
                pending != null -> PrimaryButton(stringResource(R.string.companion_connect), { vm.pairWithLink(pending) })
                match == null -> PrimaryButton(stringResource(R.string.companion_connect), { vm.connect(url, code) }, enabled = url.startsWith("http"))
            }
        },
    ) {
        ScreenTitle(stringResource(R.string.companion_title))
        ConnectionStatusRow(vm, onConnectionScreen = true)
        when {
            pending != null -> {
                SubHeading(stringResource(R.string.pair_link_title, vm.serverDisplayName(pending.serverName)))
                // The name comes from the link; the address is where this phone will actually connect.
                Text(
                    if (pending.hosts.isEmpty()) stringResource(R.string.pair_link_address_by_name)
                    else stringResource(R.string.pair_link_address, pending.hosts.joinToString(", ")),
                    color = c.textMuted,
                )
                state?.let { Text(it, color = c.text, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) }
                PlainButton(stringResource(R.string.cancel), { vm.pendingLink.value = null })
            }
            match != null -> MatchCode(match!!) { vm.cancelAsk() }
            else -> {
                Lead(stringResource(R.string.companion_explain))
                SecondaryButton(stringResource(R.string.pair_scan), ::scan, icon = R.drawable.ic_bc_pair_phone)
                if (found.isEmpty()) {
                    Text(stringResource(R.string.companion_searching), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                } else {
                    RowGroup {
                        found.forEachIndexed { i, engine ->
                            if (i > 0) RowDivider()
                            ListRow(vm.serverDisplayName(engine.name), { url = engine.url }, chevron = false,
                                trailing = if (url == engine.url) ({ Text(stringResource(R.string.companion_chosen), color = c.textMuted) }) else null)
                        }
                    }
                }
                OutlinedTextField(code, { code = it.trim() }, label = { Text(stringResource(R.string.companion_code)) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
                state?.let { Text(it, color = c.text, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) }
                if (askAgain != null) SecondaryButton(stringResource(R.string.pair_ask_again), { vm.askComputer(askAgain!!) }, icon = R.drawable.ic_bc_retry)
                else PlainButton(stringResource(R.string.pair_ask), { vm.askComputer(url) }, enabled = url.startsWith("http"))
            }
        }
        PlainButton(stringResource(if (details) R.string.details_hide else R.string.details_show), { details = !details })
        if (details) {
            Text(stringResource(R.string.companion_tech_details), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            OutlinedTextField(url, { url = it.trim() }, label = { Text(stringResource(R.string.companion_address)) }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
            val facts = listOfNotNull(
                stringResource(R.string.conn_detail_address, settings.url),
                settings.serverId?.let { stringResource(R.string.conn_detail_server_id, it) },
                lastAnswered?.let { stringResource(R.string.conn_detail_last_seen, java.text.DateFormat.getTimeInstance().format(java.util.Date(it))) },
                vm.lastConnectError?.let { stringResource(R.string.conn_detail_last_error, it) },
            )
            if (settings.paired) facts.forEach { Text(it, style = MaterialTheme.typography.bodyMedium, color = c.textMuted) }
            RowGroup {
                ListRow(stringResource(R.string.companion_allow_heavy), null, subtitle = stringResource(R.string.companion_allow_heavy_desc), chevron = false,
                    trailing = { PracticeChip(stringResource(if (heavy) R.string.on else R.string.off), heavy, { heavy = !heavy; settings.allowHeavy = heavy },
                        accessibleName = stringResource(R.string.companion_allow_heavy)) })
            }
            if (settings.paired && connection !is ConnectionState.Offline) OutlineButton(stringResource(R.string.pair_forget), vm::unpair)
        }
    }
}

/** The four digits both screens show, large; read out one digit at a time. */
@Composable
private fun MatchCode(code: String, cancel: () -> Unit) {
    val c = BrasscribeTheme.colors
    Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
        Text(stringResource(R.string.pair_ask_waiting), style = MaterialTheme.typography.bodyLarge)
        Surface(shape = MaterialTheme.shapes.large, color = c.surfaceRaised, border = androidx.compose.foundation.BorderStroke(1.dp, c.border)) {
            Text(
                code.toList().joinToString(" "),
                style = MaterialTheme.typography.displayMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 4.sp),
                modifier = Modifier.fillMaxWidth().padding(BrasscribeSpace.s4).semantics { contentDescription = code.toList().joinToString(", ") },
            )
        }
        PlainButton(stringResource(R.string.cancel), cancel)
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
        VersionRow(vm)
    }
}

/**
 * The version, which is also the way into the hidden Pink palette (design/system.md §10): five
 * activations in a row unlock it. It is a real button, so a TalkBack double-tap, a keyboard or a
 * switch reaches it as well as a finger; nothing on screen says so.
 */
@Composable
private fun VersionRow(vm: PlayViewModel) {
    val unlock = remember { PinkUnlock(vm.container.pinkUnlocked) }
    Text(
        stringResource(R.string.about_version, no.brasscribe.play.BuildConfig.VERSION_NAME),
        style = MaterialTheme.typography.bodyMedium,
        color = BrasscribeTheme.colors.textMuted,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .clickable(role = Role.Button) {
                if (unlock.tap()) {
                    vm.container.unlockPink()
                    vm.say(R.string.pink_unlocked)
                }
            }
            .wrapContentHeight(Alignment.CenterVertically)
            .testTag("about-version"),
    )
}

