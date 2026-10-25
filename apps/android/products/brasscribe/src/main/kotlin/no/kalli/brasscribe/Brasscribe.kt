package no.kalli.brasscribe

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import no.kalli.scribe.play.Product
import no.kalli.scribe.play.WindowColors

import no.kalli.scribe.play.OnPhone
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.ScoreEntry
import no.kalli.scribe.play.Screen
import no.kalli.scribe.play.Source
import no.kalli.scribe.play.TranscriptionResult

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import no.kalli.brasscribe.design.BrasscribeScore
import no.kalli.brasscribe.design.BrasscribeTheme
import no.kalli.scribe.engine.JobCreate
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.engine.Target
import no.kalli.scribe.play.ui.theme.LocalProductColors
import no.kalli.scribe.play.ui.theme.ProductColors

/** What makes this build Brasscribe: its name, the screens it opens with and the scores it makes. */
object Brasscribe : Product {
    override val name = "Brasscribe"

    /** Home offers Open a score: a MusicXML file from elsewhere opens on the score. */
    override val opensScores = true

    /** Without a PDF from the computer (a score made or changed on the phone), the phone lays out the PDF itself. */
    override val phonePdf = true

    /** A recording whose score was not made (it failed, was put off or was stopped) is kept in Your scores. */
    override val keepsRecordings = true

    /** A recording kept in Your scores stays until the player deletes it. */
    override val keptRecordingDays: Int? = null

    /** A recording kept in Your scores moved there: nothing here is tied to where it was. */
    @Suppress("UNUSED_PARAMETER")
    override fun recordingMoved(from: Source, to: Source) = Unit

    /** A score can be made on the phone: without the computer, "Not connected" is information, not a warning. */
    override val makesScoresOnThePhone = true

    /** A solo and a band draft are written down on the phone, with the models this app carries. */
    override fun onPhone(context: android.content.Context, core: no.kalli.scribe.model.CoreBridge): OnPhone = OnPhoneModels(context, core)

    @Composable
    override fun Root(vm: PlayViewModel) = BrasscribeRoot(vm)

    /** Brasscribe's theme, with its own colours for the screens both apps are built with. */
    @Composable
    override fun Theme(dark: Boolean, pink: Boolean, display: FontFamily, content: @Composable () -> Unit) {
        BrasscribeTheme(dark = dark, pink = pink, display = display) {
            val own = BrasscribeTheme.colors
            val colors = ProductColors(
                veryUncertain = own.veryUncertain, adlibTint = own.adlibTint, loopTint = own.loopTint, cursor = own.cursor,
                selectionTint = own.selectionTint, selectionEdge = own.selectionEdge,
                focusWidth = BrasscribeScore.focusWidth,
            )
            CompositionLocalProvider(LocalProductColors provides colors, content = content)
        }
    }

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    override fun instrumentValue(vm: PlayViewModel): String = no.kalli.brasscribe.ui.seatValue(vm.container.seat, vm.container.seats)

    /** What this app is for: of the engine's profiles, the ones of this target are its own. */
    override val windowColors = WindowColors(
        R.color.window_light, R.color.window_dark, R.color.window_pink, R.color.window_pink_dark,
        R.color.window_contrast_light, R.color.window_contrast_dark,
    )

    override val target = Target.BRASS

    /**
     * Whether a job on the computer is this app's: the engine says which target each job belongs to
     * ([no.kalli.scribe.engine.Job.target]). A job of another target, or of none, is not.
     */
    override fun makes(target: String?): Boolean = target == this.target.id

    /** Check the notes and the output choices are offered for this profile's scores. */
    override fun arranges(profile: Profile): Boolean = profile.target == target

    /** The job as it is sent to the computer: the band profiles take nothing more. */
    @Suppress("UNUSED_PARAMETER")
    override fun job(vm: PlayViewModel, request: JobCreate): JobCreate = request

    /** The recording as the computer already holds it, for a job that needs no upload: Brasscribe always sends it. */
    @Suppress("UNUSED_PARAMETER", "RedundantSuspendModifier")
    override suspend fun audioOnComputer(vm: PlayViewModel, engine: no.kalli.scribe.engine.EngineApi): String? = null

    /**
     * A copy of the recording kept apart from the one opened: Brasscribe has none. A recording kept in Your scores is
     * the one opened itself (`Source.file`), so it is sent as it is.
     */
    @Suppress("UNUSED_PARAMETER")
    override fun keptRecording(vm: PlayViewModel): no.kalli.scribe.engine.UploadSource? = null

    /** The computer, as the transcribing screen names it. */
    override fun computerName(vm: PlayViewModel): String = vm.container.engineLabel()

    /** The transcribing screen shows the time left (for a score made on the phone). */
    override val timeLeft = true

    /**
     * The transcribing screen stays on while a score is made. A solo made on the phone has nothing to keep it going
     * while the app is away, so the screen says to keep the app open. A band draft goes on in its service, and a job on
     * the computer is followed by `ComputerJobService`, which says when it is ready: then the player may leave.
     */
    override val keepOpenWhileWriting = true

    /**
     * The screen that follows a finished transcription: Check the notes, or the score for a draft made on the phone.
     * A draft has only Basic Pitch on the melody, so every melody note is marked "?", and its notice already says it
     * is rough; Check the notes is still reachable from the score (design/brands/brasscribe/system.md, the band draft).
     */
    override fun afterTranscription(result: TranscriptionResult): Screen = if (result.draft) Screen.SCORE else Screen.REVIEW

    /**
     * The screen after Check the notes: a solo ("One instrument") goes straight to the score, on the player's part; band,
     * difficulty and key are "Band, difficulty and key…" in the score's ⋯ sheet. Every other take asks How should the
     * score be? first.
     */
    override fun afterReview(result: TranscriptionResult): Screen = if (result.isSoloTake) Screen.SCORE else Screen.OUTPUT

    /** A row in Your scores that is not a band score: a tab says where it opens. Null for the usual line. */
    @Composable
    override fun rowSubtitle(entry: ScoreEntry): String? =
        if (entry.onComputer && !makes(entry.target)) stringResource(R.string.other_product_row) else null
}
