package no.brasscribe.play

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import no.brasscribe.play.fret.YourInstrumentScreen
import no.brasscribe.play.fret.yourInstrumentValue

/** What makes this build Fretscribe: its name, its pairing link and the screens it opens with. */
object Product {
    const val NAME = "Fretscribe"

    /** The scheme of the pairing link in the computer's QR code: Brasscribe's, until Fretscribe has its own. */
    const val PAIR_SCHEME = "brasscribe"

    /** Fretscribe carries no band sounds, so Settings has no choice between them. */
    const val BAND_SOUNDS = false

    /**
     * Brasscribe's screens for now, under Fretscribe's name, but for one: where Brasscribe asks "What do
     * you play?" (after the first run, and from Settings), Fretscribe asks Your instrument. "Who played
     * this?" on a finished take is still Brasscribe's.
     */
    @Composable
    fun Root(vm: PlayViewModel) {
        val stack by vm.screen.collectAsState()
        // Counts the visits to Your instrument, so each one starts from what is stored: choices left
        // without Save are gone the next time, also after the app was stopped and restored in between.
        var visit by rememberSaveable { mutableIntStateOf(0) }
        val asking = stack.last() == Screen.WHAT_DO_YOU_PLAY && vm.seatPicker != SeatPickerMode.WHO_PLAYED
        LaunchedEffect(asking) { if (!asking) visit++ }
        if (asking) {
            BackHandler(enabled = stack.size > 1) { vm.back() }
            YourInstrumentScreen(vm, visit)
        } else PlayRoot(vm)
    }

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    fun instrumentValue(vm: PlayViewModel): String = yourInstrumentValue()
}
