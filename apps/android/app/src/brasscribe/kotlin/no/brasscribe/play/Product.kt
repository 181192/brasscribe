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

    /** A score opens on the music stand, so Settings has the stand's switches. */
    const val MUSIC_STAND = true

    /** A recording whose score was not made (it failed, was put off or was stopped) is kept in Your scores. */
    const val KEEPS_RECORDINGS = true

    @Composable
    fun Root(vm: PlayViewModel) = PlayRoot(vm)

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    fun instrumentValue(vm: PlayViewModel): String = no.brasscribe.play.ui.seatValue(vm.container.seat, vm.container.seats)

    /** The computer's scores this app opens: every band score. A tab is Fretscribe's. */
    fun makes(profile: String): Boolean = !Profile.writesTab(profile)

    /** Check the notes and the output choices are offered for this profile's scores. */
    fun arranges(profile: Profile): Boolean = makes(profile.id)

    /** The job as it is sent to the computer: the band profiles take nothing more. */
    @Suppress("UNUSED_PARAMETER")
    fun job(vm: PlayViewModel, request: JobCreate): JobCreate = request

    /** The recording as the computer already holds it, for a job that needs no upload: Brasscribe always sends it. */
    @Suppress("UNUSED_PARAMETER", "RedundantSuspendModifier")
    suspend fun audioOnComputer(vm: PlayViewModel, engine: no.brasscribe.play.engine.EngineApi): String? = null

    /**
     * A copy of the recording kept apart from the one opened: Brasscribe has none. A recording kept in Your scores is
     * the one opened itself (`Source.file`), so it is sent as it is.
     */
    @Suppress("UNUSED_PARAMETER")
    fun keptRecording(vm: PlayViewModel): no.brasscribe.play.engine.UploadSource? = null

    /** The computer, as the transcribing screen names it. */
    fun computerName(vm: PlayViewModel): String = vm.container.engineLabel()

    /** The transcribing screen shows the time left (for a score made on the phone). */
    const val TIME_LEFT = true

    /**
     * Nothing tells the player when a score is ready while the app is away, so the transcribing screen says to keep
     * it open, and stays on. A band draft on the phone is the exception: its service keeps it going.
     */
    const val KEEP_OPEN_WHILE_WRITING = true

    /**
     * The screen that follows a finished transcription: Check the notes, or the score for a draft made on the phone.
     * A draft has only Basic Pitch on the melody, so every melody note is marked "?", and its notice already says it
     * is rough; Check the notes is still reachable from the score (design/system.md, the band draft).
     */
    fun afterTranscription(result: TranscriptionResult): Screen = if (result.draft) Screen.SCORE else Screen.REVIEW

    /** A row in Your scores that is not a band score: a tab says where it opens. Null for the usual line. */
    @Composable
    fun rowSubtitle(entry: ScoreEntry): String? =
        if (entry.onComputer && !makes(entry.profile)) stringResource(R.string.other_product_row) else null
}
