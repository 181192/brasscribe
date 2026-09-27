package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.connection.ConnectionState

/** The sentence for [state], in this language. */
@Composable
fun connectionText(vm: PlayViewModel, state: ConnectionState): String = when (state) {
    is ConnectionState.Connected -> stringResource(R.string.conn_connected, vm.serverDisplayName(state.serverName))
    is ConnectionState.Reconnecting -> stringResource(R.string.conn_reconnecting, vm.serverDisplayName(state.serverName))
    is ConnectionState.Offline -> stringResource(R.string.conn_offline)
    is ConnectionState.NeedsPairing -> stringResource(R.string.conn_needs_pairing)
}

fun connectionIcon(state: ConnectionState): Int = when (state) {
    is ConnectionState.Connected -> R.drawable.ic_bc_computer
    is ConnectionState.Reconnecting -> R.drawable.ic_bc_network
    is ConnectionState.Offline -> R.drawable.ic_bc_network
    is ConnectionState.NeedsPairing -> R.drawable.ic_bc_pair_phone
}

/**
 * The connection status row (Home, and Brasscribe on your computer): an icon and words, never colour
 * alone. Only the words are a polite live region, and they change only when the state does, so a
 * heartbeat that finds nothing new says nothing. The action is plain: the screen's primary stays its own.
 */
@Composable
fun ConnectionStatusRow(vm: PlayViewModel, modifier: Modifier = Modifier, onConnectionScreen: Boolean = false) {
    val state by vm.connection.state.collectAsState()
    val c = BrasscribeTheme.colors
    Row(
        modifier.fillMaxWidth().heightIn(min = 48.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
    ) {
        BcIcon(connectionIcon(state), null, Modifier.padding(top = BrasscribeSpace.s3), tint = c.textMuted)
        // The action goes under the words, so neither is squeezed at large text or in Norwegian.
        Column(Modifier.weight(1f)) {
            Text(
                connectionText(vm, state), style = MaterialTheme.typography.bodyMedium, color = c.text,
                modifier = Modifier.padding(top = BrasscribeSpace.s3).semantics { liveRegion = LiveRegionMode.Polite },
            )
            val s = state
            val action: Pair<String, () -> Unit>? = when {
                s is ConnectionState.Offline && s.paired -> stringResource(R.string.companion_connect) to { vm.connection.retry() }
                s is ConnectionState.Offline && !onConnectionScreen -> stringResource(R.string.companion_connect) to { vm.navigate(Screen.COMPANION) }
                s is ConnectionState.NeedsPairing && !onConnectionScreen -> stringResource(R.string.conn_pair_again) to { vm.navigate(Screen.COMPANION) }
                else -> null
            }
            // A plain button whose words line up with the sentence above.
            if (action != null) PlainButton(action.first, action.second, Modifier.offset(x = -BrasscribeSpace.s3))
        }
    }
}
