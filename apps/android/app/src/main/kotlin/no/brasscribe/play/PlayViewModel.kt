package no.brasscribe.play

import android.app.Application
import android.net.Uri
import android.provider.OpenableColumns
import androidx.annotation.StringRes
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.brasscribe.play.audio.AudioDecoder
import no.brasscribe.play.audio.MediaImport
import no.brasscribe.play.audio.CapturedTake
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.audio.UnsupportedMediaException
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.JobStatus
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.engine.ProgressTracker
import no.brasscribe.play.engine.UploadSource
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.Instrument
import no.brasscribe.play.model.MusicXmlTitleEditor
import no.brasscribe.play.model.PartSpec
import no.brasscribe.play.model.TickMap
import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.TempoEstimator
import no.brasscribe.play.model.VoiceRole
import no.brasscribe.play.playback.BarListening
import no.brasscribe.play.playback.ClipPlayer
import no.brasscribe.play.connection.ConnectionMonitor
import no.brasscribe.play.connection.Credential
import no.brasscribe.play.connection.CredentialStore
import no.brasscribe.play.connection.EngineConnection
import no.brasscribe.play.connection.mayBeSentTo
import no.brasscribe.play.connection.ServerNames
import no.brasscribe.play.capture.CaptureController
import no.brasscribe.play.engine.EngineException
import no.brasscribe.play.engine.KtorEngineApi
import no.brasscribe.play.engine.PairLink
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.map
import java.io.File
import java.util.zip.ZipInputStream

enum class Screen { FIRST_RUN, WHAT_DO_YOU_PLAY, HOME, RECORD, PROFILE, TRANSCRIBE, REVIEW, OUTPUT, SCORE, EXPORT, COMPANION, ABOUT, SETTINGS, PROBLEM, HELP }

/** Something went wrong that the user has to act on: shown full screen with a way forward. */
enum class Problem { FILE_UNREADABLE, NO_SOUND_TRACK, NOTHING_HEARD, RECORDING_FAILED, SCORE_FAILED, TOO_LARGE, DRAFT_TOO_LONG, DRAFT_REFUSED, NO_NOTES }

/** [r] is to be checked note by note, and holds no note to check: it opens on the problem screen instead. */
fun foundNoNotes(r: TranscriptionResult, then: Screen): Boolean =
    then == Screen.REVIEW && r.composition?.voices?.all { it.notes.isEmpty() } == true

/**
 * No notes were found: the computer is the way forward only when the phone wrote it down and the computer is there.
 * The computer hears more than the phone; when it made the result itself, it has nothing more to give.
 */
fun noNotesOffersComputer(madeOnPhone: Boolean, computerThere: Boolean): Boolean = madeOnPhone && computerThere

/** The way to record from the no-notes screen: again after a take with the microphone, else for the first time. */
@StringRes
fun noNotesRecordWords(kind: SourceKind?): Int = if (kind == SourceKind.MICROPHONE) R.string.problem_record_again else R.string.home_record_mic

enum class SourceKind { FILE, VIDEO, MICROPHONE, DEVICE, SCORE }

/**
 * What the user brought in. [file] holds the bytes sent to the engine (for a video, only its sound);
 * [audio] is decoded mono PCM, null when it is too long to hold in memory (the engine can still take it).
 */
data class Source(
    val name: String,
    val kind: SourceKind,
    val durationS: Double,
    val audio: PcmAudio? = null,
    val file: File? = null,
)

enum class Where { DEVICE, COMPANION }

/** Plain-language steps; each maps to one string resource. */
enum class Step(@StringRes val text: Int) {
    QUEUED(R.string.stage_queued), UPLOAD(R.string.stage_upload), BEATS(R.string.stage_beats), STEMS(R.string.stage_stems),
    LAYERS(R.string.stage_layers), TRANSCRIBE(R.string.stage_transcribe), ARRANGE(R.string.stage_arrange),
    EXPORT(R.string.stage_export), DECODE(R.string.stage_decode), PITCH(R.string.stage_pitch), QUANTIZE(R.string.stage_quantize),
    CONFIRM(R.string.stage_confirm);

    companion object {
        fun ofKind(kind: String?): Step = when (kind) {
            "beats" -> BEATS; "stems" -> STEMS; "layers" -> LAYERS; "transcribe" -> TRANSCRIBE
            "arrange" -> ARRANGE; "export" -> EXPORT
            // A bass tab's own stage: the two transcribers' notes joined and put on the beat grid.
            "notes" -> QUANTIZE
            else -> QUEUED
        }
    }
}

data class TranscribeState(
    val running: Boolean = false,
    val step: Step = Step.QUEUED,
    val fraction: Double = 0.0,
    val stepIndex: Int = 0,
    val stepTotal: Int = 0,
    val etaSeconds: Int? = null,
    val where: String = "",
    val error: String? = null,
    /** Every step of this run in order, for the step list. */
    val steps: List<Step> = emptyList(),
    /** A band draft on the phone: its service keeps it going while the player is out of the app. */
    val draft: Boolean = false,
)

/** A finished transcription. [musicXml] is what the score view renders; [jobId] is set for engine results. */
data class TranscriptionResult(
    /** Null for a score that was opened, not transcribed: there is no recording behind it. */
    val composition: Composition?,
    val musicXml: String,
    val profile: Profile,
    val onDevice: Boolean,
    val jobId: String? = null,
    val engineOutputs: Set<String> = emptySet(),
    /** The uploaded audio on the engine, for re-arranging with other options. */
    val audioId: String? = null,
    /** The Composition as the core wrote it (humanization reads it). */
    val compositionJson: String? = null,
    /** Semitones the arrangement itself is transposed by (the rest of a key shift is display-only in alphaTab). */
    val appliedTranspose: Int = 0,
    /** Confidence and what each transcriber heard at the uncertain notes. */
    val evidence: no.brasscribe.play.engine.Evidence? = null,
    /** A note was changed on the phone: the engine's PDF, braille and audio still show the old one. */
    val changedOnPhone: Boolean = false,
    /** A quick band draft made on the phone: the computer can make the full score from its recording. */
    val draft: Boolean = false,
)

/** What the core wants beside the MusicXML: null is fine, and is all an opened score can give. */
fun TranscriptionResult.compositionJsonFor(core: no.brasscribe.play.model.CoreBridge): String? =
    compositionJson ?: composition?.let { runCatching { core.encodeComposition(it) }.getOrNull() }


enum class Difficulty(@StringRes val label: Int) {
    FAITHFUL(R.string.difficulty_faithful), STANDARD(R.string.difficulty_standard), EASIER(R.string.difficulty_easier);

    /** The name the core and the engine use. */
    val id: String get() = name.lowercase()

    companion object {
        fun of(name: String?): Difficulty? = entries.firstOrNull { it.id == name?.trim()?.lowercase() }
    }
}

/**
 * The Output screen's answers. [seat] and [reads] are who played a solo take (or whose part a band take
 * names), pre-filled from Settings; [lead] "seat" puts the tune on the seat's part (Who plays the tune?).
 */
data class OutputOptions(
    val lineup: Lineup = Lineup.FULL, val difficulty: Difficulty = Difficulty.FAITHFUL, val keyShift: Int = 0,
    val seat: String? = null, val reads: String? = null, val lead: String? = null,
) {
    fun toCore() = ArrangeOptions(
        lineup = lineup.core,
        difficulty = difficulty.id,
        transpose = keyShift.takeIf { it != 0 },
        seat = seat,
        reads = reads.takeIf { seat != null },
        lead = lead.takeIf { seat != null && it == "seat" },
    )

    /** With the seat and clef of [choice]: none for "Not now" or "I conduct or listen". */
    fun withSeat(choice: SeatChoice, seats: List<no.brasscribe.play.model.Seat>): OutputOptions {
        val seat = choice.seatId?.let { id -> seats.firstOrNull { it.id == id } }
        return copy(seat = seat?.id, reads = seat?.let { s -> choice.readsOrNull?.takeIf { it != s.reads.firstOrNull() } }, lead = null)
    }
}

/** Where "What do you play?" was opened from: the first run, Settings, or "Who played this?" on a solo take. */
enum class SeatPickerMode { FIRST_RUN, SETTINGS, WHO_PLAYED }

/** A take with no harmony to arrange (a solo, or anything transcribed on the phone): no quartet for it. */
val TranscriptionResult.isSoloTake: Boolean get() = profile == Profile.SOLO

/** The full band can be written for this take: it has layers (see [fullBandMade]); by profile before the composition is known. */
val TranscriptionResult.fullBandMade: Boolean
    get() = composition?.fullBandMade ?: (profile != Profile.BRASS_BAND && profile != Profile.POP_ROCK)

/** The lineup this result was arranged for, when it was recorded. */
val TranscriptionResult.lineup: Lineup? get() = Lineup.recorded(composition)

/** The engine refused a quartet for this take (it has no harmony): the app says why in its own words. */
class QuartetNeedsGroupException : Exception("quartet needs a recording of the whole group")

/** The engine refused the tune on the seat's part (its lineup or seat cannot carry it). */
class LeadSeatRefusedException : Exception("the seat cannot carry the tune here")

/** Where Check the notes is: the part being checked ([voice]), the note on its card ([index]), and the notes put off. */
data class ReviewPlace(val voice: String, val index: Int?, val skipped: List<Int>)

/** A "?" on the score: its bar (1-based), how far into the bar in quarter notes, and the part it is on. */
data class ReviewTarget(val bar: Int, val quarters: Double, val part: String?)

/** A status line for sighted users that screen readers also hear (polite live region). */
data class Status(
    val text: String,
    val serial: Long = System.nanoTime(),
    /** Only for screen readers: the screen already shows it (the Listen button reads Stop), so no bar covers the card. */
    val quiet: Boolean = false,
)

class PlayViewModel(app: Application, private val savedState: SavedStateHandle) : AndroidViewModel(app) {
    val container = (app as PlayApplication).container
    private val res = app.resources
    private val scoreLibrary = container.scoreLibrary
    /**
     * Saves, deletes and reads of the library, one at a time and in order, off the main thread: a save
     * never lands after a later one, and a score is never read half-written.
     */
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    private val storage = Dispatchers.IO.limitedParallelism(1)
    /** This phone's scores (their details only), read in the background. */
    val savedScores = MutableStateFlow<List<SavedScore>>(emptyList())
    private val computerJobs = MutableStateFlow<List<no.brasscribe.play.engine.Job>>(emptyList())
    /** "Your scores": this phone's scores and the computer's latest finished ones, newest first. */
    val scores: StateFlow<List<ScoreEntry>> = kotlinx.coroutines.flow.combine(savedScores, computerJobs) { local, jobs ->
        ScoreEntry.merge(local, jobs)
    }.stateIn(viewModelScope, kotlinx.coroutines.flow.SharingStarted.Eagerly, emptyList())
    val openingScore = MutableStateFlow<String?>(null)
    /** The entry last tapped that opens in the other app (its id, and the tap's count): its row says so, where the finger is. */
    val opensElsewhere = MutableStateFlow<Pair<String, Int>?>(null)
    private val keptStore = container.keptRecordings
    /** Recordings kept in Your scores before they have a score (Product.KEEPS_RECORDINGS), newest first. */
    val keptRecordings = MutableStateFlow<List<KeptRecording>>(emptyList())
    /** What the kept recordings take on the phone, in bytes (Settings says it). */
    val keptBytes = MutableStateFlow(0L)
    /** "Open on the music stand" from the library: the score opens straight onto the stand (the entry id). */
    val standFromLibrary = MutableStateFlow<String?>(null)
    /** The library row that gets the focus back when a stand opened from the library closes. */
    val focusEntry = MutableStateFlow<String?>(null)
    /** Where each score was left in practice: on the phone, and the latest of each in memory while the app runs. */
    private val practicePlaces = ScorePlaces.of(app)
    private val practiceLeft = HashMap<String, ScorePlace>()

