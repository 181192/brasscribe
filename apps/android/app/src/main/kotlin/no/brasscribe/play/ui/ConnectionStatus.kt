package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
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
    // A different shape from "looking for": the state never rests on the words alone. Where the phone makes scores
    // itself, nothing is wrong without the computer: an ⓘ, not a warning.
    is ConnectionState.Offline -> if (no.brasscribe.play.Product.MAKES_SCORES_ON_THE_PHONE) R.drawable.ic_bc_info else R.drawable.ic_bc_attention
    is ConnectionState.NeedsPairing -> R.drawable.ic_bc_pair_phone
}

/**
 * The connection status row (Home, and Brasscribe on your computer), in the same form as Apple's: a
 * bordered surface row with the state's icon and words on the left and, when there is something to do,
 * an outline button on the right (below the words at large text). Never colour alone. Only the words are
 * a polite live region, and they change only when the state does, so a heartbeat that finds nothing new
 * says nothing. The button is outline: the screen's primary stays its own.
 */
@Composable
fun ConnectionStatusRow(vm: PlayViewModel, modifier: Modifier = Modifier, onConnectionScreen: Boolean = false) {
    val state by vm.connection.state.collectAsState()
    val c = BrasscribeTheme.colors
    val s = state
    val action: Pair<String, () -> Unit>? = when {
        s is ConnectionState.Offline && s.paired -> stringResource(R.string.companion_connect) to { vm.connection.retry() }
        s is ConnectionState.Offline && !onConnectionScreen -> stringResource(R.string.companion_connect) to { vm.navigate(Screen.COMPANION) }
        s is ConnectionState.NeedsPairing && !onConnectionScreen -> stringResource(R.string.conn_pair_again) to { vm.navigate(Screen.COMPANION) }
        else -> null
    }
    val words = @Composable { m: Modifier ->
        Row(m, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            BcIcon(connectionIcon(state), null, tint = c.text)
            Text(
                connectionText(vm, state), style = MaterialTheme.typography.bodyMedium, color = c.text,
                modifier = Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
    }
    val button = @Composable {
        if (action != null) OutlineButton(action.first, action.second, Modifier.heightIn(min = 44.dp), fill = false)
    }
    Surface(
        modifier.fillMaxWidth(), shape = MaterialTheme.shapes.medium, color = c.surface,
        border = androidx.compose.foundation.BorderStroke(1.dp, c.border),
    ) {
        val inner = Modifier.padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3).heightIn(min = 44.dp)
        if (action == null) words(inner.fillMaxWidth())
        else ActionBeside(inner.fillMaxWidth(), stack = largeText(), gap = BrasscribeSpace.s3, words = { words(Modifier) }, action = button)
    }
}

/**
 * The words with the button on the right, or the button under the words when it would leave the words
 * less than 60 % of the row (a long Norwegian label) or at large text.
 */
@Composable
private fun ActionBeside(
    modifier: Modifier, stack: Boolean, gap: androidx.compose.ui.unit.Dp,
    words: @Composable () -> Unit, action: @Composable () -> Unit,
) {
    androidx.compose.ui.layout.Layout(contents = listOf(words, action), modifier = modifier) { (w, b), constraints ->
        val gapPx = gap.roundToPx()
        val max = constraints.maxWidth
        val button = b.first().measure(constraints.copy(minWidth = 0, minHeight = 0))
        val side = !stack && button.width + gapPx <= max * 0.4f
        if (side) {
            val text = w.first().measure(constraints.copy(minWidth = 0, maxWidth = max - button.width - gapPx, minHeight = 0))
            val h = maxOf(text.height, button.height, constraints.minHeight)
            layout(max, h) {
                text.place(0, (h - text.height) / 2)
                button.place(max - button.width, (h - button.height) / 2)
            }
        } else {
            val text = w.first().measure(constraints.copy(minWidth = 0, minHeight = 0))
            val h = maxOf(text.height + gapPx + button.height, constraints.minHeight)
            layout(max, h) {
                text.place(0, 0)
                button.place(0, text.height + gapPx)
            }
        }
    }
}
