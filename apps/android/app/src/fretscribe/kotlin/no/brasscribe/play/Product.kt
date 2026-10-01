package no.brasscribe.play

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.fret.CheckTheSongScreen
import no.brasscribe.play.fret.SongAnswers
import no.brasscribe.play.fret.WhatIsThisScreen
import no.brasscribe.play.fret.YourInstrumentScreen
import no.brasscribe.play.fret.songRowSubtitle
import no.brasscribe.play.fret.tabJob
import no.brasscribe.play.fret.tabOptions
import no.brasscribe.play.fret.yourInstrumentStore
import no.brasscribe.play.fret.yourInstrumentValue

/** What makes this build Fretscribe: its name, its pairing link, the screens it opens with and the tabs it makes. */
object Product {
    const val NAME = "Fretscribe"

    /** The scheme of the pairing link in the computer's QR code: Brasscribe's, until Fretscribe has its own. */
    const val PAIR_SCHEME = "brasscribe"

    /** Fretscribe carries no band sounds, so Settings has no choice between them. */
    const val BAND_SOUNDS = false

    /**
     * Brasscribe's screens under Fretscribe's name, but for three:
     * - where Brasscribe asks "What do you play?" (after the first run, and from Settings), Fretscribe asks
     *   Your instrument ("Who played this?" on a finished take is still Brasscribe's);
     * - What is this? has Fretscribe's two choices;
     * - a bass tab's place for Brasscribe's output choices and Check the notes is Check the song.
     */
    @Composable
    fun Root(vm: PlayViewModel) {
        val stack by vm.screen.collectAsState()
        val result by vm.result.collectAsState()
        // Counts the visits to Your instrument, so each one starts from what is stored: choices left
        // without Save are gone the next time, also after the app was stopped and restored in between.
        var visit by rememberSaveable { mutableIntStateOf(0) }
        val top = stack.last()
        val asking = top == Screen.WHAT_DO_YOU_PLAY && vm.seatPicker != SeatPickerMode.WHO_PLAYED
        LaunchedEffect(asking) { if (!asking) visit++ }
        val own: (@Composable () -> Unit)? = when {
            asking -> ({ YourInstrumentScreen(vm, visit) })
            top == Screen.PROFILE -> ({ WhatIsThisScreen(vm) })
            (top == Screen.OUTPUT || top == Screen.REVIEW) && result?.profile == Profile.BASS_TAB -> ({ CheckTheSongScreen(vm) })
            else -> null
        }
        if (own != null) {
            BackHandler(enabled = stack.size > 1) { vm.back() }
            own()
        } else PlayRoot(vm)
    }

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    fun instrumentValue(vm: PlayViewModel): String = yourInstrumentValue()

    /** The computer's scores this app opens: bass tabs. A band score is Brasscribe's. */
    fun makes(profile: String): Boolean = profile == Profile.BASS_TAB.id

    /** Brasscribe's Check the notes and output choices write for a band: never offered here. */
    @Suppress("UNUSED_PARAMETER")
    fun arranges(profile: Profile): Boolean = false

    /** The job as it is sent to the computer: a bass tab takes the player's instrument and the answers for this song. */
    fun job(vm: PlayViewModel, request: JobCreate): JobCreate =
        if (request.profile != Profile.BASS_TAB.id) request
        else tabJob(request, tabOptions(yourInstrumentStore(vm.getApplication()).load(), SongAnswers.of(vm.source.value)))

    /** The screen that follows a finished transcription: Check the song for a tab (drawn in the output choices' place). */
    fun afterTranscription(result: TranscriptionResult): Screen =
        if (result.profile == Profile.BASS_TAB) Screen.OUTPUT else Screen.REVIEW

    /** A row in Your songs: a tab's instrument, tuning and notes to check; a band score says where it opens. Null for the usual line. */
    @Composable
    fun rowSubtitle(entry: ScoreEntry): String? = songRowSubtitle(entry)
}
