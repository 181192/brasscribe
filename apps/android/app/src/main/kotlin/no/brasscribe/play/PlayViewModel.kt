package no.brasscribe.play

import android.app.Application
import android.net.Uri
import android.provider.OpenableColumns
import androidx.annotation.StringRes
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.brasscribe.play.audio.AudioDecoder
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.audio.UnsupportedMediaException
import no.brasscribe.play.audio.WavFile
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.JobStatus
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.engine.ProgressTracker
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.Instrument
import no.brasscribe.play.model.MusicXmlTitleEditor
import no.brasscribe.play.model.PartSpec
import no.brasscribe.play.model.TickMap
import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.TempoEstimator
import no.brasscribe.play.model.VoiceRole
import no.brasscribe.play.playback.ClipPlayer
import java.io.File
import java.util.zip.ZipInputStream

enum class Screen { FIRST_RUN, HOME, RECORD, PROFILE, TRANSCRIBE, REVIEW, OUTPUT, SCORE, EXPORT, COMPANION, ABOUT, SETTINGS, PROBLEM, HELP }

/** Something went wrong that the user has to act on: shown full screen with a way forward. */
enum class Problem { FILE_UNREADABLE, NO_SOUND_TRACK, NOTHING_HEARD, RECORDING_FAILED, SCORE_FAILED }

enum class SourceKind { FILE, VIDEO, MICROPHONE, DEVICE, SAMPLE, SCORE }

/** What the user brought in. [file] holds the bytes sent to the engine; [audio] is decoded mono PCM. */
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
)

/** What the core wants beside the MusicXML: null is fine, and is all an opened score can give. */
fun TranscriptionResult.compositionJsonFor(core: no.brasscribe.play.model.CoreBridge): String? =
    compositionJson ?: composition?.let { runCatching { core.encodeComposition(it) }.getOrNull() }


enum class Lineup(@StringRes val label: Int, @StringRes val desc: Int) {
    FULL(R.string.lineup_full, R.string.lineup_full_desc), MINIMAL(R.string.lineup_minimal, R.string.lineup_minimal_desc),
    SOLO(R.string.lineup_solo, R.string.lineup_solo_desc),
}
enum class Difficulty(@StringRes val label: Int) { FAITHFUL(R.string.difficulty_faithful), STANDARD(R.string.difficulty_standard), EASIER(R.string.difficulty_easier) }

data class OutputOptions(val lineup: Lineup = Lineup.FULL, val difficulty: Difficulty = Difficulty.FAITHFUL, val keyShift: Int = 0) {
    fun toCore() = ArrangeOptions(
        lineup = if (lineup == Lineup.MINIMAL) "minimal" else "full",
        difficulty = difficulty.name.lowercase(),
        transpose = keyShift.takeIf { it != 0 },
    )
}

/** A status line for sighted users that screen readers also hear (polite live region). */
data class Status(val text: String, val serial: Long = System.nanoTime())

class PlayViewModel(app: Application) : AndroidViewModel(app) {
    val container = (app as PlayApplication).container
    private val res = app.resources
    private val scoreLibrary = SavedScoreLibrary(File(app.filesDir, "scores"))
    val savedScores = MutableStateFlow(scoreLibrary.list())
    private val computerJobs = MutableStateFlow<List<no.brasscribe.play.engine.Job>>(emptyList())
    /** "Your scores": this phone's scores and the computer's latest finished ones, newest first. */
    val scores: StateFlow<List<ScoreEntry>> = kotlinx.coroutines.flow.combine(savedScores, computerJobs) { local, jobs ->
        ScoreEntry.merge(local, jobs)
    }.stateIn(viewModelScope, kotlinx.coroutines.flow.SharingStarted.Eagerly, ScoreEntry.merge(scoreLibrary.list(), emptyList()))
    val openingScore = MutableStateFlow<String?>(null)
    private var currentSavedScoreId: String? = null

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
    val companionState = MutableStateFlow<String?>(null)
    val clipPlaying = MutableStateFlow<Int?>(null)
    val problem = MutableStateFlow<Problem?>(null)
    /** The detail of the last problem (an engine message), shown under the reasons. */
    var problemDetail: String? = null
        private set