    /** The saved score on screen, whose practice place is kept; null for none. */
    val practiceScoreId: String? get() = currentSavedScoreId

    /** Where the score [id] was left in practice, or null. */
    suspend fun practicePlace(id: String): ScorePlace? = practiceLeft[id] ?: withContext(storage) { practicePlaces.read(id) }

    /** Keeps where the score [id] is in practice: written in order with every other write, an older one never last. */
    fun keepPracticePlace(id: String, place: ScorePlace) {
        if (practiceLeft[id] == place) return
        practiceLeft[id] = place
        // Only for a score still in Your scores: a place written after its score was deleted would stay for good.
        viewModelScope.launch { withContext(storage) { if (scoreLibrary.get(id) != null) practicePlaces.save(id, place) } }
    }

    /** Forgets what a new process would not have in memory (tests). */
    @androidx.annotation.VisibleForTesting
    internal fun forgetPracticeInMemory() = practiceLeft.clear()

    /** The saved copy of the score on screen; kept across process death, so the score can be reopened. */
    private var currentSavedScoreId: String?
        get() = savedState[KEY_SCORE]
        set(v) { savedState[KEY_SCORE] = v }

    private val backStack = MutableStateFlow(listOf(if (container.firstRunDone) Screen.HOME else Screen.FIRST_RUN))
    val screen: StateFlow<List<Screen>> = backStack.asStateFlow()

    val source = MutableStateFlow<Source?>(null)
    val profile = MutableStateFlow<Profile?>(null)
    val where = MutableStateFlow(Where.COMPANION)
    val transcribe = MutableStateFlow(TranscribeState())
    val result = MutableStateFlow<TranscriptionResult?>(null)
    val checked = MutableStateFlow<Map<String, Set<Int>>>(emptyMap())
    val output = MutableStateFlow(OutputOptions())
    val status = MutableStateFlow<Status?>(null)
    val busy = MutableStateFlow(false)

    /** How far an import has got (0..1) while it runs; null when there is nothing to measure. */
    val importProgress = MutableStateFlow<Float?>(null)
    val companionState = MutableStateFlow<String?>(null)
    private val clips = ClipPlayer()
    /** "Listen to this bar": [clipPlaying] is the bar playing now; the button shows Stop while it is. */
    val listening = BarListening(viewModelScope, clips) { e ->
        when (e) {
            is BarListening.Event.Started -> sayQuietly(if (e.withRecording) R.string.playing_bar_original else R.string.playing_bar_score, e.bar)
            is BarListening.Event.Stopped -> sayQuietly(R.string.listen_stopped)
            is BarListening.Event.Ended -> sayQuietly(R.string.listen_ended, e.bar)
            BarListening.Event.Unavailable -> say(R.string.listen_unavailable)
        }
    }
    val clipPlaying: StateFlow<Int?> = listening.playing

    /** Connected, looking for, offline or pair again: the status row on Home and in Settings. */
    val connection = ConnectionMonitor(viewModelScope, EngineConnection(container))
    /** A pairing link (QR code or brasscribe://pair) waiting for the user to press Connect. */
    val pendingLink = MutableStateFlow<PairLink?>(null)
    /** The four-digit code both screens show while the computer is asked to allow this phone. */
    val matchCode = MutableStateFlow<String?>(null)
    /** Asking the computer ended without an answer or with a no: offer "Ask again". */
    val askAgain = MutableStateFlow<String?>(null)
    private var askJob: Job? = null
    val problem = MutableStateFlow<Problem?>(null)
    /** The detail of the last problem (an engine message), shown under the reasons. */
    var problemDetail: String? = null
        private set
    /** What went wrong in the player's words, when it is known (ErrorWords): shown above the details. */
    var problemWhy: Int? = null
        private set
    /** The recording with no notes found in it was written down on the phone (not by the computer). */
    var noNotesOnPhone = false
        private set

    /** Set while the score screen is open: MIDI export and "Play this bar" go through it. */
    var scoreController: no.brasscribe.play.score.ScoreController? = null

    /** The last score screen's MIDI, for the export screen after it (the controller itself is let go). */
    var scoreMidi: no.brasscribe.play.score.ScoreMidi? = null

    private var job: Job? = null
    private var engineJobId: String? = null
    /** The engine's render of a score, by the job that made it: another score never plays it. */
    private var renderedScoreAudio: Pair<String, PcmAudio>? = null
    /** Level-matching of "Listen to this bar": the recording and the engine's rendered score, each measured whole. */
    private val recordingLevel = no.brasscribe.play.playback.LevelMatch()
    private val renderedLevel = no.brasscribe.play.playback.LevelMatch()

    init {
        // Leaving a place stops "Listen to this bar" (and asking the computer), whichever way the user left.
        viewModelScope.launch {
            backStack.map { it.last() }.distinctUntilChanged().drop(1).collect { top ->
                listening.stop(announce = false)
                if (top != Screen.COMPANION) cancelAsk()
            }
        }
        // The output choices follow the score on screen: its recorded lineup and difficulty, and never a
        // quartet for a solo take (it has no harmony to arrange).
        viewModelScope.launch {
            result.collect { r ->
                r ?: return@collect
                val recorded = r.lineup
                val difficulty = Difficulty.of(r.arrangementText("difficulty"))
                // Who it was written for, as recorded ("Who played this?" shows the score's own answer).
                val seat = r.composition?.arrangementString("seat")
                val synced = output.value.let { o ->
                    o.copy(
                        lineup = (recorded ?: if (r.isSoloTake && o.lineup == Lineup.QUARTET) Lineup.FULL else o.lineup).madeFor(r.fullBandMade),
                        difficulty = if (recorded != null && difficulty != null) difficulty else o.difficulty,
                        seat = if (recorded != null) seat else o.seat,
                        reads = if (recorded != null) r.composition?.arrangementString("reads") else o.reads,
                        lead = if (recorded != null) r.composition?.arrangementString("lead")?.takeIf { !r.isSoloTake } else o.lead,
                    )
                }
                // The score on screen is what these options make: Show the score re-arranges only after a change.
                output.value = synced
                lastApplied = synced
            }
        }
        restore()
        // Where the user is, and what they brought in, outlive the process (the system may end it in the background).
        viewModelScope.launch { backStack.collect { stack -> savedState[KEY_STACK] = ArrayList(stack.map { it.name }) } }
        viewModelScope.launch {
            var previous: File? = null
            source.collect { s ->
                savedState[KEY_SOURCE] = s?.let { SavedSource.of(it).encode() }
                // A recording or import that is no longer the source is not needed again: its copy goes.
                val old = previous
                previous = s?.file
                // In order with the kept recordings' changes: a take is never deleted under a keep that is waiting.
                if (old != null && old != s?.file) withContext(storage) { deleteCopy(old) }
            }
        }
    }

    /** Where recordings and imported copies are kept while they are the source. */
    private val takesDir get() = File(getApplication<Application>().cacheDir, "takes")

    /**
     * Deletes [file] when it is one of the app's own copies (a take or an import, or a kept recording that has
     * left Your scores), never anything else: a recording kept in Your scores stays.
     */
    private fun deleteCopy(file: File) {
        if (file.parentFile?.canonicalFile == takesDir.canonicalFile && file != CaptureController.activeFile()) file.delete()
        else if (keptStore.owns(file)) keptStore.prune(inUse = source.value?.file)
    }

    /**
     * After the process was ended in the background: back to the screen the user was on, with the source
     * they brought in and the score they had open; a step that cannot be resumed (recording, making the
     * score) goes back to the one before it. Then copies nothing refers to any more are cleared away.
     */
    private fun restore() {
        val names = savedState.get<ArrayList<String>>(KEY_STACK)
        val restoredSource = savedState.get<String>(KEY_SOURCE)?.let(SavedSource::decode)
        // The process ended while the full score of a draft was being made: the draft comes back.
        val scoreId = currentSavedScoreId ?: draftBehind
        draftBehind = null
        if (names != null) {
            val restored = names.mapNotNull { n -> Screen.entries.firstOrNull { it.name == n } }
            val sourceBack = restoredSource?.takeIf { it.file == null || it.file.isFile }
            source.value = sourceBack?.toSource()
            val plain = RestoredStack.plain(restored, hasSource = sourceBack != null)
            backStack.value = plain
            if (scoreId != null && RestoredStack.needsScore(restored)) {
                // Dispatched, not immediate: this runs from the constructor, and a score read back before the
                // constructor has finished would be shown on a view model whose later fields are not set yet.
                viewModelScope.launch(Dispatchers.Main) {
                    val saved = withContext(storage) { scoreLibrary.get(scoreId)?.let { it to scoreLibrary.content(it.id) } }
                    val content = saved?.second ?: return@launch
                    if (backStack.value != plain) return@launch
                    // The recording the score was made from is still the source, as before the process ended:
                    // What is this? under the score can send it again, and a take is not deleted from the phone.
                    showSaved(saved.first, content, recording = source.value?.takeIf { it.file != null })
                    backStack.value = RestoredStack.withScore(restored, hasSource = sourceBack != null)
                }
            }
        }
        viewModelScope.launch {
            val keep = source.value?.file
            val list = withContext(storage) {
                // Takes and imports from before, and the rendered scores fetched for "Listen to this bar".
                takesDir.listFiles()?.filter { it != keep && it != CaptureController.activeFile() }?.forEach { it.delete() }
                getApplication<Application>().cacheDir.listFiles { f -> f.name.startsWith("score-") && f.name.endsWith(".mp3") }?.forEach { it.delete() }
                keptStore.prune(inUse = keep)
                // A score deleted while its place was being written leaves nothing behind; one still on the phone keeps it.
                practicePlaces.prune(scoreLibrary::has)
                scoreLibrary.list()
            }
            savedScores.value = list
            refreshKept()
        }
    }

    fun navigate(to: Screen) = backStack.update { it + to }

    /**
     * The score: back to the one already in the stack (from Check the notes, How should the score be?), so Check them
     * and Show the score don't pile up scores one on another; else a new one.
     */
    fun showScore() = backStack.update { s ->
        val at = s.lastIndexOf(Screen.SCORE)
        if (at >= 0) s.take(at + 1) else s + Screen.SCORE
    }

    /**
     * After a score is made, [next] takes the transcribing screen's place. Check the notes goes over the score: Back from
     * it shows the score that is already saved, and never sends the recording again. What is this? stays under the
     * score, so its answer can still be changed.
     */
    private fun afterTranscription(next: Screen) = backStack.update { s ->
        val below = s.dropLast(1)
        if (next == Screen.REVIEW && below.lastOrNull() != Screen.SCORE) below + Screen.SCORE + Screen.REVIEW else below + next
    }

    /** A score opened from Your scores: Check the notes goes over a band score, so Back from there shows the score (a product that checks no band score keeps its own). */
    private fun opened(review: Boolean) = when {
        !review -> listOf(Screen.HOME, Screen.SCORE)
        result.value?.let { Product.arranges(it.profile) } == true -> listOf(Screen.HOME, Screen.SCORE, Screen.REVIEW)
        else -> listOf(Screen.HOME, Screen.REVIEW)
    }

    fun replaceTop(to: Screen) = backStack.update { it.dropLast(1) + to }

