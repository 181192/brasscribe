package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import no.kalli.scribe.play.Product
import no.kalli.scribe.play.WindowColors

import no.kalli.scribe.play.OnPhone
import no.kalli.scribe.play.ui.AboutScreen
import no.kalli.scribe.play.ui.CompanionScreen
import no.kalli.scribe.play.ui.ExportScreen
import no.kalli.scribe.play.ui.FirstRunScreen
import no.kalli.scribe.play.ui.HelpScreen
import no.kalli.scribe.play.ui.HomeScreen
import no.kalli.scribe.play.ui.ProblemScreen
import no.kalli.scribe.play.ui.RecordScreen
import no.kalli.scribe.play.ui.SettingsScreen
import no.kalli.scribe.play.ui.TranscribeScreen
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.ScoreEntry
import no.kalli.scribe.play.Screen
import no.kalli.scribe.play.SeatPickerMode
import no.kalli.scribe.play.Source
import no.kalli.scribe.play.TranscriptionResult

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.text.font.FontFamily
import no.kalli.fretscribe.design.FretscribeTab
import no.kalli.fretscribe.design.FretscribeTheme
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.engine.JobCreate
import no.kalli.scribe.engine.Profile
import no.kalli.scribe.engine.Target
import no.kalli.fretscribe.CheckTheSongScreen
import no.kalli.fretscribe.ComputerProfiles
import no.kalli.scribe.tab.PracticeRecordings
import no.kalli.fretscribe.SongAnswers
import no.kalli.fretscribe.TabScreen
import no.kalli.fretscribe.WhatIsThisScreen
import no.kalli.fretscribe.YourInstrumentScreen
import no.kalli.fretscribe.songRowSubtitle
import no.kalli.fretscribe.tabJob
import no.kalli.fretscribe.tabOptions
import no.kalli.fretscribe.yourInstrumentStore
import no.kalli.fretscribe.yourInstrumentValue
import no.kalli.scribe.play.ui.theme.LocalProductColors
import no.kalli.scribe.play.ui.theme.ProductColors

/** What makes this build Fretscribe: its name, the screens it opens with and the tabs it makes. */
object Fretscribe : Product {
    override val name = "Fretscribe"

    /**
     * Home has no Open a tab: a MusicXML file opened from Home would show on Brasscribe's score screen, not in the tab
     * view. It comes back once an imported tab opens there.
     */
    override val opensScores = false

    /** A tab's PDF comes from the computer only. */
    override val phonePdf = false

    /**
     * A take whose tab was not made (it failed, or was stopped) is kept in Your songs, as Brasscribe keeps a recording
     * in Your scores: for [keptRecordingDays] days, then it is deleted if no tab was made from it.
     */
    override val keepsRecordings = true

    /** How long a take without a tab is kept in Your songs. Settings and the words that say it is kept say so too. */
    override val keptRecordingDays: Int? = 30

    /** A take kept in Your songs is the same recording in another place: What is this?'s answers go with it. */
    override fun recordingMoved(from: Source, to: Source) = SongAnswers.moved(from, to)

    /** A tab is written on the computer only: without it, "Not connected" is a warning. */
    override val makesScoresOnThePhone = false

    /** So the app carries no models, and no ONNX Runtime to run them. */
    @Suppress("UNUSED_PARAMETER")
    override fun onPhone(context: android.content.Context, core: no.kalli.scribe.model.CoreBridge): OnPhone = OnPhone.None

    /**
     * Fretscribe's theme. It has no Pink palette. The screens it has from Brasscribe draw a score with colours a tab
     * has no name for: there the one doubt colour stands in for the very doubtful one, and the repeat's band for the
     * band behind freely played bars.
     */
    @Composable
    override fun Theme(dark: Boolean, @Suppress("UNUSED_PARAMETER") pink: Boolean, display: FontFamily, content: @Composable () -> Unit) {
        FretscribeTheme(dark = dark, display = display) {
            val own = FretscribeTheme.colors
            val doubt = ScribeTheme.colors.uncertain
            val colors = ProductColors(
                veryUncertain = doubt, adlibTint = own.loopTint, loopTint = own.loopTint, cursor = own.cursor,
                selectionTint = own.selectionTint, selectionEdge = own.selectionEdge,
                focusWidth = FretscribeTab.focusWidth,
            )
            CompositionLocalProvider(LocalProductColors provides colors, content = content)
        }
    }

