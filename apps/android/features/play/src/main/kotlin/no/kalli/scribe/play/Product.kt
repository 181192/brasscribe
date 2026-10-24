package no.kalli.scribe.play

import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.FontFamily
import no.kalli.scribe.engine.EngineApi
import no.kalli.scribe.engine.JobCreate
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.engine.Target
import no.kalli.scribe.engine.UploadSource
import no.kalli.scribe.model.CoreBridge

/**
 * What an app built on the shared flow is: its name, its screens and what it makes. Each product module has one
 * and hands it in through its [PlayApplication]; the shared code asks it and never names a product.
 */
interface Product {
    /** The app's name, as the screens say it. */
    val name: String

    /** What this app is for: of the engine's profiles, the ones of this target are its own. */
    val target: Target

    /**
     * Whether a job on the computer is this app's: the engine says which target each job belongs to
     * ([no.kalli.scribe.engine.Job.target]). A job of another target, or of none, is not.
     */
    fun makes(target: String?): Boolean = target == this.target.id

    /** Check the notes and the output choices are offered for this profile's results. */
    fun arranges(profile: Profile): Boolean

    /** Home offers Open a score: a MusicXML file from elsewhere opens on the score. */
    val opensScores: Boolean

    /** Without a PDF from the computer (a result made or changed on the phone), the phone lays out the PDF itself. */
    val phonePdf: Boolean

    /** A recording whose result was not made (it failed, was put off or was stopped) is kept in the library. */
    val keepsRecordings: Boolean

    /** How long a kept recording stays before it is deleted; null keeps it until the player deletes it. */
    val keptRecordingDays: Int?

    /** A kept recording moved to the library: what the product keeps about it goes with it. */
    fun recordingMoved(from: Source, to: Source) = Unit

    /** A result can be made on the phone: without the computer, "Not connected" is information, not a warning. */
    val makesScoresOnThePhone: Boolean

    /** What writes down the notes on the phone. */
    fun onPhone(context: android.content.Context, core: CoreBridge): OnPhone

    /** The transcribing screen shows the time left (for a result made on the phone). */
    val timeLeft: Boolean

    /** The transcribing screen stays on while the notes are written down. */
    val keepOpenWhileWriting: Boolean

    /** The screen that follows a finished transcription. */
    fun afterTranscription(result: TranscriptionResult): Screen

    /** The screen after Check the notes. */
    fun afterReview(result: TranscriptionResult): Screen

    /** The job as it is sent to the computer. */
    fun job(vm: PlayViewModel, request: JobCreate): JobCreate = request

    /** The recording as the computer already holds it, for a job that needs no upload; null sends it. */
    suspend fun audioOnComputer(vm: PlayViewModel, engine: EngineApi): String? = null

    /** A copy of the recording kept apart from the one opened, sent when the opened one is gone. */
    fun keptRecording(vm: PlayViewModel): UploadSource? = null

    /** The computer, as the transcribing screen names it. */
    fun computerName(vm: PlayViewModel): String

    /** The window behind Compose, in each palette: the product's token bg (its res/values/themes.xml). */
    val windowColors: WindowColors

    /** The app: its navigation and its screens. */
    @Composable
    fun Root(vm: PlayViewModel)

    /** The app's theme around [content], with its own colours for the screens it shares. */
    @Composable
    fun Theme(dark: Boolean, pink: Boolean, display: FontFamily, content: @Composable () -> Unit)

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    fun instrumentValue(vm: PlayViewModel): String

    /** A row in the library: its own second line, or null for the usual one. */
    @Composable
    fun rowSubtitle(entry: ScoreEntry): String?
}

/** A product's window colours (colour resources), one for each palette the app draws in. */
data class WindowColors(
    val light: Int, val dark: Int, val pink: Int, val pinkDark: Int, val contrastLight: Int, val contrastDark: Int,
) {
    /** The colour of the palette the app draws in. The phone's high contrast wins over Pink, as it does in the theme. */
    fun pick(dark: Boolean, pink: Boolean, highContrast: Boolean): Int = when {
        highContrast && dark -> contrastDark
        highContrast -> contrastLight
        pink && dark -> pinkDark
        pink -> this.pink
        dark -> this.dark
        else -> light
    }
}
