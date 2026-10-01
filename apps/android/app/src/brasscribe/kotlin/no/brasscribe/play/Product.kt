package no.brasscribe.play

import androidx.compose.runtime.Composable

/** What makes this build Brasscribe: its name, its pairing link and the screens it opens with. */
object Product {
    const val NAME = "Brasscribe"

    /** The scheme of the pairing link in the computer's QR code. */
    const val PAIR_SCHEME = "brasscribe"

    @Composable
    fun Root(vm: PlayViewModel) = PlayRoot(vm)
}
