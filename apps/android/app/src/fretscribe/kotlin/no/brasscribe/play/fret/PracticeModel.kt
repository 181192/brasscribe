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
    /** The phone has no room to keep it. */
    NO_ROOM,
    /** It is larger than the phone takes. */
    TOO_LARGE,
    /** On the phone, and the phone cannot play it. */
    UNPLAYABLE,
}

/**
 * The recordings of the songs the phone has practised, one file to a song, by the id of the song's job on
 * the computer: a song's recording is copied here when its tab is first opened with the recording in hand,
 * or when it is fetched from the computer, so the song can be practised when it is opened again.
 */
class PracticeRecordings(private val dir: File) {
    /**
     * The file of [job]: what a file name can hold of the id, and a short hash of the whole id, so two ids that
     * read the same once their other characters are gone, or past the length kept, are still two files.
     */
    private fun named(job: String): File? {
        if (job.isEmpty()) return null
        val plain = job.filter { it.isLetterOrDigit() || it == '-' || it == '_' }.take(60)
        val hash = java.security.MessageDigest.getInstance("SHA-256").digest(job.toByteArray()).take(4).joinToString("") { "%02x".format(it) }
        return File(dir, "$plain.$hash")
    }

    fun find(job: String): File? = named(job)?.takeIf { it.isFile && it.length() > 0 }

    /** Where a recording being fetched or copied is written, until it is whole ([arrived]); what an earlier try left there is gone. */
    fun arriving(job: String): File? = named(job)?.let { dir.mkdirs(); File(dir, it.name + PART).also(File::delete) }

    /** The try at [job]'s recording did not get through: what there is of it goes. */
    fun dropped(job: String) {
        named(job)?.let { File(dir, it.name + PART).delete() }
    }

    /** Room left for recordings, in bytes. */
    val room: Long get() = generateSequence(dir) { it.parentFile }.firstOrNull { it.exists() }?.usableSpace ?: 0L

    fun arrived(job: String): File? {
        val to = named(job) ?: return null
        val part = File(dir, to.name + PART)
        return if (part.length() > 0 && part.renameTo(to)) to else { part.delete(); null }
    }

    /** A copy of [from] kept for [job]; [from] itself when it cannot be copied. */
    fun keep(job: String, from: File): File {
        find(job)?.let { if (it.length() == from.length()) return it }
        val part = arriving(job) ?: return from
        return runCatching { from.copyTo(part, overwrite = true); arrived(job) }.getOrNull() ?: from.also { dropped(job) }
    }

    /**
     * Drops the recordings of every song but [jobs]: a song deleted from Your songs takes its recording with it.
     * What a fetch or a copy that did not finish left behind goes too (none is running when this is asked).
     */
    fun prune(jobs: Set<String>) {
        val kept = jobs.mapNotNull { named(it)?.name }.toSet()
        dir.listFiles()?.filter { it.name !in kept }?.forEach { it.delete() }
    }

    companion object {
        private const val PART = ".part"

        /** Less room than this after a fetch failed: the phone is full. */
        const val FULL_BYTES = 16L shl 20

        /**
         * Why a recording did not come from the computer, from what went wrong ([error]) and the [room] left on the
         * phone: the computer does not have it; it is larger than the phone takes; the phone could not keep it
         * (no room, or the file could not be written); or the computer was not reached.
         */
        fun whyNot(error: Throwable, room: Long): RecordingState = when {
            (error as? EngineException)?.status == 404 -> RecordingState.GONE
            (error as? EngineException)?.status == 413 -> RecordingState.TOO_LARGE
            error is EngineException -> RecordingState.NO_ANSWER
            error is java.io.FileNotFoundException || error is IllegalStateException || room < FULL_BYTES -> RecordingState.NO_ROOM
            else -> RecordingState.NO_ANSWER
        }
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
    private var fetching: kotlinx.coroutines.Job? = null

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
        if (player != null || fetching?.isActive == true) { stretch(); return }
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
        // One fetch at a time: a second press while one runs does nothing.
        if (fetching?.isActive == true || player != null) return
        val look = ++looking
        recording = RecordingState.GETTING
        fetching = viewModelScope.launch {
            val got = try {
                withContext(Dispatchers.IO) {
                    val part = store.arriving(job) ?: throw IllegalStateException("no place to keep the recording")
                    engine.jobInput(job, part)
                    store.arrived(job) ?: throw java.io.IOException("the recording came empty")
                }
            } catch (e: CancellationException) {
                withContext(kotlinx.coroutines.NonCancellable + Dispatchers.IO) { store.dropped(job) }
                throw e
            } catch (e: Exception) {
                android.util.Log.w(PlayViewModel.TAG, "the recording could not be fetched", e)
                val why = withContext(Dispatchers.IO) { store.dropped(job); PracticeRecordings.whyNot(e, store.room) }
                if (look == looking) recording = why
                null
            }
            if (got != null && look == looking) load(got)
        }
    }

    fun toggle() {
        val p = player ?: return
        if (playing || p.playing) { p.pause(); return }
        // Asked to play while the phone holds the sound back: asked again, from the start of the asking.
        if (p.asked) p.pause()
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

    /** A bar back or on from the bar the song is in. In the last bar (of the tab, or of the bars being repeated) there is no bar on: nothing happens. */
    fun step(bars: Int) {
        val clock = clock ?: return
        val bar = clock.placeAt(now()).bar
        if (bars > 0 && bar >= (repeat?.last ?: (clock.bars - 1))) return
        toBar(bar + bars)
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

    /** The tab is left: the sound stops, a fetch that is running is given up, and the song is kept where it was. */
    fun leave() {
        looking++
        fetching?.cancel()
        fetching = null
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
