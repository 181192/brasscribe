package no.brasscribe.play.fret

import android.app.Application
import androidx.annotation.VisibleForTesting
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.engine.EngineException
import java.io.File

/** What is known of the recording of the song on screen. */
enum class RecordingState {
    /** Being looked for on the phone. */
    LOOKING,
    /** On the phone, and it plays. */
    HERE,
    /** Not on the phone: the song was opened from the computer's list, or its file is gone. */
    NOT_HERE,
    /** Being copied from the computer. */
    GETTING,
    /** The computer does not have it either. */
    GONE,
    /** The computer could not be asked. */
    NO_ANSWER,
    /** On the phone, and the phone cannot play it. */
    UNPLAYABLE,
}

/**
 * The recordings of the songs the phone has practised, one file to a song, by the id of the song's job on
 * the computer: a song's recording is copied here when its tab is first opened with the recording in hand,
 * or when it is fetched from the computer, so the song can be practised when it is opened again.
 */
class PracticeRecordings(private val dir: File) {
    private fun named(job: String): File? = job.filter { it.isLetterOrDigit() || it == '-' || it == '_' }.take(80).takeIf { it.isNotEmpty() }?.let { File(dir, it) }

    fun find(job: String): File? = named(job)?.takeIf { it.isFile && it.length() > 0 }

    /** Where a recording being fetched is written, until it is whole ([arrived]). */
    fun arriving(job: String): File? = named(job)?.let { dir.mkdirs(); File(dir, it.name + PART) }

    fun arrived(job: String): File? {
        val to = named(job) ?: return null
        val part = File(dir, to.name + PART)
        return if (part.length() > 0 && part.renameTo(to)) to else { part.delete(); null }
    }

    /** A copy of [from] kept for [job]; [from] itself when it cannot be copied. */
    fun keep(job: String, from: File): File {
        find(job)?.let { if (it.length() == from.length()) return it }
        val part = arriving(job) ?: return from
        return runCatching { from.copyTo(part, overwrite = true); arrived(job) }.getOrNull() ?: from
    }

    /** Drops the recordings of every song but [jobs]: a song deleted from Your songs takes its recording with it. */
    fun prune(jobs: Set<String>) {
        val kept = jobs.mapNotNull { named(it)?.name }.toSet()
        dir.listFiles()?.filter { it.name.removeSuffix(PART) !in kept }?.forEach { it.delete() }
    }

    private companion object {
        const val PART = ".part"
    }
}

/**
 * Practice: the recording of the song on screen, where it is, how fast it plays and which bars it repeats.
 * It outlives the tab's views (a new size or a turn of the phone is a new view) and is kept for each song
 * while the app runs; the song being practised is also kept through the app being stopped.
 */
class PracticeModel(app: Application, private val saved: SavedStateHandle) : AndroidViewModel(app), RecordingPlayer.Listener {
    private val store = PracticeRecordings(File(app.noBackupFilesDir, "recordings"))
    private var player: RecordingPlayer? = null
    private var clock: TabClock? = null
    private var song: String? = null
    private var job: String? = null
    private var looking = 0

    private class Left(val at: Double, val speed: Int, val repeat: RepeatBars?)
    private val left = HashMap<String, Left>()

    var recording by mutableStateOf(RecordingState.LOOKING)
        private set
    var playing by mutableStateOf(false)
        private set
    /** Per cent of the recording's own speed. */
    var speed by mutableIntStateOf(PracticeSpeed.FULL)
        private set
    var repeat by mutableStateOf<RepeatBars?>(null)
        private set
    /** The second of the recording the song is at while it is not playing; while it plays, [now] says. */
    var at by mutableDoubleStateOf(0.0)
        private set

    /** Counts the times the player moved the song: a bar back or on, to the start, into a repeat. The page then shows where it went. */
    var jumps by mutableIntStateOf(0)
        private set

    /** The second of the recording the song is at. */
    fun now(): Double = player?.takeIf { playing }?.position ?: at

    /**
     * The song on screen: [song] names it, [job] is its job on the computer (the recording is kept and fetched
     * by it), [clock] follows the recording in its tab, and [inHand] is the recording's file when the phone
     * sent it. [songs]: the jobs of Your songs, when the list is known; the recordings of the others go.
     */
    fun open(song: String, job: String?, clock: TabClock?, inHand: File?, songs: Set<String>? = null) {
        this.clock = clock
        if (song != this.song) {
            remember()
            release()
            this.song = song
            val was = left[song] ?: Left(
                saved.get<Double>(KEY_AT)?.takeIf { saved.get<String>(KEY_SONG) == song } ?: 0.0,
                saved.get<Int>(KEY_SPEED)?.takeIf { saved.get<String>(KEY_SONG) == song } ?: PracticeSpeed.FULL,
                saved.get<IntArray>(KEY_REPEAT)?.takeIf { saved.get<String>(KEY_SONG) == song && it.size == 2 }?.let { RepeatBars(it[0], it[1]) },
            )
            at = was.at; speed = was.speed.coerceIn(PracticeSpeed.MIN, PracticeSpeed.MAX); repeat = was.repeat
        }
        this.job = job
        repeat = repeat?.takeIf { clock == null || (it.first in 0..it.last && it.last < clock.bars) }
        if (player != null || recording == RecordingState.GETTING) { stretch(); return }
        val file = inHand?.takeIf { it.isFile && it.length() > 0 }
        val look = ++looking
        recording = RecordingState.LOOKING
        viewModelScope.launch {
            val found = withContext(Dispatchers.IO) {
                if (job != null && songs != null && job in songs) store.prune(songs)
                if (job == null) file else file?.let { store.keep(job, it) } ?: store.find(job)
            }
            if (look != looking) return@launch
            if (found != null) load(found) else recording = RecordingState.NOT_HERE
        }
    }