    /**
     * Leaving Check the notes forwards: How should the score be?, or, where the product says so (a solo in Brasscribe),
     * the score itself, with the choices it was made with (applied first only if they changed).
     */
    fun afterReview() {
        val r = result.value
        if (r != null && Product.afterReview(r) == Screen.SCORE) applyOutput { showScore() } else navigate(Screen.OUTPUT)
    }
    fun back(): Boolean {
        if (backStack.value.size <= 1) return false
        if (backStack.value.last() == Screen.TRANSCRIBE) cancelTranscription()
        backStack.update { it.dropLast(1) }
        showDraftBehind()
        return true
    }

    /**
     * The draft that "Make the full score" started from. Making the full score puts a new source in the draft's
     * place; when the player comes back before it is ready (Cancel, or back from a problem), the draft is
     * shown again.
     */
    private var draftBehind: String?
        get() = savedState[KEY_DRAFT_BEHIND]
        set(v) { savedState[KEY_DRAFT_BEHIND] = v }

    private fun showDraftBehind() {
        val id = draftBehind ?: return
        if (result.value != null || backStack.value.last() !in setOf(Screen.SCORE, Screen.REVIEW)) return
        draftBehind = null
        viewModelScope.launch {
            val saved = withContext(storage) { scoreLibrary.get(id)?.let { it to scoreLibrary.content(id) } }
            val content = saved?.second
            if (content == null) { home(); return@launch }
            // Only while the player is still there, and nothing else took its place.
            if (result.value == null && backStack.value.last() in setOf(Screen.SCORE, Screen.REVIEW)) showSaved(saved.first, content)
        }
    }

    fun home() { backStack.value = listOf(Screen.HOME) }

    /** Get started: "What do you play?" next, the first run's one question (skipped without the core's seats). */
    fun finishFirstRun() {
        if (container.seats.isEmpty()) { endFirstRun(); return }
        seatPicker = SeatPickerMode.FIRST_RUN
        backStack.value = listOf(Screen.WHAT_DO_YOU_PLAY)
    }

    private fun endFirstRun() {
        container.firstRunDone = true
        focusHomeTitle.value = true
        backStack.value = listOf(Screen.HOME)
    }

    // ---- What do you play? ----------------------------------------------------------------------------

    /** Where the picker was opened from; it decides what Continue changes. */
    var seatPicker: SeatPickerMode = SeatPickerMode.FIRST_RUN
        private set

    /** After the first run, focus goes to the Home title; after Settings' picker, back to its row. */
    val focusHomeTitle = MutableStateFlow(false)
    val focusSeatRow = MutableStateFlow(false)

    fun openSeatPicker(mode: SeatPickerMode) {
        seatPicker = mode
        navigate(Screen.WHAT_DO_YOU_PLAY)
    }

    /** The seat as the picker starts: this solo take's player for "Who played this?", else the setting. */
    fun seatPickerStart(): SeatChoice = when (seatPicker) {
        SeatPickerMode.WHO_PLAYED -> output.value.seat?.let { id ->
            SeatChoice.Player(id, output.value.reads ?: container.seats.firstOrNull { it.id == id }?.reads?.firstOrNull())
        } ?: container.seat
        else -> container.seat
    }

    /**
     * Continue (or "I conduct or listen"): the only moment the answer is applied (WCAG 3.2.2). Settings
     * and the first run save it for the phone; "Who played this?" changes only this take, on Show the score.
     */
    fun chooseSeat(choice: SeatChoice) {
        when (seatPicker) {
            SeatPickerMode.FIRST_RUN -> { container.updateSeat(choice); endFirstRun() }
            SeatPickerMode.SETTINGS -> { container.updateSeat(choice); focusSeatRow.value = true; back() }
            SeatPickerMode.WHO_PLAYED -> { output.update { it.withSeat(choice, container.seats) }; back() }
        }
    }

    /** "Not now" on the first run: nothing is set, and it is not asked again. */
    fun skipSeat() = endFirstRun()

    /** "Make this my part", per score: saved with it; the seat in Settings stays as it is. */
    val myPartOverride = MutableStateFlow<String?>(null)

    /** The one-line lineup notice was closed for the score on screen; it is not shown for it again. */
    val mappedNoticeSeen = MutableStateFlow(false)

    fun closeMappedNotice() {
        mappedNoticeSeen.value = true
        result.value?.let(::saveCurrentScore)
    }

    fun makeMyPart(part: String) {
        myPartOverride.value = part
        result.value?.let(::saveCurrentScore)
        say(R.string.my_part_made, no.brasscribe.play.ui.PartNames.display(part))
    }

    /** "Your part" among [parts] of [r]: this score's pick, else the seat's part (the core's table). */
    fun yourPart(parts: List<String>, r: TranscriptionResult?): YourPart =
        YourParts.resolve(parts, r?.lineup ?: Lineup.ofParts(parts), container.seat, myPartOverride.value, container.seats, container.core::seatPart)

    /** Where each part of [r] came from, by part name (the core's part_sources); empty for an opened score. */
    fun partSources(r: TranscriptionResult): Map<String, no.brasscribe.play.model.PartSource> =
        r.compositionJsonFor(container.core)?.let { runCatching { container.core.partSources(it) }.getOrNull() }.orEmpty()

    /** Shows [p] full screen, replacing the step that failed (the recording is kept). */
    fun showProblem(p: Problem, detail: String? = null, @androidx.annotation.StringRes why: Int? = null) {
        problem.value = p
        problemDetail = detail
        problemWhy = why
        backStack.update { (if (it.last() in setOf(Screen.TRANSCRIBE, Screen.RECORD)) it.dropLast(1) else it) + Screen.PROBLEM }
    }

    fun say(@StringRes id: Int, vararg args: Any) { status.value = Status(res.getString(id, *args)) }
    private fun sayQuietly(@StringRes id: Int, vararg args: Any) { status.value = Status(res.getString(id, *args), quiet = true) }
    private fun sayText(text: String) { status.value = Status(text) }

    // ---- Import ---------------------------------------------------------------------------------------

    fun importUri(uri: Uri) {
        val ctx = getApplication<Application>()
        busy.value = true
        viewModelScope.launch {
            // Asking the provider for the name can block on its process: not on the main thread.
            val name = withContext(Dispatchers.IO) { displayName(uri, "recording") }
            if (name.substringAfterLast('.', "").lowercase() in SCORE_EXTENSIONS) { openScore(uri, name); return@launch }
            importProgress.value = 0f
            say(R.string.reading_file, name)
            try {
                // Never the whole file in memory: a video's sound is taken out on disk, the PCM decoded a buffer at a time.
                // The file is read on a worker; how far it has got is shown from here, on the main thread.
                var extracting = false
                val imported = reportedHere<Pair<MediaImport.Phase, Double>, _>(Dispatchers.IO, show = { (phase, f) ->
                    if (phase == MediaImport.Phase.EXTRACT && !extracting) {
                        extracting = true
                        sayQuietly(R.string.extracting_sound, name)
                    }
                    // Copying and taking the sound out are the long part; decoding the result is quick.
                    importProgress.value = (if (phase == MediaImport.Phase.DECODE) 0.8 + 0.2 * f else 0.8 * f).toFloat()
                }) { report ->
                    MediaImport.import(ctx, uri, name, File(ctx.cacheDir, "takes")) { phase, f -> report(phase to f) }
                }
                val kind = if (imported.hasVideo) SourceKind.VIDEO else SourceKind.FILE
                setSource(Source(name, kind, imported.durationS, imported.audio, imported.file))
                say(if (imported.hasVideo) R.string.imported_video else R.string.imported, name, durationText(imported.durationS))
                navigate(Screen.PROFILE)
            } catch (e: UnsupportedMediaException) {
                showProblem(Problem.NO_SOUND_TRACK)
            } catch (e: OutOfMemoryError) {
                showProblem(Problem.TOO_LARGE, e.toString())
            } catch (e: Exception) {
                showProblem(if (isTooLarge(e)) Problem.TOO_LARGE else Problem.FILE_UNREADABLE, e.message ?: e.toString())
            } finally {
                busy.value = false
                importProgress.value = null
            }
        }
    }

    private fun displayName(uri: Uri, fallback: String): String =
        runCatching {
            getApplication<Application>().contentResolver
                .query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
        }.getOrNull() ?: uri.lastPathSegment ?: fallback

    fun openScoreUri(uri: Uri) {
        busy.value = true
        viewModelScope.launch { openScore(uri, withContext(Dispatchers.IO) { displayName(uri, "score") }) }
    }

    /**
     * Opens a MusicXML score with no transcription behind it: straight to the score, so Play is also
     * a reader for parts that were written elsewhere. `.mxl` is a zip whose container names the root file.
     */
    private fun openScore(uri: Uri, name: String) {
        val ctx = getApplication<Application>()
        busy.value = true
        say(R.string.reading_file, name)
        viewModelScope.launch {
            try {
                val xml = withContext(Dispatchers.IO) {
                    ctx.contentResolver.openInputStream(uri)!!.use { input ->
                        if (name.endsWith(".mxl", ignoreCase = true)) unzipScore(input)
                        else String(readLimited(input, MAX_SCORE_BYTES), Charsets.UTF_8)
                    }
                }
                require(xml.contains("score-partwise") || xml.contains("score-timewise")) { "not MusicXML" }
                setSource(Source(name, SourceKind.SCORE, 0.0))
                val opened = TranscriptionResult(null, xml, Profile.BRASS_BAND, onDevice = true)
                result.value = opened
                saveCurrentScore(opened, name.substringBeforeLast('.'))
                say(R.string.opened_score, name)
                navigate(Screen.SCORE)
            } catch (e: OutOfMemoryError) {
                showProblem(Problem.TOO_LARGE, e.toString())
            } catch (e: Exception) {
                showProblem(if (isTooLarge(e)) Problem.TOO_LARGE else Problem.FILE_UNREADABLE, e.message ?: e.toString())
            } finally {
                busy.value = false
            }
        }
    }

