package no.brasscribe.play

import androidx.compose.runtime.Composable

/** What makes this build Fretscribe: its name, its pairing link and the screens it opens with. */
object Product {
    const val NAME = "Fretscribe"

    /** The scheme of the pairing link in the computer's QR code: Brasscribe's, until Fretscribe has its own. */
    const val PAIR_SCHEME = "brasscribe"

    /** Brasscribe's screens for now, under Fretscribe's name. */
    @Composable
    fun Root(vm: PlayViewModel) = PlayRoot(vm)
}
