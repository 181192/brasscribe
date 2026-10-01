package no.brasscribe.play

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import no.brasscribe.play.fret.YourInstrumentScreen
import no.brasscribe.play.fret.yourInstrumentValue

/** What makes this build Fretscribe: its name, its pairing link and the screens it opens with. */
object Product {
    const val NAME = "Fretscribe"

    /** The scheme of the pairing link in the computer's QR code: Brasscribe's, until Fretscribe has its own. */
    const val PAIR_SCHEME = "brasscribe"

    /**
     * Brasscribe's screens for now, under Fretscribe's name, but for one: where Brasscribe asks "What do
     * you play?" (after the first run, and from Settings), Fretscribe asks Your instrument. "Who played
     * this?" on a finished take is still Brasscribe's.
     */
    @Composable
    fun Root(vm: PlayViewModel) {
        val stack by vm.screen.collectAsState()
        if (stack.last() == Screen.WHAT_DO_YOU_PLAY && vm.seatPicker != SeatPickerMode.WHO_PLAYED) {
            BackHandler(enabled = stack.size > 1) { vm.back() }
            YourInstrumentScreen(vm)
        } else PlayRoot(vm)
    }

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    fun instrumentValue(vm: PlayViewModel): String = yourInstrumentValue()
}
