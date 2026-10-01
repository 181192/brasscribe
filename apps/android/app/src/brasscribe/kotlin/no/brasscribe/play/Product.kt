package no.brasscribe.play

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.Profile

/** What makes this build Brasscribe: its name, its pairing link, the screens it opens with and the scores it makes. */
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

    /** The computer's scores this app opens: every band score. A bass tab is Fretscribe's. */
    fun makes(profile: String): Boolean = profile != Profile.BASS_TAB.id

    /** Check the notes and the output choices are offered for this profile's scores. */
    fun arranges(profile: Profile): Boolean = makes(profile.id)

    /** The job as it is sent to the computer: the band profiles take nothing more. */
    @Suppress("UNUSED_PARAMETER")
    fun job(vm: PlayViewModel, request: JobCreate): JobCreate = request

    /** The recording as the computer already holds it, for a job that needs no upload: Brasscribe always sends it. */
    @Suppress("UNUSED_PARAMETER", "RedundantSuspendModifier")
    suspend fun audioOnComputer(vm: PlayViewModel, engine: no.brasscribe.play.engine.EngineApi): String? = null

    /** The computer, as the transcribing screen names it. */
    fun computerName(vm: PlayViewModel): String = vm.container.engineLabel()

    /** The transcribing screen shows the time left. */
    const val TIME_LEFT = true

    /** The transcribing screen says the app may be left, so it does not hold the screen on. */
    const val KEEP_OPEN_WHILE_WRITING = false

    /** The screen that follows a finished transcription. */
    @Suppress("UNUSED_PARAMETER")
    fun afterTranscription(result: TranscriptionResult): Screen = Screen.REVIEW

    /** A row in Your scores that is not a band score: a bass tab says where it opens. Null for the usual line. */
    @Composable
    fun rowSubtitle(entry: ScoreEntry): String? =
        if (entry.onComputer && !makes(entry.profile)) stringResource(R.string.other_product_row) else null
}