    /** Set while the score screen is open: MIDI export and "Play this bar" go through it. */
    var scoreController: no.brasscribe.play.score.ScoreController? = null

    private var job: Job? = null
    private var engineJobId: String? = null
    private val clips = ClipPlayer()
    private var renderedScoreAudio: PcmAudio? = null

    fun navigate(to: Screen) = backStack.update { it + to }
    fun replaceTop(to: Screen) = backStack.update { it.dropLast(1) + to }
    fun back(): Boolean {
        if (backStack.value.size <= 1) return false
        if (backStack.value.last() == Screen.TRANSCRIBE) cancelTranscription()
        backStack.update { it.dropLast(1) }
        return true
    }

    fun home() { backStack.value = listOf(Screen.HOME) }

    fun finishFirstRun() {
        container.firstRunDone = true
        backStack.value = listOf(Screen.HOME)
    }

    /** Shows [p] full screen, replacing the step that failed (the recording is kept). */
    fun showProblem(p: Problem, detail: String? = null) {
        problem.value = p
        problemDetail = detail
        backStack.update { (if (it.last() in setOf(Screen.TRANSCRIBE, Screen.RECORD)) it.dropLast(1) else it) + Screen.PROBLEM }
    }

    fun say(@StringRes id: Int, vararg args: Any) { status.value = Status(res.getString(id, *args)) }
    private fun sayText(text: String) { status.value = Status(text) }

    // ---- Import ---------------------------------------------------------------------------------------

    fun importUri(uri: Uri) {
        val ctx = getApplication<Application>()
        val name = displayName(uri, "recording")
        if (name.substringAfterLast('.', "").lowercase() in SCORE_EXTENSIONS) { openScore(uri, name); return }
        busy.value = true
        say(R.string.reading_file, name)
        viewModelScope.launch {
            try {
                val (decoded, file) = withContext(Dispatchers.IO) {
                    val copy = File(ctx.cacheDir, "takes").apply { mkdirs() }.resolve(name.replace('/', '_'))
                    ctx.contentResolver.openInputStream(uri)!!.use { input -> copy.outputStream().use { input.copyTo(it) } }
                    AudioDecoder.decode(ctx, Uri.fromFile(copy)) to copy
                }
                val kind = if (decoded.hasVideo) SourceKind.VIDEO else SourceKind.FILE
                setSource(Source(name, kind, decoded.durationS, decoded.audio, file))
                say(if (decoded.hasVideo) R.string.imported_video else R.string.imported, name, durationText(decoded.durationS))
                navigate(Screen.PROFILE)
            } catch (e: UnsupportedMediaException) {
                showProblem(Problem.NO_SOUND_TRACK)
            } catch (e: Exception) {
                showProblem(Problem.FILE_UNREADABLE, e.message)
            } finally {
                busy.value = false
            }
        }
    }

    fun openSample() {
        setSource(Source("Mikkel", SourceKind.SAMPLE, 246.0))
        profile.value = null
        navigate(Screen.PROFILE)
    }

    private fun displayName(uri: Uri, fallback: String): String =
        getApplication<Application>().contentResolver
            .query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
            ?: uri.lastPathSegment ?: fallback