    /**
     * Fretscribe's navigation. It shares Home, recording, writing down, sharing, pairing, Settings, Help and the
     * problems with Brasscribe; its own are Your instrument (where Brasscribe asks "What do you play?"), What is
     * this? with its two choices, Check the song (in the place of Check the notes and the output choices) and the
     * tab view.
     */
    @Composable
    override fun Root(vm: PlayViewModel) {
        val stack by vm.screen.collectAsState()
        // Counts the visits to Your instrument, so each one starts from what is stored: choices left
        // without Save are gone the next time, also after the app was stopped and restored in between.
        var visit by rememberSaveable { mutableIntStateOf(0) }
        val top = stack.last()
        LaunchedEffect(top == Screen.WHAT_DO_YOU_PLAY) { if (top != Screen.WHAT_DO_YOU_PLAY) visit++ }
        BackHandler(enabled = stack.size > 1) { vm.back() }
        when (top) {
            Screen.FIRST_RUN -> FirstRunScreen(vm)
            Screen.WHAT_DO_YOU_PLAY -> YourInstrumentScreen(vm, visit)
            Screen.HOME -> HomeScreen(vm)
            Screen.RECORD -> RecordScreen(vm)
            Screen.PROFILE -> WhatIsThisScreen(vm)
            Screen.TRANSCRIBE -> TranscribeScreen(vm)
            Screen.REVIEW, Screen.OUTPUT -> CheckTheSongScreen(vm)
            Screen.SCORE -> TabScreen(vm)
            Screen.EXPORT -> ExportScreen(vm)
            Screen.COMPANION -> CompanionScreen(vm)
            Screen.ABOUT -> AboutScreen(vm)
            Screen.SETTINGS -> SettingsScreen(vm)
            Screen.HELP -> HelpScreen(vm)
            Screen.PROBLEM -> ProblemScreen(vm)
        }
    }

    /** Settings: what the "What you play" row shows as its value. */
    @Composable
    override fun instrumentValue(vm: PlayViewModel): String = yourInstrumentValue()

    /** What this app is for: of the engine's profiles, the ones of this target are its own. */
    override val windowColors = WindowColors(
        R.color.window_light, R.color.window_dark, R.color.window_pink, R.color.window_pink_dark,
        R.color.window_contrast_light, R.color.window_contrast_dark,
    )

    override val target = Target.FRETTED

    /**
     * Whether a job on the computer is this app's: the engine says which target each job belongs to
     * ([no.kalli.scribe.engine.Job.target]). A job of another target, or of none, is not.
     */
    override fun makes(target: String?): Boolean = target == this.target.id

    /** Brasscribe's Check the notes and output choices write for a band: never offered here. */
    @Suppress("UNUSED_PARAMETER")
    override fun arranges(profile: Profile): Boolean = false

    /**
     * The job as it is sent to the computer: a tab takes the player's instrument and the answers for this song,
     * under the profile id the computer has for it (a computer from before the tab profile still takes a bass).
     */
    override fun job(vm: PlayViewModel, request: JobCreate): JobCreate =
        if (!Profile.writesTab(request.profile)) request
        else tabJob(request, tabOptions(yourInstrumentStore(vm.getApplication()).load(), SongAnswers.of(vm.source.value)), ComputerProfiles.listed)

    /**
     * The recording as the computer already holds it, when Check the song has the song written down again:
     * the new job is made on the same upload, so it also works for a song opened from Your songs and when
     * the phone's copy of the recording is gone. Null for a first job: the recording is sent.
     */
    override suspend fun audioOnComputer(vm: PlayViewModel, engine: no.kalli.scribe.engine.EngineApi): String? {
        if (vm.profile.value?.writesTab != true || SongAnswers.of(vm.source.value).again == null) return null
        val written = vm.result.value ?: return null
        return written.audioId ?: written.jobId?.let { engine.job(it).audioId }
    }

    /**
     * The song's recording as practice keeps it on the phone, for a song whose recording the computer no longer
     * has: it is sent again. Named by the song, with the kind of file it is (the copy has no name of its own).
     */
    override fun keptRecording(vm: PlayViewModel): no.kalli.scribe.engine.UploadSource? {
        // Only for the song on screen written down again: a first send is of the recording opened, never of another song's.
        if (vm.profile.value?.writesTab != true || SongAnswers.of(vm.source.value).again == null) return null
        val job = vm.result.value?.jobId ?: return null
        val file = PracticeRecordings.of(vm.getApplication()).find(job) ?: return null
        val name = (vm.source.value?.name ?: vm.result.value?.composition?.title).orEmpty().substringBeforeLast('.').ifBlank { "recording" }
        return no.kalli.scribe.engine.UploadSource.of(file, "$name.${PracticeRecordings.extensionOf(file)}")
    }

    /** The computer, as the transcribing screen names it: "Bandroom on Kari's Mac", never its address. */
    override fun computerName(vm: PlayViewModel): String =
        if (vm.container.usingFixture) vm.container.engineLabel() else vm.serverDisplayName(vm.container.settings.serverName)

    /**
     * No time left on the transcribing screen: the estimate counts stages, and a tab's stages differ too much
     * in length for it to be right. The step and the percentage are shown.
     */
    override val timeLeft = false

    /**
     * The transcribing screen stays on while the notes are written down, so the player can watch it. The job runs on
     * the computer and is followed while the player is away (`ComputerJobService`), so the screen also says the player
     * may switch apps: the app says when the tab is ready, and a finished tab is in Your songs.
     */
    override val keepOpenWhileWriting = true

    /** The screen that follows a finished transcription: Check the song for a tab (drawn in the output choices' place). */
    override fun afterTranscription(result: TranscriptionResult): Screen =
        if (result.profile.writesTab) Screen.OUTPUT else Screen.REVIEW

    /** The screen after Check the notes: the output choices, for every take. */
    @Suppress("UNUSED_PARAMETER")
    override fun afterReview(result: TranscriptionResult): Screen = Screen.OUTPUT

    /** A row in Your songs: a tab's instrument, tuning and notes to check; a band score says where it opens. Null for the usual line. */
    @Composable
    override fun rowSubtitle(entry: ScoreEntry): String? = songRowSubtitle(entry)
}