    /**
     * The root score of a compressed MusicXML container, or the first .xml that is not the container.
     * Read from the stream entry by entry; only the container and .xml entries are kept, each capped.
     */
    private fun unzipScore(input: java.io.InputStream): String {
        val entries = HashMap<String, ByteArray>()
        var kept = 0L
        ZipInputStream(input.buffered()).use { zip ->
            while (true) {
                val e = zip.nextEntry ?: break
                if (e.isDirectory || !(e.name.endsWith(".xml", true) || e.name.endsWith(".musicxml", true))) continue
                val bytes = readLimited(zip, MAX_SCORE_BYTES - kept)
                kept += bytes.size
                entries[e.name] = bytes
            }
        }
        val root = entries["META-INF/container.xml"]?.decodeToString()
            ?.let { Regex("""full-path\s*=\s*"([^"]+)"""").find(it)?.groupValues?.get(1) }
        val chosen = root?.let { entries[it] }
            ?: entries.entries.firstOrNull { it.key.endsWith(".xml", true) && !it.key.startsWith("META-INF") }?.value
        return requireNotNull(chosen) { "no score in the container" }.decodeToString()
    }

    /** A finished take, already on disk; its samples are null when it was too long to keep in memory. */
    fun recorded(take: CapturedTake, kind: SourceKind) {
        // A recording is named by when it was made, never by its file's timestamp (review 3).
        setSource(Source(ScoreTitles.recording(System.currentTimeMillis()), kind, take.seconds, take.audio, take.file))
        say(R.string.record_stopped, durationText(take.seconds))
        replaceTop(Screen.PROFILE)
    }

    /** Internal so instrumented tests can open a source without a file picker. */
    internal fun setSource(s: Source) {
        source.value = s
        currentSavedScoreId = null
        result.value = null
        checked.value = emptyMap()
        reviewChanges.value = emptyMap()
        renderedScoreAudio = null
        mappedNoticeSeen.value = false
        myPartOverride.value = null
        // A new take is the player's own, as Settings says; a friend's seat from the last one does not carry over.
        output.update { it.withSeat(container.seat, container.seats) }
        profile.value = null
        draftBehind = null
        where.value = if (s.kind == SourceKind.MICROPHONE && container.hasPitchModel) Where.DEVICE else Where.COMPANION
    }

    fun durationText(seconds: Double): String {
        val total = seconds.toInt()
        val m = total / 60
        val s = total % 60
        val sec = res.getQuantityString(R.plurals.duration_seconds, s, s)
        return if (m == 0) sec else res.getQuantityString(R.plurals.duration_minutes, m, m) + " " + sec
    }

    // ---- Transcription --------------------------------------------------------------------------------

    fun chooseProfile(p: Profile) {
        profile.value = p
        // A solo is made on the phone by default; a brass band goes to the computer when it is there and is
        // otherwise a draft on the phone; the other choices need the computer (OnDeviceRouting).
        where.value = OnDeviceRouting.defaultWhere(p, canTranscribeOnDevice(), computerThere())
    }

    fun canTranscribeOnDevice(): Boolean = OnDeviceRouting.canRunOnDevice(profile.value, container.hasPitchModel,
        container.hasBandModels, source.value?.audio != null)

    /** The computer is there to make a score (the fixture engine of the UI tests always is). */
    fun computerThere(): Boolean = container.usingFixture || OnDeviceRouting.computerThere(connection.state.value)

    fun startTranscription() {
        val p = profile.value ?: return
        val s = source.value ?: return
        // A drummer's solo take is no drum part: refused before anything is transcribed (the screen says so too).
        if (p == Profile.SOLO && percussionSeat(container.seat, container.seats)) { say(R.string.percussion_solo_refused); return }
        navigate(Screen.TRANSCRIBE)
        val previous = job
        previous?.cancel()
        job = viewModelScope.launch {
            // A run that was cancelled stops at its next step; the new one starts after it, never beside it.
            previous?.join()
            try {
                val r = when {
                    where.value != Where.DEVICE || !canTranscribeOnDevice() -> transcribeWithEngine(s, p)
                    p == Profile.BRASS_BAND -> transcribeBandDraft(s)
                    else -> transcribeOnDevice(s)
                }
                // Check the notes needs a note to check (a very low recording can have none on the phone).
                if (foundNoNotes(r, Product.afterTranscription(r))) {
                    transcribe.update { it.copy(running = false) }
                    noNotesOnPhone = r.onDevice
                    showProblem(Problem.NO_NOTES)
                    return@launch
                }
                val ignored = seatIgnored(r)
                reviewChanges.value = emptyMap()
                draftBehind = null
                result.value = r
                saveCurrentScore(r)
                // It has a score now: a recording kept in Your scores leaves it (its file goes once it is not in hand).
                forgetKept(s)
                transcribe.update { it.copy(running = false, fraction = 1.0, etaSeconds = 0) }
                // An engine that ignored the seat wrote for Solo Cornet: say so once, not silently.
                if (ignored) sayText(res.getString(R.string.transcribe_done) + " " + res.getString(R.string.engine_too_old_seat))
                else say(R.string.transcribe_done)
                afterTranscription(Product.afterTranscription(r))
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: OutOfMemoryError) {
                transcribe.update { it.copy(running = false, error = e.toString()) }
                keepRecording(s)
                showProblem(Problem.TOO_LARGE, e.toString())
            } catch (e: DraftTooLongException) {
                transcribe.update { it.copy(running = false, error = e.message) }
                keepRecording(s)
                showProblem(Problem.DRAFT_TOO_LONG, e.message)
            } catch (e: Exception) {
                transcribe.update { it.copy(running = false, error = e.message ?: e.javaClass.simpleName) }
                keepRecording(s)
                showProblem(if (isTooLarge(e)) Problem.TOO_LARGE else Problem.SCORE_FAILED, e.message ?: e.toString(),
                    ErrorWords.of(e).takeIf { it != R.string.error_generic })
            }
        }
    }

    /** Starts again after a failed run, with the same recording and answer. */
    fun retryTranscription() {
        backStack.update { it.dropLast(1) }
        startTranscription()
    }

    /**
     * The phone would not let the draft's service into the foreground (its daily time for such work is used up,
     * for one): the draft stops, and the problem screen says to try later or to use the computer.
     */
    internal fun draftRefused() {
        job?.cancel()
        transcribe.update { it.copy(running = false) }
        source.value?.let(::keepRecording)
        showProblem(Problem.DRAFT_REFUSED)
    }

    /** The way forward from a take too long for a draft on the phone: the same recording, made on the computer. */
    fun makeOnComputer() {
        where.value = Where.COMPANION
        retryTranscription()
    }

    private suspend fun transcribeOnDevice(s: Source): TranscriptionResult {
        val audio = s.audio!!
        val steps = listOf(Step.DECODE, Step.PITCH, Step.CONFIRM, Step.BEATS, Step.ARRANGE)
        transcribe.value = TranscribeState(true, Step.DECODE, 0.0, 0, steps.size, estimateDeviceSeconds(audio), res.getString(R.string.transcribe_where_device), steps = steps)
        val title = ScoreTitles.withoutExtension(s.name)
        return withContext(Dispatchers.Default) {
            // The models run as plain blocking calls: Cancel is checked between their stages.
            val running = coroutineContext.job
            // The core takes the WAV as bytes and the take keeps them for re-arranging, so only a take that fits.
            val wav = s.file?.takeIf { it.extension.equals("wav", true) && it.length() <= MAX_CORE_WAV_BYTES }?.readBytes()
            container.openSoloPipeline().use { pipeline ->
                val (take, stats) = pipeline.pipeline.listen(audio.samples, audio.sampleRate, title, wav) { stage ->
                    running.ensureActive()
                    val step = steps[stage.ordinal.coerceAtMost(steps.size - 1)]
                    transcribe.update { it.copy(step = step, stepIndex = stage.ordinal, fraction = stage.ordinal / steps.size.toDouble(),
                        etaSeconds = ((1 - stage.ordinal / steps.size.toDouble()) * estimateDeviceSeconds(audio)).toInt()) }
                }
                running.ensureActive()
                transcribe.update { it.copy(step = Step.ARRANGE, stepIndex = 4, fraction = 0.9) }
                val a0 = System.nanoTime()
                // A solo take has no harmony for a quartet: the full band then, as the Output screen shows it.
                val opts = output.value.let { if (it.lineup == Lineup.QUARTET) it.copy(lineup = Lineup.FULL) else it }
                val arranged = runCatching { pipeline.pipeline.arrange(take, opts.toCore()) }
                    .onFailure { android.util.Log.w(TAG, "core arrangement failed", it) }.getOrNull()
                val arrangeMs = (System.nanoTime() - a0) / 1_000_000
                android.util.Log.i(TAG, "on-device solo: %.1f s audio, SwiftF0 %d notes, Basic Pitch %d, beats %d (%s), downbeats %d, stages %s ms, arrange %d ms, core %s"
                    .format(stats.audioSeconds, stats.swiftF0Notes, stats.basicPitchNotes, stats.beats, stats.beatSource, stats.downbeats,
                        stats.ms.entries.joinToString { "${it.key.name.lowercase()} ${it.value}" }, arrangeMs, container.core.name))
                soloTake = take
                val models = listOf(
                    NoteEvidenceBuilder.ModelNotes("swift-f0", "SwiftF0", take.swiftF0),
                    NoteEvidenceBuilder.ModelNotes("basic-pitch", "Basic Pitch", take.basicPitch),
                )
                if (arranged != null) {
                    // Kept for inspection (adb pull): the last on-device arrangement, as the core wrote it.
                    runCatching { getApplication<Application>().getExternalFilesDir("runs")?.resolve("last-solo-composition.json")?.writeText(arranged.compositionJson) }
                    TranscriptionResult(arranged.composition, arranged.musicXml, Profile.SOLO, onDevice = true, compositionJson = arranged.compositionJson,
                        evidence = NoteEvidenceBuilder.build(arranged.composition, models))
                } else {
                    // Without the Rust core: the Kotlin grid and a single solo part.
                    val c = container.core.quantizeSolo(take.swiftF0, TempoEstimator.estimate(take.swiftF0.map { it.onsetS }), title)
                    TranscriptionResult(c, container.core.toMusicXml(c, listOf(PartSpec("solo", SOLO_PART_NAME, Instrument.CORNET))), Profile.SOLO, onDevice = true,
                        evidence = NoteEvidenceBuilder.build(c, models))
                }
            }
        }
    }

    /** The last on-device take, kept so Output options re-arrange it without listening again. */
    private var soloTake: SoloTake? = null

    /**
     * A band draft on the phone: the engine's brass-band profile without MuScriptor (Basic Pitch on the mix,
     * Beat This! small, the core's song arranger), in a foreground service so it goes on when the player
     * leaves the app. A take longer than free memory holds is refused before anything runs.
     */
    private suspend fun transcribeBandDraft(s: Source): TranscriptionResult {
        val audio = s.audio!!
        val app = getApplication<Application>()
        val memory = android.app.ActivityManager.MemoryInfo().also { app.getSystemService(android.app.ActivityManager::class.java).getMemoryInfo(it) }
        if (!no.brasscribe.play.pitch.BandDraftPipeline.fits(audio.seconds, memory.availMem))
            throw DraftTooLongException("%.0f s, %d MB free".format(audio.seconds, memory.availMem shr 20))
        val steps = listOf(Step.TRANSCRIBE, Step.BEATS, Step.ARRANGE)
        val eta = estimateDeviceSeconds(audio)
        transcribe.value = TranscribeState(true, steps[0], 0.0, 0, steps.size, eta,
            res.getString(OnDeviceRouting.transcribingWhere(draft = true)), steps = steps, draft = true)
        val title = ScoreTitles.withoutExtension(s.name)
        // A band draft is re-arranged from its Composition (Output), never from a solo take.
        soloTake = null
        DraftService.start(app, ::draftRefused)
        try {
            return withContext(Dispatchers.Default) {
                // The models run as plain blocking calls: Cancel is checked between their stages.
                val running = coroutineContext.job
                container.openBandDraftPipeline().use { open ->
                    val (take, stats) = open.pipeline.listen(audio.samples, audio.sampleRate, title) { stage ->
                        running.ensureActive()
                        transcribe.update { it.copy(step = steps[stage.ordinal], stepIndex = stage.ordinal, fraction = stage.ordinal / steps.size.toDouble(),
                            etaSeconds = ((1 - stage.ordinal / steps.size.toDouble()) * eta).toInt()) }
                    }
                    running.ensureActive()
                    transcribe.update { it.copy(step = Step.ARRANGE, stepIndex = 2, fraction = 0.9) }
                    val a0 = System.nanoTime()
                    val arranged = requireNotNull(open.pipeline.arrange(take, output.value.toCore())) { "the core is not available" }
                    android.util.Log.i(TAG, "on-device band draft: %.1f s audio, Basic Pitch %d notes, beats %d, downbeats %d, stages %s ms, arrange %d ms"
                        .format(stats.audioSeconds, stats.basicPitchNotes, stats.beats, stats.downbeats,
                            stats.ms.entries.joinToString { "${it.key.name.lowercase()} ${it.value}" }, (System.nanoTime() - a0) / 1_000_000))
                    TranscriptionResult(arranged.composition, arranged.musicXml, Profile.BRASS_BAND, onDevice = true,
                        compositionJson = arranged.compositionJson, draft = true,
                        evidence = NoteEvidenceBuilder.build(arranged.composition,
                            listOf(NoteEvidenceBuilder.ModelNotes("basic-pitch", "Basic Pitch", take.basicPitch))))
                }
            }
        } finally {
            DraftService.stop(app)
        }
    }

    /**
     * "Make the full score": the draft's kept recording goes to the computer as a brass band score. It becomes a
     * new score; the draft stays in Your scores.
     */
    fun makeFullScore() {
        val id = currentSavedScoreId ?: return
        val r = result.value?.takeIf { it.draft } ?: return
        viewModelScope.launch {
            val recording = withContext(storage) { scoreLibrary.recordingFile(id) } ?: return@launch
            val title = source.value?.name ?: r.composition?.title.orEmpty()
            setSource(Source(title, SourceKind.FILE, 0.0, audio = null, file = recording))
            draftBehind = id
            profile.value = Profile.BRASS_BAND
            where.value = Where.COMPANION
            startTranscription()
        }
    }

    /**
     * Applies the Output options: on-device results are re-arranged by the core; engine results
     * become a new engine job with the options (the engine's cache makes it quick).
     */
    fun applyOutput(then: () -> Unit) {
        val r = result.value ?: return
        val opts = output.value
        if (opts == lastApplied) { then(); return }
        busy.value = true
        viewModelScope.launch {
            try {
                val take = soloTake
                // Only arranging the Composition again keeps the notes changed in Review (they are in it);
                // a take or the computer writes them afresh.
                val fromComposition = !(r.onDevice && take != null) && !(!r.onDevice && r.audioId != null)
                val updated = when {
                    r.onDevice && take != null -> withContext(Dispatchers.Default) {
                        container.core.arrangeSolo(take, opts.toCore())?.let {
                            runCatching { getApplication<Application>().getExternalFilesDir("runs")?.resolve("last-solo-composition.json")?.writeText(it.compositionJson) }
                            r.copy(composition = it.composition, musicXml = it.musicXml, compositionJson = it.compositionJson,
                                appliedTranspose = opts.keyShift)
                        }
                    }
                    !r.onDevice && r.audioId != null -> rerunWithEngine(r, opts)
                    // A score arranged on the phone before (no take kept): the core re-arranges its Composition.
                    r.onDevice && r.composition != null -> withContext(Dispatchers.Default) { rearrange(r, opts) }
                    else -> null
                }
                if (updated != null) {
                    lastApplied = opts
                    if (!fromComposition) reviewChanges.value = emptyMap()
                    result.value = updated
                    saveCurrentScore(updated)
                }
                if (updated != null && !updated.onDevice && seatFellBack)
                    sayText(res.getString(R.string.arrangement_ready) + " " + res.getString(R.string.engine_too_old_seat))
                else say(R.string.arrangement_ready)
                then()
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                // In the player's words; the engine's or the core's own text goes to the log only.
                android.util.Log.w(TAG, "re-arrangement failed", e)
                say(ErrorWords.of(e))
            } finally {
                busy.value = false
            }
        }
    }

    private var lastApplied: OutputOptions = OutputOptions()

    /** The engine refused the seat and wrote for [SEAT_FALLBACK]'s instead (the last engine job). */
    private var seatFellBack = false

    /** A seat went to the computer and came back unrecorded or refused: that Brasscribe is too old to write for it. */
    private fun seatIgnored(r: TranscriptionResult): Boolean =
        !r.onDevice && output.value.seat != null && r.composition != null &&
            (seatFellBack || r.composition.arrangementString("seat") == null)

    private suspend fun rerunWithEngine(r: TranscriptionResult, opts: OutputOptions): TranscriptionResult {
        val engine = container.engine() ?: throw NoCompanionException()
        val core = opts.toCore()
        // Re-arrangements skip the MP3 render: it is one more MuseScore run on the engine's machine.
        seatFellBack = false
        val job = try {
            engine.createJobForSeat(JobCreate(r.audioId, r.profile.id, renderAudio = false,
                allowHeavy = container.settings.allowHeavy, title = r.composition?.title.orEmpty(), lineup = opts.lineup.madeFor(r.fullBandMade).engine,
                difficulty = core.difficulty, transpose = core.transpose, seat = core.seat, reads = core.reads, lead = core.lead))
                .also { seatFellBack = it.second }.first
        } catch (e: EngineException) {
            // The engine's own words stay out of the app: a refused quartet gets the card's reason.
            if (e.status == 422 && e.code == null && opts.lineup == Lineup.QUARTET) throw QuartetNeedsGroupException()
            if (e.status == 422 && e.code == null && core.lead == "seat") throw LeadSeatRefusedException()
            throw e
        }
        engine.events(job.id).collect { }
        val final = engine.job(job.id)
        if (final.status != JobStatus.SUCCEEDED) throw EngineJobFailedException(final.error ?: final.status.name.lowercase())
        return r.copy(composition = engine.composition(job.id), musicXml = engine.musicXml(job.id), jobId = job.id,
            engineOutputs = final.outputs.toSet(), compositionJson = null, appliedTranspose = opts.keyShift,
            evidence = runCatching { engine.evidence(job.id) }.getOrNull())
    }

    private fun estimateDeviceSeconds(audio: PcmAudio): Int = maxOf(1, (audio.seconds / 20).toInt())

    private suspend fun transcribeWithEngine(s: Source, p: Profile): TranscriptionResult {
        val engine: EngineApi = container.engine() ?: throw NoCompanionException()
        val stages = FixtureEngineApi.stagesOf(p).size
        transcribe.value = TranscribeState(true, Step.UPLOAD, 0.0, 0, stages, null,
            res.getString(R.string.transcribe_where_companion, Product.computerName(this)))
        // Streamed from the file: memory stays flat whatever its size (a video arrives here as its sound only).
        // The phone's copy: the recording opened, else the one the product kept for the song.
        val copy = withContext(Dispatchers.IO) { s.file?.takeIf { it.isFile }?.let { UploadSource.of(it) } ?: Product.keptRecording(this@PlayViewModel) }
        // A source with no file (tests) sends an empty upload, as before.
        val upload = copy ?: s.file?.let { UploadSource.of(it) } ?: UploadSource.of(s.name, ByteArray(0))
        // A product that writes a song down again names the recording the computer already holds: nothing is sent twice,
        // unless the computer no longer has it.
        val (audioId, created) = jobFromRecording(
            held = { Product.audioOnComputer(this, engine) },
            canSend = copy != null,
            send = {
                withContext(Dispatchers.IO) {
                    engine.uploadAudio(upload) { sent, total ->
                        if (total > 0) transcribe.update { it.copy(fraction = (sent.toDouble() / total).coerceIn(0.0, 1.0)) }
                    }
                }.audioId
            },
            resent = { say(R.string.recording_sent_again) },
        ) { audioId ->
            transcribe.update { it.copy(fraction = 0.0) }
            seatFellBack = false
            engine.createJobForSeat(
                // The product adds what its own profiles take (a bass tab's instrument and tuning).
                Product.job(this, JobCreate(audioId, p.id, renderAudio = true, allowHeavy = container.settings.allowHeavy,
                    title = ScoreTitles.withoutExtension(s.name), seat = output.value.seat, reads = output.value.reads.takeIf { output.value.seat != null })),
            ).also { seatFellBack = it.second }.first
        }
        engineJobId = created.id
        // Followed while the player is away from the app, with a notification when it is done.
        ComputerJobService.start(getApplication(), created.id, ScoreTitles.withoutExtension(s.name))
        val kinds = created.stages.map { Step.ofKind(it.kind ?: it.name.substringBefore('.')) }.filter { it != Step.QUEUED }.distinct()
        transcribe.update { it.copy(steps = listOf(Step.UPLOAD) + kinds.ifEmpty { listOf(Step.BEATS, Step.STEMS, Step.LAYERS, Step.TRANSCRIBE, Step.ARRANGE, Step.EXPORT) }) }
        val tracker = ProgressTracker(created.stages.size.takeIf { it > 0 } ?: stages)
        val streamed = runCatching {
            engine.events(created.id).collect { e ->
                val pr = tracker.onEvent(e)
                transcribe.update {
                    it.copy(step = if (pr.currentKind != null) Step.ofKind(pr.currentKind) else Step.QUEUED, fraction = pr.fraction,
                        stepIndex = pr.stagesDone, stepTotal = pr.stagesTotal, etaSeconds = pr.etaSeconds, error = pr.error)
                }
            }
        }
        streamed.exceptionOrNull()?.let { if (it is kotlinx.coroutines.CancellationException) throw it }
        // The events stop when the phone loses the computer for a while (the player left the app and the Wi-Fi slept):
        // the job goes on there, so it is asked for until it ends. Only a computer that stays away is a failure.
        val final = if (streamed.isSuccess) engine.job(created.id)
        else JobFollow.untilEnded({ engine.job(created.id) }, pause = followPause, tries = FOLLOW_TRIES) ?: throw streamed.exceptionOrNull()!!
        // Seen here, in front: nothing more for the notification to say.
        if (AppInFront.now) ComputerJobService.stop(getApplication())
        if (final.status != JobStatus.SUCCEEDED) throw EngineJobFailedException(final.error ?: final.status.name.lowercase())
        val composition = engine.composition(created.id)
        val xml = engine.musicXml(created.id)
        return TranscriptionResult(composition, xml, p, onDevice = false, jobId = created.id, audioId = audioId,
            engineOutputs = final.outputs.toSet().ifEmpty { FixtureEngineApi.OUTPUTS.toSet() },
            evidence = runCatching { engine.evidence(created.id) }.getOrNull())
    }

    fun cancelTranscription() {
        job?.cancel()
        ComputerJobService.stop(getApplication())
        val id = engineJobId
        if (id != null) viewModelScope.launch { runCatching { container.engine()?.cancel(id) } }
        engineJobId = null
        if (transcribe.value.running) {
            transcribe.update { it.copy(running = false) }
            val s = source.value
            // Said once the recording is kept, and only then that it is in Your scores.
            if (s != null && keepsRecording(s)) keepRecording(s) { kept -> say(if (kept) R.string.transcribe_cancelled_kept else R.string.transcribe_cancelled) }
            else say(R.string.transcribe_cancelled)
        }
    }

    // ---- Recordings kept in Your scores ----------------------------------------------------------------

    /**
     * Keeps the recording [s] in Your scores: its score was not made (it failed, was put off or was stopped). A take
     * or an import moves out of the app's cache into the kept recordings, and stays the recording in hand. A score's
     * own recording (a draft's, for Make the full score) stays with its score.
     */
    private fun keepRecording(s: Source, done: (Boolean) -> Unit = {}) {
        if (!keepsRecording(s)) { done(false); return }
        val file = s.file!!
        viewModelScope.launch {
            // A keep that fails leaves the recording where it was, and the source as it was: nothing says it is kept.
            val kept = withContext(storage) {
                runCatching { keptStore.keep(file, s.name, s.kind, s.durationS) }
                    .onFailure { android.util.Log.w(TAG, "the recording could not be kept", it) }.getOrNull()
            }
            if (kept != null) {
                // Still the recording in hand: it is the kept file from now on (the cache's copy is gone).
                if (source.value?.file == file && kept.file != file) source.value = source.value?.copy(file = kept.file)
                refreshKept()
            }
            done(kept != null)
        }
    }

    /** Whether [s] is a recording this app keeps in Your scores: a take or an import of its own, not a score's. */
    private fun keepsRecording(s: Source): Boolean {
        if (!Product.KEEPS_RECORDINGS || s.kind == SourceKind.SCORE) return false
        val file = s.file ?: return false
        val ours = file.parentFile?.canonicalFile == takesDir.canonicalFile || keptStore.owns(file)
        return ours && file != CaptureController.activeFile()
    }

    /** The recording [s] has a score now: it leaves Your scores. Its file stays while it is the recording in hand. */
    private fun forgetKept(s: Source) {
        val file = s.file ?: return
        viewModelScope.launch {
            val forgot = withContext(storage) { keptStore.entryOf(file)?.also { keptStore.forget(it.id) } }
            if (forgot != null) refreshKept()
        }
    }

    private fun refreshKept() {
        if (!Product.KEEPS_RECORDINGS) return
        viewModelScope.launch {
            val (list, bytes) = withContext(storage) { keptStore.list().let { it to it.sumOf { k -> k.file.length() } } }
            keptRecordings.value = list
            keptBytes.value = bytes
        }
    }

    /** Opens a kept recording in What is this?, as it was when it was kept. */
    fun openKept(k: KeptRecording) {
        val ctx = getApplication<Application>()
        busy.value = true
        viewModelScope.launch {
            try {
                // Read where it is: it is the app's own file already, so nothing is copied.
                val decoded = withContext(Dispatchers.IO) {
                    check(k.file.isFile) { "the recording is gone" }
                    no.brasscribe.play.audio.AudioDecoder.decode(ctx, Uri.fromFile(k.file), {})
                }
                setSource(Source(k.title, k.kind, decoded.durationS, decoded.audio, k.file))
                say(R.string.imported, k.title, durationText(decoded.durationS))
                navigate(Screen.PROFILE)
            } catch (e: OutOfMemoryError) {
                showProblem(Problem.TOO_LARGE, e.toString())
            } catch (e: Exception) {
                showProblem(Problem.FILE_UNREADABLE, e.message ?: e.toString())
            } finally {
                busy.value = false
            }
        }
    }

    /** Deletes a kept recording: it leaves Your scores, and its file is removed from the phone. */
    fun deleteKept(k: KeptRecording) {
        if (source.value?.file == k.file) source.value = null
        viewModelScope.launch {
            withContext(storage) { keptStore.delete(k.id) }
            refreshKept()
        }
    }

    // ---- Review ---------------------------------------------------------------------------------------

    /** Where Check the notes was left for each score while the app runs, by the saved score's id. */
    private val reviewPlaces = HashMap<String, ReviewPlace>()

    /** A "?" tapped on the score, for Check the notes to open at; taken once. */
    private var reviewTarget: ReviewTarget? = null

    /** Where Check the notes was left for the score on screen: Check them comes back to it. */
    fun reviewPlace(): ReviewPlace? = currentSavedScoreId?.let { reviewPlaces[it] }

    fun keepReviewPlace(place: ReviewPlace) {
        currentSavedScoreId?.let { reviewPlaces[it] = place }
    }

    /** Opens Check the notes at the "?" the player tapped on the score. */
    fun checkAt(target: ReviewTarget) {
        reviewTarget = target
        navigate(Screen.REVIEW)
    }

    fun takeReviewTarget(): ReviewTarget? = reviewTarget.also { reviewTarget = null }

    /**
     * Saves [r] as the score on screen. What it is saved with is taken now; the writing happens off the
     * main thread, in order with every other save.
     */
    private fun saveCurrentScore(r: TranscriptionResult, title: String? = null) {
        val scoreTitle = title?.takeIf(String::isNotBlank)
            ?: r.composition?.title?.takeIf(String::isNotBlank)
            ?: source.value?.name?.let(ScoreTitles::withoutExtension)
            ?: res.getString(R.string.score_title)
        // The id is fixed before the write, so a second save of a new score does not make a second copy.
        val id = currentSavedScoreId ?: java.util.UUID.randomUUID().toString().also { currentSavedScoreId = it }
        val checkedNow = checked.value.flatMap { (voice, events) -> events.map { "$voice:$it" } }.toSet()
        val part = myPartOverride.value
        val noticeSeen = mappedNoticeSeen.value
        val changes = reviewChanges.value
        // A draft keeps its recording for "Make the full score" (copied on its first save).
        val recording = if (r.draft) source.value?.file else null
        viewModelScope.launch {
            val list = withContext(storage) {
                runCatching {
                    scoreLibrary.save(id, scoreTitle, r.profile.id, r.musicXml, r.compositionJsonFor(container.core),
                        jobId = r.jobId, evidenceJson = r.evidence?.let { no.brasscribe.play.model.BrasscribeJson.encodeToString(no.brasscribe.play.engine.Evidence.serializer(), it) },
                        checked = checkedNow, part = part, noticeSeen = noticeSeen, changedOnPhone = r.changedOnPhone, reviewChanges = changes,
                        draft = r.draft, recording = recording)
                }.onFailure { android.util.Log.w(TAG, "score not saved", it) }
                scoreLibrary.list()
            }
            savedScores.value = list
        }
    }

    /**
     * A tap on "ready": the score or tab [jobId] made. Nothing when it is on screen already, or when the transcribing
     * screen is still following it (it moves on by itself); else the one saved on the phone, or the computer's.
     */
    fun openFinishedJob(jobId: String) {
        val top = backStack.value.last()
        if (top == Screen.TRANSCRIBE && engineJobId == jobId) return
        if (result.value?.jobId == jobId && top in setOf(Screen.SCORE, Screen.REVIEW, Screen.OUTPUT)) return
        viewModelScope.launch {
            val saved = withContext(storage) { scoreLibrary.list() }.firstOrNull { it.jobId == jobId }
            if (saved != null) { home(); openSavedScore(saved); return@launch }
            val engine = container.engine() ?: return@launch
            val done = runCatching { engine.job(jobId) }.getOrNull() ?: return@launch
            val entry = ScoreEntry.merge(emptyList(), listOf(done)).firstOrNull() ?: return@launch
            home()
            openEntry(entry)
        }
    }

    /** Fetch the computer's finished scores; keeps the phone's list when the computer can't be reached. */
    fun refreshComputerScores() {
        val engine = container.engine()?.takeIf { !container.usingFixture } ?: run { computerJobs.value = emptyList(); return }
        viewModelScope.launch { runCatching { engine.jobs() }.onSuccess { computerJobs.value = it } }
    }

    fun openEntry(entry: ScoreEntry, review: Boolean = false, stand: Boolean = false) {
        val opening = entry.opening(review, stand, Product::makes)
        // The computer's list also holds what the other app made: that opens there, not here, and leaves nothing behind.
        if (!opening.here) { opensElsewhere.value = entry.id to (opensElsewhere.value?.second ?: 0) + 1; say(R.string.other_product_opens); return }
        standFromLibrary.value = opening.standFor
        entry.saved?.let { openSavedScore(it, review); return }
        val jobId = entry.jobId ?: return
        val engine = container.engine() ?: return
        openingScore.value = entry.id
        viewModelScope.launch {
            try {
                val job = engine.job(jobId)
                val r = TranscriptionResult(engine.composition(jobId), engine.musicXml(jobId),
                    Profile.of(job.profile) ?: Profile.BRASS_BAND, onDevice = false, jobId = jobId, audioId = job.audioId,
                    engineOutputs = job.outputs.toSet(), evidence = runCatching { engine.evidence(jobId) }.getOrNull())
                source.value = Source(entry.title, SourceKind.SCORE, 0.0)
                currentSavedScoreId = null
                myPartOverride.value = null
                mappedNoticeSeen.value = false
                checked.value = emptyMap()
                reviewChanges.value = emptyMap()
                result.value = r
                saveCurrentScore(r, entry.title)
                backStack.value = opened(review)
            } catch (e: Exception) {
                // A connection or engine failure is no unreadable file: its own words, not "try an MP3".
                val why = ErrorWords.of(e).takeIf { it != R.string.error_generic }
                showProblem(if (why != null) Problem.SCORE_FAILED else Problem.FILE_UNREADABLE, e.message, why)
            } finally {
                openingScore.value = null
            }
        }
    }

    fun renameEntry(entry: ScoreEntry, title: String) {
        val cleaned = title.trim()
        if (cleaned.isEmpty()) return
        entry.saved?.let { renameSavedScore(it.id, cleaned); return }
        val jobId = entry.jobId ?: return
        viewModelScope.launch {
            runCatching { container.engine()?.renameRun(jobId, cleaned) }
            refreshComputerScores()
        }
    }

    fun deleteEntry(entry: ScoreEntry) {
        entry.saved?.let { saved ->
            if (currentSavedScoreId == saved.id) currentSavedScoreId = null
            practiceLeft.remove(saved.id)
            viewModelScope.launch {
                savedScores.value = withContext(storage) { scoreLibrary.delete(saved.id); practicePlaces.forget(saved.id); scoreLibrary.list() }
            }
            return
        }
        val jobId = entry.jobId ?: return
        viewModelScope.launch {
            runCatching { container.engine()?.deleteRun(jobId) }
            refreshComputerScores()
        }
    }

    /** Opens a score from "Your scores": it is read (off the main thread) and then shown. */
    fun openSavedScore(saved: SavedScore, review: Boolean = false) {
        openingScore.value = saved.id
        viewModelScope.launch {
            try {
                // Its latest details too: a save may have been waiting when the list was drawn.
                val (latest, content) = withContext(storage) { (scoreLibrary.get(saved.id) ?: saved) to scoreLibrary.content(saved.id) }
                if (content == null) { showProblem(Problem.FILE_UNREADABLE, saved.title); return@launch }
                showSaved(latest, content)
                backStack.value = opened(review)
            } finally {
                openingScore.value = null
            }
        }
    }

    /** Makes [saved] the score on screen. */
    private fun showSaved(saved: SavedScore, content: SavedScoreContent, recording: Source? = null) {
        currentSavedScoreId = saved.id
        myPartOverride.value = saved.part
        mappedNoticeSeen.value = saved.noticeSeen
        source.value = recording ?: Source(saved.title, SourceKind.SCORE, 0.0)
        reviewChanges.value = saved.reviewChanges
        result.value = TranscriptionResult(
            composition = content.compositionJson?.let { runCatching { container.core.decodeComposition(it) }.getOrNull() },
            musicXml = content.musicXml,
            profile = Profile.entries.firstOrNull { it.id == saved.profile } ?: Profile.BRASS_BAND,
            onDevice = saved.jobId == null,
            jobId = saved.jobId,
            compositionJson = content.compositionJson,
            evidence = content.evidenceJson?.let {
                runCatching { no.brasscribe.play.model.BrasscribeJson.decodeFromString(no.brasscribe.play.engine.Evidence.serializer(), it) }.getOrNull()
            },
            changedOnPhone = saved.changedOnPhone,
            draft = saved.draft,
        )
        checked.value = saved.checked.mapNotNull { key ->
            key.substringAfterLast(':').toIntOrNull()?.let { key.substringBeforeLast(':') to it }
        }.groupBy({ it.first }, { it.second }).mapValues { it.value.toSet() }
    }

    private fun renameSavedScore(id: String, title: String) {
        val cleaned = title.trim()
        if (cleaned.isEmpty()) return
        viewModelScope.launch {
            val renamed = withContext(storage) {
                runCatching {
                    val saved = scoreLibrary.get(id) ?: return@runCatching null
                    val content = scoreLibrary.content(id) ?: return@runCatching null
                    val composition = content.compositionJson?.let { container.core.decodeComposition(it).copy(title = cleaned) }
                    val compositionJson = composition?.let(container.core::encodeComposition)
                    val xml = MusicXmlTitleEditor.replaceTitle(content.musicXml, cleaned)
                    scoreLibrary.save(id, cleaned, saved.profile, xml, compositionJson, saved.jobId, content.evidenceJson, saved.checked, saved.part, saved.noticeSeen, saved.changedOnPhone, saved.reviewChanges, saved.draft)
                    Triple(saved.jobId, composition to compositionJson, xml)
                }.onFailure { android.util.Log.w(TAG, "score not renamed", it) }.getOrNull()
            }
            savedScores.value = withContext(storage) { scoreLibrary.list() }
            val (job, composition, xml) = renamed ?: return@launch
            job?.let { runCatching { container.engine()?.renameRun(it, cleaned) } }
            if (currentSavedScoreId == id) {
                result.value = result.value?.copy(composition = composition.first, musicXml = xml, compositionJson = composition.second)
                source.value = source.value?.copy(name = cleaned)
            }
        }
    }

    /**
     * The score with the note at [start] moved from [pitch] by [semitones], arranged as Save writes it: the
     * Composition and the MusicXML. Nothing is kept; null when the note is not there or the score can't be written.
     */
    private fun changedScore(current: TranscriptionResult, voiceId: String, start: Int, pitch: Int, semitones: Int): Pair<Composition, String>? {
        val composition = current.composition ?: return null
        val voice = composition.voice(voiceId) ?: return null
        val noteIndex = voice.notes.indexOfFirst { it.start == start && it.pitch == pitch }
        if (noteIndex < 0) return null
        val updatedVoice = voice.copy(notes = voice.notes.mapIndexed { index, note ->
            if (index == noteIndex) note.copy(pitch = (note.pitch + semitones).coerceIn(0, 127)) else note
        })
        val updatedComposition = composition.copy(voices = composition.voices.map { if (it.id == voiceId) updatedVoice else it })
        val parts = updatedComposition.voices.map { v ->
            val name = when (v.id) { "solo" -> "Solo Cornet"; "brass" -> "Brass"; "strings" -> "Strings"; "bass" -> "Bass"; "drums" -> "Drums"; else -> v.id }
            PartSpec(v.id, name, if (v.role == VoiceRole.MELODY) Instrument.CORNET else Instrument.CONCERT)
        }
        // The same lineup and difficulty as the score came from (the golden Composition re-arranges to the
        // golden score), and no new transposition: the recorded total is passed back.
        val options = OutputOptions(
            lineup = current.lineup ?: output.value.lineup,
            difficulty = Difficulty.of(current.arrangementText("difficulty")) ?: output.value.difficulty,
            // Whoever the score was written for, as recorded: a change in Settings never re-arranges it.
            seat = composition.arrangementString("seat"), reads = composition.arrangementString("reads"),
            lead = composition.arrangementString("lead")?.takeIf { !current.isSoloTake },
        )
        val arranged = runCatching { arrangeComposition(updatedComposition, options, current.isSoloTake) }.getOrNull()
        val xml = arranged?.second
            ?: runCatching { container.core.toMusicXml(updatedComposition, parts) }.getOrNull()
            ?: return null
        return (arranged?.first ?: updatedComposition) to xml
    }

    /** A note is being changed: the score is arranged again in the background, and Save waits for it. */
    val changingNote = MutableStateFlow(false)

    /**
     * Moves the note and arranges the score again, off the main thread (the core's arranger takes a
     * moment on a full band). Once done, and only if the score on screen is still the one it started
     * from, [changes] become the Review changes, the score is shown and saved, and [onDone] hears true.
     */
    private fun correctNote(voiceId: String, start: Int, pitch: Int, semitones: Int, changes: Map<String, Int>, onDone: (Boolean) -> Unit) {
        val current = result.value ?: return onDone(false)
        if (changingNote.value) return onDone(false)
        changingNote.value = true
        viewModelScope.launch {
            val updated = try {
                withContext(Dispatchers.Default) {
                    val (finalComposition, xml) = changedScore(current, voiceId, start, pitch, semitones) ?: return@withContext null
                    val newPitch = (pitch + semitones).coerceIn(0, 127)
                    // The evidence follows the note: the musician's pitch is now the written one each transcriber is compared to.
                    val evidence = current.evidence?.let { e ->
                        e.copy(notes = e.notes.map { n ->
                            if (n.voice == voiceId && n.start == start && n.pitch == pitch)
                                n.copy(pitch = newPitch, models = n.models.map { it.copy(agrees = it.pitch == newPitch) }) else n
                        })
                    }
                    current.copy(composition = finalComposition, musicXml = xml,
                        compositionJson = container.core.encodeComposition(finalComposition), evidence = evidence, changedOnPhone = true)
                }
            } finally {
                changingNote.value = false
            }
            if (updated == null || result.value !== current) { onDone(false); return@launch }
            reviewChanges.value = changes
            result.value = updated
            saveCurrentScore(updated)
            onDone(true)
        }
    }

    /**
     * [composition] arranged by the core for [options]' lineup and difficulty, with no new transposition
     * (the recorded total goes back in). Returns the Composition with its arrangement recorded as the
     * core made it, and the MusicXML; null without the core.
     */
    private fun arrangeComposition(composition: Composition, options: OutputOptions, soloTake: Boolean): Pair<Composition, String>? {
        val transposed = (composition.arrangement?.get("transpose_semitones") as? kotlinx.serialization.json.JsonPrimitive)?.content?.toIntOrNull()
        val lineup = options.lineup.madeFor(composition.fullBandMade)
        val core = options.toCore().copy(lineup = lineup.core)
        val xml = container.core.arrangeMusicXmlWith(composition, core.copy(transpose = transposed)) ?: return null
        return composition.arrangedFor(lineup, options.difficulty.id, core.seat, core.reads, core.lead, soloTake) to xml
    }

    /** A score arranged on the phone, re-arranged from its Composition (the rest of a key shift stays display-only). */
    private fun rearrange(r: TranscriptionResult, opts: OutputOptions): TranscriptionResult? {
        val (composition, xml) = arrangeComposition(r.composition ?: return null, opts, r.isSoloTake) ?: return null
        return r.copy(composition = composition, musicXml = xml, compositionJson = container.core.encodeComposition(composition))
    }

    /**
     * Notes changed in Review ("Change note…" → Save), by [changeKey]: the pitch Brasscribe wrote. A
     * changed note stays open until it is kept, so it can be listened to, changed again or undone.
     */
    val reviewChanges = MutableStateFlow<Map<String, Int>>(emptyMap())

    fun changeKey(voiceId: String, start: Int) = "$voiceId@$start"

    /**
     * Review's Save: the note at [start] moves from [pitch] by [semitones], is written to the score
     * and stays open. Moving it back to what Brasscribe wrote clears the change.
     */
    fun changeReviewNote(voiceId: String, start: Int, pitch: Int, semitones: Int, onDone: (Boolean) -> Unit = {}) {
        if (semitones == 0) return onDone(false)
        val key = changeKey(voiceId, start)
        val was = reviewChanges.value[key] ?: pitch
        stopListening(announce = false)
        val now = (pitch + semitones).coerceIn(0, 127)
        val changes = reviewChanges.value.let { if (now == was) it - key else it + (key to was) }
        correctNote(voiceId, start, pitch, semitones, changes, onDone)
    }

    /** Review's "Undo change": the note at [start], now [pitch], goes back to what Brasscribe wrote. */
    fun undoReviewChange(voiceId: String, start: Int, pitch: Int, onDone: (Boolean) -> Unit = {}) {
        val key = changeKey(voiceId, start)
        val was = reviewChanges.value[key] ?: return onDone(false)
        stopListening(announce = false)
        val changes = reviewChanges.value - key
        if (was == pitch) {
            reviewChanges.value = changes
            result.value?.let(::saveCurrentScore)
            return onDone(true)
        }
        correctNote(voiceId, start, pitch, was - pitch, changes, onDone)
    }

    /** Keeps several notes at once ("Keep the rest of this bar"). */
    fun markCheckedAll(voiceId: String, indexes: Collection<Int>, remaining: Int) {
        checked.update { it + (voiceId to (it[voiceId].orEmpty() + indexes)) }
        result.value?.let(::saveCurrentScore)
        say(R.string.checked_left, remaining)
    }

    fun markChecked(voiceId: String, index: Int, remaining: Int) {
        checked.update { it + (voiceId to (it[voiceId].orEmpty() + index)) }
        result.value?.let(::saveCurrentScore)
        say(R.string.checked_left, remaining)
    }

    /**
     * Plays the recording's bar, then the score's bar, once; pressing it again while that bar plays stops
     * it (the button reads Stop meanwhile).
     */
    fun listenToBar(bar: Int) {
        val r = result.value ?: return
        val composition = r.composition ?: return
        listening.toggle(bar) {
            val map = TickMap(composition)
            val original = source.value?.audio?.let { a ->
                val span = map.barSeconds(bar)
                // at the band's loudness: the whole recording measured once (off the main thread)
                withContext(Dispatchers.Default) { recordingLevel.slice(a, span.start, span.endInclusive, r.musicXml) }
            }
            val score = scoreBarAudio(r, map, bar)
            BarListening.Clips(listOfNotNull(original, score), withRecording = original != null)
        }
    }

    private suspend fun scoreBarAudio(r: TranscriptionResult, map: TickMap, bar: Int): PcmAudio? {
        // A note changed on the phone is not in the engine's render: the bar is rendered here, with the new note.
        if (r.changedOnPhone) return withContext(Dispatchers.Default) {
            runCatching { no.brasscribe.play.score.BarAudio.render(getApplication(), r.musicXml, bar) }
                .onFailure { android.util.Log.w("BrasscribePlay", "bar $bar not rendered on the phone", it) }.getOrNull()
        }
        val jobId = r.jobId ?: return null
        val rendered = renderedScoreAudio?.takeIf { it.first == jobId }?.second ?: withContext(Dispatchers.IO) {
            val f = File(getApplication<Application>().cacheDir, "score-$jobId.mp3")
            try {
                runCatching {
                    val bytes = container.engine()?.renderedAudio(jobId) ?: return@runCatching null
                    f.writeBytes(bytes)
                    AudioDecoder.decode(getApplication(), Uri.fromFile(f)).audio
                }.getOrNull()
            } finally {
                // Only needed to decode it: the samples are kept, not the file.
                f.delete()
            }
        }?.also { renderedScoreAudio = jobId to it } ?: return null
        // The rendered score starts at bar 1 and runs at the score's tempo.
        val comp = r.composition ?: return null
        val secondsPerTick = 60.0 / comp.bpm / comp.ticksPerBeat
        val from = maxOf(0, map.barStart(bar)) * secondsPerTick
        val to = map.barEnd(bar) * secondsPerTick
        // the engine's render is mastered hot: it plays at the same loudness as the recording
        return withContext(Dispatchers.Default) { renderedLevel.slice(rendered, from, to, r.musicXml) }
    }

    /**
     * Change note…'s "Play the bar with this note": [bar] with the note at [start] moved from [pitch] by
     * [semitones], before it is saved. It is arranged as Save would write it and rendered on the phone (the
     * band SoundFont's subset for the bar, [no.brasscribe.play.score.BarAudio]); nothing is kept. Pressing it
     * again while it plays stops it.
     */
    fun previewNote(bar: Int, voiceId: String, start: Int, pitch: Int, semitones: Int) {
        val current = result.value ?: return
        listening.toggle(bar) {
            val audio = withContext(Dispatchers.Default) {
                val xml = if (semitones == 0) current.musicXml else changedScore(current, voiceId, start, pitch, semitones)?.second
                lastPreviewXml = xml
                xml?.let { x ->
                    runCatching { no.brasscribe.play.score.BarAudio.render(getApplication(), x, bar) }
                        .onFailure { android.util.Log.w("BrasscribePlay", "bar $bar not rendered for the preview", it) }.getOrNull()
                }
            }
            BarListening.Clips(listOfNotNull(audio), withRecording = false)
        }
    }

    /** The score the last preview played (tests check it has the candidate). */
    @androidx.annotation.VisibleForTesting
    @Volatile internal var lastPreviewXml: String? = null

    fun stopListening(announce: Boolean = true) = listening.stop(announce)

    // ---- Companion ------------------------------------------------------------------------------------

    /** The engine's name in this language: "Brasscribe on Kari's Mac" / "Brasscribe på Kari's Mac". */
    fun serverDisplayName(serverName: String): String =
        ServerNames.display(serverName, { res.getString(R.string.server_name_format, it) }, res.getString(R.string.companion_title))

    /**
     * Connects to the engine at [url]. A credential this phone already holds for that engine is checked
     * first (GET /v1/devices/me); the code is only used when there is none, or the engine answers 401.
     */
    fun connect(url: String, code: String) {
        pendingLink.value = null
        askAgain.value = null
        companionState.value = res.getString(R.string.companion_connecting)
        viewModelScope.launch {
            try {
                val done = container.newEngineClient(url).use { client -> connectTo(client, url, client.health(), code) }
                if (!done) companionState.value = res.getString(R.string.pair_code_needed)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                failed(e)
            }
        }
    }

    /** A pairing link from a QR code or brasscribe://pair: shown on the connection screen, connected on Connect. */
    fun openPairLink(text: String): Boolean {
        val link = PairLink.parse(text)
        if (link == null) {
            say(R.string.pair_link_invalid)
            return false
        }
        pendingLink.value = link
        companionState.value = null
        if (backStack.value.last() != Screen.COMPANION) navigate(Screen.COMPANION)
        return true
    }

    /**
     * Tries the link's addresses in order (or the address mDNS gives for its server id) and pairs only
     * with the engine whose id matches. Without a code, the computer is asked to allow this phone.
     */
    fun pairWithLink(link: PairLink) {
        // A pinned certificate needs TLS, which this version does not speak yet: never fall back to plain HTTP.
        if (link.fingerprint != null) {
            companionState.value = res.getString(R.string.pair_needs_update)
            say(R.string.pair_needs_update)
            return
        }
        askAgain.value = null
        companionState.value = res.getString(R.string.companion_connecting)
        viewModelScope.launch {
            val urls = link.urls.ifEmpty { listOfNotNull(container.reconnectDiscovery.find(link.serverId)) }
            for (url in urls) {
                val client = container.newEngineClient(url)
                try {
                    val health = client.health()
                    if (health.serverId != link.serverId) continue
                    pendingLink.value = null
                    if (!connectTo(client, url, health, link.code.orEmpty())) askComputer(url)
                    return@launch
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (e: EngineException) {
                    if (e.status != 0) { failed(e); return@launch }
                } catch (e: Exception) {
                    // Not reachable at this address: try the next one.
                } finally {
                    client.close()
                }
            }
            companionState.value = res.getString(R.string.pair_link_unreachable, serverDisplayName(link.serverName))
        }
    }

    /**
     * Uses a credential this phone already holds for the engine, or pairs with [code]. False when there is
     * neither a valid credential nor a code.
     */
    private suspend fun connectTo(client: KtorEngineApi, url: String, health: no.brasscribe.play.engine.Health, code: String): Boolean {
        val store = container.credentials
        // Only this phone itself or the emulator's host is let in without pairing; any other address that
        // says so pairs all the same.
        if (!health.authRequired && no.brasscribe.play.engine.LocalHosts.hostOf(url)?.let(no.brasscribe.play.engine.LocalHosts::isTrusted) == true) {
            connected(url, health.serverId, health.serverName)
            return true
        }
        // A token from an earlier version belongs to the address it was used with.
        store.get(CredentialStore.LEGACY_ID)?.takeIf { it.lastAddress == url }?.let { store.adopt(health.serverId, health.serverName) }
        // A credential goes only to the address it was paired at: at another one, this phone pairs again.
        val held = store.get(health.serverId)?.takeIf { it.mayBeSentTo(url) }
        if (held != null) {
            client.token = held.token
            val valid = try { client.thisDevice(); true } catch (e: EngineException) { if (e.status == 401) false else throw e }
            if (valid) {
                store.put(held.copy(lastAddress = url, serverName = health.serverName))
                connected(url, health.serverId, health.serverName)
                return true
            }
            store.remove(health.serverId)
            client.token = null
        }
        if (code.isBlank()) return false
        val r = client.pair(code.trim(), container.deviceName)
        store.put(Credential(r.serverId, r.token, r.deviceId, r.serverName, url))
        connected(url, r.serverId, r.serverName)
        return true
    }

    private fun connected(url: String, serverId: String, serverName: String) {
        val s = container.settings
        s.url = url
        s.serverId = serverId
        s.serverName = serverName
        s.paired = true
        companionState.value = null
        askAgain.value = null
        sayText(res.getString(R.string.conn_connected, serverDisplayName(serverName)))
        connection.retry()
        refreshComputerScores()
    }

    private fun failed(e: Exception) {
        // The reason goes to the log and the tech details, never into the sentence.
        android.util.Log.w(TAG, "connect failed", e)
        lastConnectError = e.message ?: e.javaClass.simpleName
        val text = when ((e as? EngineException)?.status) {
            403 -> res.getString(R.string.pair_code_wrong)
            429 -> res.getString(R.string.pair_code_locked)
            else -> res.getString(R.string.companion_failed_plain)
        }
        // Shown on the connection screen already: heard, not shown twice.
        companionState.value = text
        status.value = Status(text, quiet = true)
    }

    /** What went wrong last time, for the tech details. */
    var lastConnectError: String? = null
        private set

    /** Pairing without a code: the computer shows "Allow <phone>?" with [matchCode]; this waits for the answer. */
    fun askComputer(url: String) {
        askJob?.cancel()
        pendingLink.value = null
        askAgain.value = null
        companionState.value = res.getString(R.string.companion_connecting)
        askJob = viewModelScope.launch {
            val client = container.newEngineClient(url)
            try {
                val health = client.health()
                if (connectTo(client, url, health, "")) return@launch
                val info = client.requestPairing(container.deviceName)
                matchCode.value = info.matchCode
                companionState.value = null
                sayQuietly(R.string.pair_ask_waiting_spoken, info.matchCode.toList().joinToString(" "))
                val until = System.currentTimeMillis() + ASK_TIMEOUT_MS
                while (System.currentTimeMillis() < until) {
                    delay(ASK_POLL_MS)
                    val r = try { client.pollPairingRequest(info.requestId) } catch (e: EngineException) {
                        if (e.status == 404) break
                        if (e.status == 0) continue else throw e
                    } catch (e: java.io.IOException) {
                        // A moment without Wi-Fi does not end the wait: the computer is asked again next time.
                        android.util.Log.i(TAG, "pairing request poll: $e")
                        continue
                    }
                    when (r.status) {
                        "approved" -> {
                            val token = r.token ?: break
                            val serverId = r.serverId ?: health.serverId
                            val name = r.serverName ?: health.serverName
                            container.credentials.put(Credential(serverId, token, r.deviceId, name, url))
                            matchCode.value = null
                            connected(url, serverId, name)
                            return@launch
                        }
                        "denied" -> {
                            matchCode.value = null
                            askAgain.value = url
                            companionState.value = res.getString(R.string.pair_ask_denied)
                            sayQuietly(R.string.pair_ask_denied)
                            return@launch
                        }
                    }
                }
                matchCode.value = null
                askAgain.value = url
                companionState.value = res.getString(R.string.pair_ask_expired)
                sayQuietly(R.string.pair_ask_expired)
            } catch (e: kotlinx.coroutines.CancellationException) {
                matchCode.value = null
                throw e
            } catch (e: Exception) {
                matchCode.value = null
                failed(e)
            } finally {
                client.close()
            }
        }
    }

    fun cancelAsk() {
        askJob?.cancel()
        askJob = null
        matchCode.value = null
    }

    /** Removes this phone from the computer's list and forgets the credential. */
    fun unpair() {
        val s = container.settings
        val id = s.serverId ?: CredentialStore.LEGACY_ID
        val token = s.token
        val url = s.url
        viewModelScope.launch {
            if (token != null) runCatching { container.newEngineClient(url, token).use { it.unpairThisDevice() } }
            container.credentials.remove(id)
            s.paired = false
            companionState.value = null
            say(R.string.pair_forgotten)
            connection.retry()
            refreshComputerScores()
        }
    }

    override fun onCleared() {
        listening.stop(announce = false)
    }

    /** How long the transcribing screen waits between asking the computer for a job whose events stopped (tests shorten it). */
    @androidx.annotation.VisibleForTesting
    internal var followPause = 3_000L

    companion object {
        const val TAG = "BrasscribePlay"

        /** A job whose events stopped is asked for this many times in a row without an answer before it counts as failed. */
        const val FOLLOW_TRIES = 40

        /** A MusicXML score larger than this is not a score. */
        const val MAX_SCORE_BYTES = 64L shl 20

        /** A recorded WAV up to this size (about 9 minutes of mono 44.1 kHz) also goes to the core as bytes. */
        const val MAX_CORE_WAV_BYTES = 48L shl 20

        /**
         * True when [e] is, or was caused by, running out of memory. HTTP clients report a failure
         * while writing the body as an IOException with the real error as its cause or suppressed.
         */
        fun isTooLarge(e: Throwable): Boolean {
            val seen = HashSet<Throwable>()
            fun walk(t: Throwable?): Boolean {
                if (t == null || !seen.add(t)) return false
                if (t is OutOfMemoryError) return true
                val m = t.message.orEmpty()
                if ("OutOfMemoryError" in m || ("Failed to allocate" in m && "until OOM" in m)) return true
                return walk(t.cause) || t.suppressed.any { walk(it) }
            }
            return walk(e)
        }

        /** Reads at most [limit] bytes; more is an error, not a truncated file. */
        fun readLimited(input: java.io.InputStream, limit: Long): ByteArray {
            val out = java.io.ByteArrayOutputStream()
            val buf = ByteArray(1 shl 16)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                out.write(buf, 0, n)
                require(out.size() <= limit) { "file larger than ${limit shr 20} MB" }
            }
            return out.toByteArray()
        }
        private const val KEY_STACK = "stack"
        private const val KEY_SOURCE = "source"
        private const val KEY_SCORE = "score"
        private const val KEY_DRAFT_BEHIND = "draftBehind"
        const val ASK_POLL_MS = 2_000L
        /** The engine forgets a pairing request after two minutes. */
        const val ASK_TIMEOUT_MS = 125_000L
        const val SOLO_PART_NAME = "Solo Cornet"
        /** Opened as a score, never sent through a transcription profile. */
        val SCORE_EXTENSIONS = setOf("musicxml", "mxl", "xml")
    }
}
