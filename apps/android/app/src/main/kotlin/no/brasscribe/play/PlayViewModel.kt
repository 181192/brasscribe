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
import no.brasscribe.play.model.PartSpec
import no.brasscribe.play.model.TickMap
import no.brasscribe.play.model.ArrangeOptions
import no.brasscribe.play.model.SoloTake
import no.brasscribe.play.model.TempoEstimator
import no.brasscribe.play.playback.ClipPlayer
import java.io.File

enum class Screen { HOME, RECORD, PROFILE, TRANSCRIBE, REVIEW, OUTPUT, SCORE, EXPORT, COMPANION, ABOUT }

enum class SourceKind { FILE, VIDEO, MICROPHONE, DEVICE, SAMPLE }

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
)

/** A finished transcription. [musicXml] is what the score view renders; [jobId] is set for engine results. */
data class TranscriptionResult(
    val composition: Composition,
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
)

enum class Lineup(@StringRes val label: Int) { FULL(R.string.lineup_full), MINIMAL(R.string.lineup_minimal), SOLO(R.string.lineup_solo) }
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

    private val backStack = MutableStateFlow(listOf(Screen.HOME))
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

    fun say(@StringRes id: Int, vararg args: Any) { status.value = Status(res.getString(id, *args)) }
    private fun sayText(text: String) { status.value = Status(text) }

    // ---- Import ---------------------------------------------------------------------------------------

    fun importUri(uri: Uri) {
        val ctx = getApplication<Application>()
        val name = ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: uri.lastPathSegment ?: "recording"
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
                say(R.string.import_no_audio)
            } catch (e: Exception) {
                say(R.string.import_failed, e.message ?: e.javaClass.simpleName)
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
                transcribe.update { it.copy(running = false, fraction = 1.0, etaSeconds = 0) }
                say(R.string.transcribe_done)
                replaceTop(Screen.REVIEW)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                transcribe.update { it.copy(running = false, error = e.message ?: e.javaClass.simpleName) }
                say(R.string.transcribe_failed, e.message ?: e.javaClass.simpleName)
            }
        }
    }

    private suspend fun transcribeOnDevice(s: Source): TranscriptionResult {
        val audio = s.audio!!
        val steps = listOf(Step.DECODE, Step.PITCH, Step.CONFIRM, Step.BEATS, Step.ARRANGE)
        transcribe.value = TranscribeState(true, Step.DECODE, 0.0, 0, steps.size, estimateDeviceSeconds(audio), res.getString(R.string.transcribe_where_device))
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
                if (arranged != null) {
                    TranscriptionResult(arranged.composition, arranged.musicXml, Profile.SOLO, onDevice = true, compositionJson = arranged.compositionJson)
                } else {
                    // Without the Rust core: the Kotlin grid and a single solo part.
                    val c = container.core.quantizeSolo(take.swiftF0, TempoEstimator.estimate(take.swiftF0.map { it.onsetS }), title)
                    TranscriptionResult(c, container.core.toMusicXml(c, listOf(PartSpec("solo", SOLO_PART_NAME, Instrument.CORNET))), Profile.SOLO, onDevice = true)
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
                            r.copy(composition = it.composition, musicXml = it.musicXml, compositionJson = it.compositionJson,
                                appliedTranspose = opts.keyShift)
                        }
                    }
                    !r.onDevice && r.audioId != null -> rerunWithEngine(r, opts)
                    else -> null
                }
                if (updated != null) { result.value = updated; lastApplied = opts }
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
            allowHeavy = container.settings.allowHeavy, title = r.composition.title, lineup = core.lineup,
            difficulty = core.difficulty, transpose = core.transpose))
        engine.events(job.id).collect { }
        val final = engine.job(job.id)
        if (final.status != JobStatus.SUCCEEDED) error(final.error ?: final.status.name.lowercase())
        return r.copy(composition = engine.composition(job.id), musicXml = engine.musicXml(job.id), jobId = job.id,
            engineOutputs = final.outputs.toSet(), compositionJson = null, appliedTranspose = opts.keyShift)
    }

    private fun estimateDeviceSeconds(audio: PcmAudio): Int = maxOf(1, (audio.seconds / 20).toInt())

    private suspend fun transcribeWithEngine(s: Source, p: Profile): TranscriptionResult {
        val engine: EngineApi = container.engine() ?: error(res.getString(R.string.where_companion_missing))
        val stages = FixtureEngineApi.stagesOf(p).size
        transcribe.value = TranscribeState(true, Step.UPLOAD, 0.0, 0, stages, null,
            res.getString(R.string.transcribe_where_companion, container.engineLabel()))
        val bytes = withContext(Dispatchers.IO) { s.file?.readBytes() ?: ByteArray(0) }
        val audio = engine.uploadAudio(s.name, bytes)
        val created = engine.createJob(
            JobCreate(audio.audioId, p.id, renderAudio = true, allowHeavy = container.settings.allowHeavy,
                title = s.name.substringBeforeLast('.')),
        )
        engineJobId = created.id
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
            engineOutputs = final.outputs.toSet().ifEmpty { FixtureEngineApi.OUTPUTS.toSet() })
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

    fun markChecked(voiceId: String, index: Int, remaining: Int) {
        checked.update { it + (voiceId to (it[voiceId].orEmpty() + index)) }
        say(R.string.checked_left, remaining)
    }

    /** Plays the recording's bar, then the score's bar, looped, until [stopListening]. */
    fun listenToBar(bar: Int) {
        val r = result.value ?: return
        val map = TickMap(r.composition)
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
        val secondsPerTick = 60.0 / r.composition.bpm / r.composition.ticksPerBeat
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
    }
}