    private fun load(file: File) {
        player = MediaRecordingPlayer(getApplication(), file, this, silent).also {
            it.speed = speed / 100f
            if (at > 0) it.seekTo(at)
        }
        stretch()
        recording = RecordingState.HERE
    }

    /** Gives the player the seconds of the bars to repeat. */
    private fun stretch() {
        player?.repeat = repeat?.let { r -> clock?.span(r) }
    }

    /** Copies the recording from the computer, which holds what it was sent. */
    fun fetch(engine: EngineApi) {
        val job = job ?: return
        if (recording == RecordingState.GETTING || player != null) return
        val look = ++looking
        recording = RecordingState.GETTING
        viewModelScope.launch {
            val got = try {
                withContext(Dispatchers.IO) {
                    val part = store.arriving(job) ?: throw IllegalStateException("no place to keep the recording")
                    engine.jobInput(job, part)
                    store.arrived(job) ?: throw IllegalStateException("the recording came empty")
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.w(PlayViewModel.TAG, "the recording could not be fetched", e)
                if (look == looking) recording = if ((e as? EngineException)?.status == 404) RecordingState.GONE else RecordingState.NO_ANSWER
                null
            }
            if (got != null && look == looking) load(got)
        }
    }

    fun toggle() {
        val p = player ?: return
        if (playing || p.playing) { p.pause(); return }
        // From the end, or from outside the bars being repeated, it starts over.
        val span = repeat?.let { clock?.span(it) }
        val end = clock?.end
        if (span != null && (at < span.start - EDGE || at >= span.endInclusive - EDGE)) seek(span.start)
        else if (end != null && at >= end - EDGE) seek(0.0)
        p.play()
    }

    fun pause() {
        player?.pause()
    }

    private fun seek(seconds: Double) {
        val to = seconds.coerceAtLeast(0.0)
        player?.seekTo(to)
        at = to
        jumps++
        remember()
    }

    /** To the line of [bar], kept inside the bars being repeated. */
    fun toBar(bar: Int) {
        val clock = clock ?: return
        val within = repeat?.let { bar.coerceIn(it.first, it.last) } ?: bar.coerceIn(0, clock.bars - 1)
        seek(clock.secondsAt(within))
    }

    /** A bar back or on from the bar the song is in. */
    fun step(bars: Int) {
        val clock = clock ?: return
        toBar(clock.placeAt(now()).bar + bars)
    }

    /** Back to where the repeat starts; to the start of the tab when nothing is repeated. */
    fun toStart() = toBar(repeat?.first ?: 0)

    fun slower() = speedTo(PracticeSpeed.slower(speed))
    fun faster() = speedTo(PracticeSpeed.faster(speed))

    private fun speedTo(percent: Int) {
        speed = percent
        player?.speed = percent / 100f
        remember()
    }

    /** Repeats [bars]; null plays on. The song goes to the first of them when it is outside them. */
    fun repeat(bars: RepeatBars?) {
        repeat = bars
        stretch()
        val clock = clock
        if (bars != null && clock != null && clock.placeAt(now()).bar !in bars.first..bars.last) toBar(bars.first)
        remember()
    }

    /** The tab is left: the sound stops, and the song is kept where it was. */
    fun leave() {
        looking++
        remember()
        release()
        recording = RecordingState.LOOKING
    }

    private fun release() {
        player?.let { at = if (playing) it.position else at; it.release() }
        player = null
        playing = false
    }

    private fun remember() {
        val song = song ?: return
        val now = now()
        left[song] = Left(now, speed, repeat)
        saved[KEY_SONG] = song
        saved[KEY_AT] = now
        saved[KEY_SPEED] = speed
        saved[KEY_REPEAT] = repeat?.let { intArrayOf(it.first, it.last) }
    }

    override fun onPlaying(playing: Boolean) {
        if (!playing) player?.let { at = it.position }
        this.playing = playing
        if (!playing) remember()
    }

    override fun onEnded() {
        player?.let { at = it.position }
        playing = false
    }

    override fun onFailed() {
        release()
        recording = RecordingState.UNPLAYABLE
    }

    override fun onCleared() = release()

    /** The player, for the tests that listen to what it does. */
    @get:VisibleForTesting
    internal val recordingPlayer: RecordingPlayer? get() = player

    companion object {
        /** How near the end of a stretch counts as its end, in seconds. */
        private const val EDGE = 0.05
        private const val KEY_SONG = "practice.song"
        private const val KEY_AT = "practice.at"
        private const val KEY_SPEED = "practice.speed"
        private const val KEY_REPEAT = "practice.repeat"

        /** The tests play without sound. */
        @VisibleForTesting
        @Volatile var silent = false
    }
}
