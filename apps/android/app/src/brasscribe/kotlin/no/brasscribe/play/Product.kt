package no.brasscribe.play

import androidx.compose.runtime.Composable

/** What makes this build Brasscribe: its name, its pairing link and the screens it opens with. */
object Product {
    const val NAME = "Brasscribe"

    /** The scheme of the pairing link in the computer's QR code. */
    const val PAIR_SCHEME = "brasscribe"

    /** The band's sounds are in this app, so Settings offers the choice between them. */
    const val BAND_SOUNDS = true

    @Composable
    fun Root(vm: PlayViewModel) = PlayRoot(vm)

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    fun instrumentValue(vm: PlayViewModel): String = no.brasscribe.play.ui.seatValue(vm.container.seat, vm.container.seats)
}