    fun openScoreUri(uri: Uri) = openScore(uri, displayName(uri, "score"))

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
                    val bytes = ctx.contentResolver.openInputStream(uri)!!.use { it.readBytes() }
                    if (name.endsWith(".mxl", ignoreCase = true)) unzipScore(bytes) else bytes.decodeToString()
                }
                require(xml.contains("score-partwise") || xml.contains("score-timewise")) { "not MusicXML" }
                setSource(Source(name, SourceKind.SCORE, 0.0))
                val opened = TranscriptionResult(null, xml, Profile.BRASS_BAND, onDevice = true)
                result.value = opened
                saveCurrentScore(opened, name.substringBeforeLast('.'))
                say(R.string.opened_score, name)
                navigate(Screen.SCORE)
            } catch (e: Exception) {
                showProblem(Problem.FILE_UNREADABLE, e.message)
            } finally {
                busy.value = false
            }
        }
    }

    /** The root score of a compressed MusicXML container, or the first .xml that is not the container. */
    private fun unzipScore(bytes: ByteArray): String {
        val entries = HashMap<String, ByteArray>()
        ZipInputStream(bytes.inputStream()).use { zip ->
            while (true) {
                val e = zip.nextEntry ?: break
                if (!e.isDirectory) entries[e.name] = zip.readBytes()
            }
        }
        val root = entries["META-INF/container.xml"]?.decodeToString()
            ?.let { Regex("""full-path\s*=\s*"([^"]+)"""").find(it)?.groupValues?.get(1) }
        val chosen = root?.let { entries[it] }
            ?: entries.entries.firstOrNull { it.key.endsWith(".xml", true) && !it.key.startsWith("META-INF") }?.value
        return requireNotNull(chosen) { "no score in the container" }.decodeToString()
    }

    fun recorded(audio: PcmAudio, kind: SourceKind) {
        val ctx = getApplication<Application>()
        val file = File(ctx.cacheDir, "takes").apply { mkdirs() }.resolve("take-${System.currentTimeMillis()}.wav")
        viewModelScope.launch {
            withContext(Dispatchers.IO) { WavFile.write(file, audio) }
            setSource(Source(file.name, kind, audio.seconds, audio, file))
            say(R.string.record_stopped, durationText(audio.seconds))
            replaceTop(Screen.PROFILE)
        }
    }

    private fun setSource(s: Source) {
        source.value = s
        currentSavedScoreId = null
        result.value = null
        checked.value = emptyMap()
        renderedScoreAudio = null
        profile.value = null
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
        // A solo is transcribed offline on the phone by default; everything else needs the engine.
        where.value = if (canTranscribeOnDevice()) Where.DEVICE else Where.COMPANION
    }

    fun canTranscribeOnDevice(): Boolean = profile.value == Profile.SOLO && container.hasPitchModel && source.value?.audio != null

    fun startTranscription() {
        val p = profile.value ?: return
        val s = source.value ?: return
        navigate(Screen.TRANSCRIBE)
        job?.cancel()
        job = viewModelScope.launch {
            try {
                val r = if (where.value == Where.DEVICE && canTranscribeOnDevice()) transcribeOnDevice(s) else transcribeWithEngine(s, p)
                result.value = r
                saveCurrentScore(r)
                transcribe.update { it.copy(running = false, fraction = 1.0, etaSeconds = 0) }
                say(R.string.transcribe_done)
                replaceTop(Screen.REVIEW)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                transcribe.update { it.copy(running = false, error = e.message ?: e.javaClass.simpleName) }
                showProblem(Problem.SCORE_FAILED, e.message)
            }
        }
    }

    /** Starts again after a failed run, with the same recording and answer. */
    fun retryTranscription() {
        backStack.update { it.dropLast(1) }
        startTranscription()
    }

    private suspend fun transcribeOnDevice(s: Source): TranscriptionResult {
        val audio = s.audio!!
        val steps = listOf(Step.DECODE, Step.PITCH, Step.CONFIRM, Step.BEATS, Step.ARRANGE)
        transcribe.value = TranscribeState(true, Step.DECODE, 0.0, 0, steps.size, estimateDeviceSeconds(audio), res.getString(R.string.transcribe_where_device), steps = steps)
        val title = s.name.substringBeforeLast('.')
        return withContext(Dispatchers.Default) {
            val wav = s.file?.takeIf { it.extension.equals("wav", true) }?.readBytes()
            container.openSoloPipeline().use { pipeline ->
                val (take, stats) = pipeline.pipeline.listen(audio.samples, audio.sampleRate, title, wav) { stage ->
                    val step = steps[stage.ordinal.coerceAtMost(steps.size - 1)]
                    transcribe.update { it.copy(step = step, stepIndex = stage.ordinal, fraction = stage.ordinal / steps.size.toDouble(),
                        etaSeconds = ((1 - stage.ordinal / steps.size.toDouble()) * estimateDeviceSeconds(audio)).toInt()) }
                }
                transcribe.update { it.copy(step = Step.ARRANGE, stepIndex = 4, fraction = 0.9) }
                val a0 = System.nanoTime()
                val arranged = runCatching { pipeline.pipeline.arrange(take, output.value.toCore()) }
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
                val updated = when {
                    r.onDevice && take != null -> withContext(Dispatchers.Default) {
                        container.core.arrangeSolo(take, opts.toCore())?.let {
                            runCatching { getApplication<Application>().getExternalFilesDir("runs")?.resolve("last-solo-composition.json")?.writeText(it.compositionJson) }
                            r.copy(composition = it.composition, musicXml = it.musicXml, compositionJson = it.compositionJson,
                                appliedTranspose = opts.keyShift)
                        }
                    }
                    !r.onDevice && r.audioId != null -> rerunWithEngine(r, opts)
                    else -> null
                }
                if (updated != null) { result.value = updated; saveCurrentScore(updated); lastApplied = opts }
                say(R.string.arrangement_ready)
                then()
            } catch (e: Exception) {
                say(R.string.transcribe_failed, e.message ?: e.javaClass.simpleName)
            } finally {
                busy.value = false
            }
        }
    }

    private var lastApplied: OutputOptions = OutputOptions()

    private suspend fun rerunWithEngine(r: TranscriptionResult, opts: OutputOptions): TranscriptionResult {
        val engine = container.engine() ?: error(res.getString(R.string.where_companion_missing))
        val core = opts.toCore()
        // Re-arrangements skip the MP3 render: it is one more MuseScore run on the engine's machine.
        val job = engine.createJob(JobCreate(r.audioId, r.profile.id, renderAudio = false,
            allowHeavy = container.settings.allowHeavy, title = r.composition?.title.orEmpty(), lineup = core.lineup,
            difficulty = core.difficulty, transpose = core.transpose))
        engine.events(job.id).collect { }
        val final = engine.job(job.id)
        if (final.status != JobStatus.SUCCEEDED) error(final.error ?: final.status.name.lowercase())
        return r.copy(composition = engine.composition(job.id), musicXml = engine.musicXml(job.id), jobId = job.id,
            engineOutputs = final.outputs.toSet(), compositionJson = null, appliedTranspose = opts.keyShift,
            evidence = runCatching { engine.evidence(job.id) }.getOrNull())
    }

    private fun estimateDeviceSeconds(audio: PcmAudio): Int = maxOf(1, (audio.seconds / 20).toInt())

    private suspend fun transcribeWithEngine(s: Source, p: Profile): TranscriptionResult {
        val engine: EngineApi = container.engine() ?: error(res.getString(R.string.where_companion_missing))
        val stages = FixtureEngineApi.stagesOf(p).size
        transcribe.value = TranscribeState(true, Step.UPLOAD, 0.0, 0, stages, null,
            if (container.usingFixture) res.getString(R.string.demo_where) else res.getString(R.string.transcribe_where_companion, container.engineLabel()))
        val bytes = withContext(Dispatchers.IO) { s.file?.readBytes() ?: ByteArray(0) }
        val audio = engine.uploadAudio(s.name, bytes)
        val created = engine.createJob(
            JobCreate(audio.audioId, p.id, renderAudio = true, allowHeavy = container.settings.allowHeavy,
                title = s.name.substringBeforeLast('.')),
        )
        engineJobId = created.id
        val kinds = created.stages.map { Step.ofKind(it.kind ?: it.name.substringBefore('.')) }.filter { it != Step.QUEUED }.distinct()
        transcribe.update { it.copy(steps = listOf(Step.UPLOAD) + kinds.ifEmpty { listOf(Step.BEATS, Step.STEMS, Step.LAYERS, Step.TRANSCRIBE, Step.ARRANGE, Step.EXPORT) }) }
        val tracker = ProgressTracker(created.stages.size.takeIf { it > 0 } ?: stages)
        engine.events(created.id).collect { e ->
            val pr = tracker.onEvent(e)
            transcribe.update {
                it.copy(step = if (pr.currentKind != null) Step.ofKind(pr.currentKind) else Step.QUEUED, fraction = pr.fraction,
                    stepIndex = pr.stagesDone, stepTotal = pr.stagesTotal, etaSeconds = pr.etaSeconds, error = pr.error)
            }
        }
        val final = engine.job(created.id)
        if (final.status != JobStatus.SUCCEEDED) error(final.error ?: final.status.name.lowercase())
        val composition = engine.composition(created.id)
        val xml = engine.musicXml(created.id)
        return TranscriptionResult(composition, xml, p, onDevice = false, jobId = created.id, audioId = audio.audioId,
            engineOutputs = final.outputs.toSet().ifEmpty { FixtureEngineApi.OUTPUTS.toSet() },
            evidence = runCatching { engine.evidence(created.id) }.getOrNull())
    }

    fun cancelTranscription() {
        job?.cancel()
        val id = engineJobId
        if (id != null) viewModelScope.launch { runCatching { container.engine()?.cancel(id) } }
        engineJobId = null
        if (transcribe.value.running) {
            transcribe.update { it.copy(running = false) }
            say(R.string.transcribe_cancelled)
        }
    }

    // ---- Review ---------------------------------------------------------------------------------------

    private fun saveCurrentScore(r: TranscriptionResult, title: String? = null) {
        val scoreTitle = title?.takeIf(String::isNotBlank)
            ?: r.composition?.title?.takeIf(String::isNotBlank)
            ?: source.value?.name?.substringBeforeLast('.')
            ?: res.getString(R.string.score_title)
        val saved = scoreLibrary.save(currentSavedScoreId, scoreTitle, r.profile.id, r.musicXml, r.compositionJsonFor(container.core),
            jobId = r.jobId, evidenceJson = r.evidence?.let { no.brasscribe.play.model.BrasscribeJson.encodeToString(no.brasscribe.play.engine.Evidence.serializer(), it) },
            checked = checked.value.flatMap { (voice, events) -> events.map { "$voice:$it" } }.toSet())
        currentSavedScoreId = saved.id
        savedScores.value = scoreLibrary.list()
    }

    /** Fetch the computer's finished scores; keeps the phone's list when the computer can't be reached. */
    fun refreshComputerScores() {
        val engine = container.engine()?.takeIf { !container.usingFixture } ?: run { computerJobs.value = emptyList(); return }
        viewModelScope.launch { runCatching { engine.jobs() }.onSuccess { computerJobs.value = it } }
    }

    fun openEntry(entry: ScoreEntry, review: Boolean = false) {
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
                checked.value = emptyMap()
                result.value = r
                saveCurrentScore(r, entry.title)
                backStack.value = listOf(Screen.HOME, if (review) Screen.REVIEW else Screen.SCORE)
            } catch (e: Exception) {
                showProblem(Problem.FILE_UNREADABLE, e.message)
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
            scoreLibrary.delete(saved.id)
            if (currentSavedScoreId == saved.id) currentSavedScoreId = null
            savedScores.value = scoreLibrary.list()
            return
        }
        val jobId = entry.jobId ?: return
        viewModelScope.launch {
            runCatching { container.engine()?.deleteRun(jobId) }
            refreshComputerScores()
        }
    }

    fun openSavedScore(saved: SavedScore, review: Boolean = false) {
        currentSavedScoreId = saved.id
        source.value = Source(saved.title, SourceKind.SCORE, 0.0)
        result.value = TranscriptionResult(
            composition = saved.compositionJson?.let { runCatching { container.core.decodeComposition(it) }.getOrNull() },
            musicXml = saved.musicXml,
            profile = Profile.entries.firstOrNull { it.id == saved.profile } ?: Profile.BRASS_BAND,
            onDevice = saved.jobId == null,
            jobId = saved.jobId,
            compositionJson = saved.compositionJson,
            evidence = saved.evidenceJson?.let {
                runCatching { no.brasscribe.play.model.BrasscribeJson.decodeFromString(no.brasscribe.play.engine.Evidence.serializer(), it) }.getOrNull()
            },
        )
        checked.value = saved.checked.mapNotNull { key ->
            key.substringAfterLast(':').toIntOrNull()?.let { key.substringBeforeLast(':') to it }
        }.groupBy({ it.first }, { it.second }).mapValues { it.value.toSet() }
        backStack.value = listOf(Screen.HOME, if (review) Screen.REVIEW else Screen.SCORE)
    }

    fun renameSavedScore(id: String, title: String): Boolean {
        val cleaned = title.trim()
        if (cleaned.isEmpty()) return false
        val saved = scoreLibrary.list().firstOrNull { it.id == id } ?: return false
        return runCatching {
            val composition = saved.compositionJson?.let { container.core.decodeComposition(it).copy(title = cleaned) }
            val compositionJson = composition?.let(container.core::encodeComposition)
            val xml = MusicXmlTitleEditor.replaceTitle(saved.musicXml, cleaned)
            scoreLibrary.save(id, cleaned, saved.profile, xml, compositionJson, saved.jobId, saved.evidenceJson, saved.checked)
            savedScores.value = scoreLibrary.list()
            saved.jobId?.let { job -> viewModelScope.launch { runCatching { container.engine()?.renameRun(job, cleaned) } } }
            if (currentSavedScoreId == id) {
                result.value = result.value?.copy(composition = composition, musicXml = xml, compositionJson = compositionJson)
                source.value = source.value?.copy(name = cleaned)
            }
            true
        }.getOrDefault(false)
    }

    fun correctNote(voiceId: String, start: Int, pitch: Int, semitones: Int): Boolean {
        val current = result.value ?: return false
        val composition = current.composition ?: return false
        val voice = composition.voice(voiceId) ?: return false
        val noteIndex = voice.notes.indexOfFirst { it.start == start && it.pitch == pitch }
        if (noteIndex < 0) return false
        val updatedVoice = voice.copy(notes = voice.notes.mapIndexed { index, note ->
            if (index == noteIndex) note.copy(pitch = (note.pitch + semitones).coerceIn(0, 127)) else note
        })
        val updatedComposition = composition.copy(voices = composition.voices.map { if (it.id == voiceId) updatedVoice else it })
        val parts = updatedComposition.voices.map { v ->
            val name = when (v.id) { "solo" -> "Solo Cornet"; "brass" -> "Brass"; "strings" -> "Strings"; "bass" -> "Bass"; "drums" -> "Drums"; else -> v.id }
            PartSpec(v.id, name, if (v.role == VoiceRole.MELODY) Instrument.CORNET else Instrument.CONCERT)
        }
        // The same arranger as the score came from: the golden Composition re-arranges to the golden score.
        val arranger = if (output.value.lineup == Lineup.MINIMAL) "minimal" else "auto"
        val xml = runCatching { container.core.arrangeMusicXml(updatedComposition, arranger) }.getOrNull()
            ?: runCatching { container.core.toMusicXml(updatedComposition, parts) }.getOrNull()
            ?: return false
        val newPitch = (pitch + semitones).coerceIn(0, 127)
        // The evidence follows the note: the musician's pitch is now the written one each transcriber is compared to.
        val evidence = current.evidence?.let { e ->
            e.copy(notes = e.notes.map { n ->
                if (n.voice == voiceId && n.start == start && n.pitch == pitch)
                    n.copy(pitch = newPitch, models = n.models.map { it.copy(agrees = it.pitch == newPitch) }) else n
            })
        }
        val updated = current.copy(composition = updatedComposition, musicXml = xml,
            compositionJson = container.core.encodeComposition(updatedComposition), evidence = evidence, changedOnPhone = true)
        result.value = updated
        saveCurrentScore(updated)
        return true
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

    /** Plays the recording's bar, then the score's bar, looped, until [stopListening]. */
    fun listenToBar(bar: Int) {
        val r = result.value ?: return
        val map = TickMap(r.composition ?: return)
        val original = source.value?.audio?.let { a ->
            val span = map.barSeconds(bar)
            a.slice(span.start, span.endInclusive)
        }
        viewModelScope.launch {
            val score = scoreBarAudio(r, map, bar)
            val clipsToPlay = listOfNotNull(original, score)
            if (clipsToPlay.isEmpty()) { say(R.string.listen_unavailable); return@launch }
            clips.playLooped(clipsToPlay)
            clipPlaying.value = bar
            say(if (original != null) R.string.playing_bar_original else R.string.playing_bar_score, bar)
        }
    }

    private suspend fun scoreBarAudio(r: TranscriptionResult, map: TickMap, bar: Int): PcmAudio? {
        val jobId = r.jobId ?: return null
        val rendered = renderedScoreAudio ?: withContext(Dispatchers.IO) {
            runCatching {
                val bytes = container.engine()?.renderedAudio(jobId) ?: return@runCatching null
                val f = File(getApplication<Application>().cacheDir, "score-$jobId.mp3").apply { writeBytes(bytes) }
                AudioDecoder.decode(getApplication(), Uri.fromFile(f)).audio
            }.getOrNull()
        }?.also { renderedScoreAudio = it } ?: return null
        // The rendered score starts at bar 1 and runs at the score's tempo.
        val comp = r.composition ?: return null
        val secondsPerTick = 60.0 / comp.bpm / comp.ticksPerBeat
        val from = maxOf(0, map.barStart(bar)) * secondsPerTick
        val to = map.barEnd(bar) * secondsPerTick
        return rendered.slice(from, to)
    }

    fun stopListening() {
        clips.stop()
        clipPlaying.value = null
    }

    // ---- Companion ------------------------------------------------------------------------------------

    fun connect(url: String, code: String) {
        companionState.value = res.getString(R.string.companion_connecting)
        viewModelScope.launch {
            try {
                val client = container.newEngineClient(url)
                val health = client.health()
                if (health.authRequired) {
                    val token = client.pair(code.trim(), container.deviceName).token
                    container.settings.token = token
                } else container.settings.token = null
                container.settings.url = url
                container.settings.paired = true
                container.settings.useFixture = false
                companionState.value = res.getString(R.string.companion_connected, health.version, url, health.device)
                say(R.string.companion_connected, health.version, url, health.device)
            } catch (e: Exception) {
                companionState.value = res.getString(R.string.companion_failed, e.message ?: e.javaClass.simpleName)
                say(R.string.companion_failed, e.message ?: e.javaClass.simpleName)
            }
        }
    }

    fun useFixture(on: Boolean) {
        container.settings.useFixture = on
        companionState.value = null
    }

    override fun onCleared() {
        clips.stop()
    }

    companion object {
        const val TAG = "BrasscribePlay"
        const val SOLO_PART_NAME = "Solo Cornet"
        /** Opened as a score, never sent through a transcription profile. */
        val SCORE_EXTENSIONS = setOf("musicxml", "mxl", "xml")
    }
}
