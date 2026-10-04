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
import no.brasscribe.play.fret.ComputerProfiles
import no.brasscribe.play.fret.PracticeRecordings
import no.brasscribe.play.fret.SongAnswers
import no.brasscribe.play.fret.TabScreen
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

    /** A tab has no music stand, so Settings has none of the stand's switches. */
    const val MUSIC_STAND = false

    /**
     * Home has no Open a tab: a MusicXML file opened from Home would show on Brasscribe's score screen, not in the tab
     * view. It comes back once an imported tab opens there.
     */
    const val OPENS_SCORES = false

    /** The page pedals turn pages on a band score's stand; a tab has its own keys. */
    const val PEDALS_REPEAT = false

    /** A tab's PDF comes from the computer only. */
    const val PHONE_PDF = false

    /**
     * A take whose tab was not made (it failed, or was stopped) is kept in Your songs, as Brasscribe keeps a recording
     * in Your scores: for [KEPT_RECORDING_DAYS] days, then it is deleted if no tab was made from it.
     */
    const val KEEPS_RECORDINGS = true

    /** How long a take without a tab is kept in Your songs. Settings and the words that say it is kept say so too. */
    val KEPT_RECORDING_DAYS: Int? = 30

    /** A tab is written on the computer only: without it, "Not connected" is a warning. */
    const val MAKES_SCORES_ON_THE_PHONE = false

    /**
     * Brasscribe's screens under Fretscribe's name, but for four:
     * - where Brasscribe asks "What do you play?" (after the first run, and from Settings), Fretscribe asks
     *   Your instrument ("Who played this?" on a finished take is still Brasscribe's);
     * - What is this? has Fretscribe's two choices;
     * - a tab's place for Brasscribe's output choices and Check the notes is Check the song;
     * - a tab is shown in the tab view, where Brasscribe shows a score.
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
            (top == Screen.OUTPUT || top == Screen.REVIEW) && result?.profile?.writesTab == true -> ({ CheckTheSongScreen(vm) })
            top == Screen.SCORE && result?.profile?.writesTab == true -> ({ TabScreen(vm) })
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

    /** The computer's scores this app opens: tabs, also a bass tab made before there were other instruments. A band score is Brasscribe's. */
    fun makes(profile: String): Boolean = Profile.writesTab(profile)

    /** Brasscribe's Check the notes and output choices write for a band: never offered here. */
    @Suppress("UNUSED_PARAMETER")
    fun arranges(profile: Profile): Boolean = false

    /**
     * The job as it is sent to the computer: a tab takes the player's instrument and the answers for this song,
     * under the profile id the computer has for it (a computer from before the tab profile still takes a bass).
     */
    fun job(vm: PlayViewModel, request: JobCreate): JobCreate =
        if (!Profile.writesTab(request.profile)) request
        else tabJob(request, tabOptions(yourInstrumentStore(vm.getApplication()).load(), SongAnswers.of(vm.source.value)), ComputerProfiles.listed)

    /**
     * The recording as the computer already holds it, when Check the song has the song written down again:
     * the new job is made on the same upload, so it also works for a song opened from Your songs and when
     * the phone's copy of the recording is gone. Null for a first job: the recording is sent.
     */
    suspend fun audioOnComputer(vm: PlayViewModel, engine: no.brasscribe.play.engine.EngineApi): String? {
        if (vm.profile.value?.writesTab != true || SongAnswers.of(vm.source.value).again == null) return null
        val written = vm.result.value ?: return null
        return written.audioId ?: written.jobId?.let { engine.job(it).audioId }
    }

    /**
     * The song's recording as practice keeps it on the phone, for a song whose recording the computer no longer
     * has: it is sent again. Named by the song, with the kind of file it is (the copy has no name of its own).
     */
    fun keptRecording(vm: PlayViewModel): no.brasscribe.play.engine.UploadSource? {
        // Only for the song on screen written down again: a first send is of the recording opened, never of another song's.
        if (vm.profile.value?.writesTab != true || SongAnswers.of(vm.source.value).again == null) return null
        val job = vm.result.value?.jobId ?: return null
        val file = PracticeRecordings.of(vm.getApplication()).find(job) ?: return null
        val name = (vm.source.value?.name ?: vm.result.value?.composition?.title).orEmpty().substringBeforeLast('.').ifBlank { "recording" }
        return no.brasscribe.play.engine.UploadSource.of(file, "$name.${PracticeRecordings.extensionOf(file)}")
    }

    /** The computer, as the transcribing screen names it: "Fretscribe on Kari's Mac", never its address. */
    fun computerName(vm: PlayViewModel): String =
        if (vm.container.usingFixture) vm.container.engineLabel() else vm.serverDisplayName(vm.container.settings.serverName)

    /**
     * No time left on the transcribing screen: the estimate counts stages, and a tab's stages differ too much
     * in length for it to be right. The step and the percentage are shown.
     */
    const val TIME_LEFT = false

    /**
     * The transcribing screen stays on while the notes are written down, so the player can watch it. The job runs on
     * the computer, so the screen also says the player may switch apps: a finished tab is in Your songs.
     */
    const val KEEP_OPEN_WHILE_WRITING = true

    /** The screen that follows a finished transcription: Check the song for a tab (drawn in the output choices' place). */
    fun afterTranscription(result: TranscriptionResult): Screen =
        if (result.profile.writesTab) Screen.OUTPUT else Screen.REVIEW

    /** The screen after Check the notes: the output choices, for every take. */
    @Suppress("UNUSED_PARAMETER")
    fun afterReview(result: TranscriptionResult): Screen = Screen.OUTPUT

    /** A row in Your songs: a tab's instrument, tuning and notes to check; a band score says where it opens. Null for the usual line. */
    @Composable
    fun rowSubtitle(entry: ScoreEntry): String? = songRowSubtitle(entry)
}
