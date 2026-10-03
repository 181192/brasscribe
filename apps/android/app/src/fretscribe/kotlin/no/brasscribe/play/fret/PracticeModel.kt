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
    private fun named(job: String): File? = fileName(job)?.let { File(dir, it) }

    fun find(job: String): File? = named(job)?.takeIf { it.isFile && it.length() > 0 }

    /**
     * Where a recording being fetched or copied is written, until it is whole ([arrived]): a file of this try's own,
     * so a try that was given up and clears up after itself late never takes the file of the try after it.
     */
    fun arriving(job: String): File? = named(job)?.let { runCatching { dir.mkdirs(); File.createTempFile(it.name + ".", PART, dir) }.getOrNull() }

    /** The try that wrote [part] did not get through: what there is of it goes. */
    fun dropped(part: File?) {
        part?.delete()
    }

    /** Room left for recordings, in bytes. */
    val room: Long get() = generateSequence(dir) { it.parentFile }.firstOrNull { it.exists() }?.usableSpace ?: 0L

    /** [part], written whole, becomes [job]'s recording; one that came empty goes. */
    fun arrived(job: String, part: File): File? {
        val to = named(job)
        return if (to != null && part.length() > 0 && part.renameTo(to)) to else { part.delete(); null }
    }

    /** A copy of [from] kept for [job]; [from] itself when it cannot be copied. */
    fun keep(job: String, from: File): File {
        find(job)?.let { if (it.length() == from.length()) return it }
        val part = arriving(job) ?: return from
        return runCatching { from.copyTo(part, overwrite = true); arrived(job, part) }.getOrNull() ?: from.also { dropped(part) }
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

        /**
         * The name of [job]'s file: what a file name can hold of the id, and a short hash of the whole id, so two ids
         * that read the same once their other characters are gone, or past the length kept, are still two files.
         */
        fun fileName(job: String): String? {
            if (job.isEmpty()) return null
            val plain = job.filter { it.isLetterOrDigit() || it == '-' || it == '_' }.take(60)
            val hash = java.security.MessageDigest.getInstance("SHA-256").digest(job.toByteArray()).take(4).joinToString("") { "%02x".format(it) }
            return "$plain.$hash"
        }

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

        /** The recordings of the app on [context]. */
        fun of(context: android.content.Context): PracticeRecordings = PracticeRecordings(File(context.noBackupFilesDir, "recordings"))

        /**
         * The kind of sound file [file] is, as a file name's extension, read from its first bytes (a kept recording's
         * name says nothing of it): WAV, MP4 sound (M4A), MP3, Ogg, FLAC or WebM; "wav" when it is none of these.
         */
        fun extensionOf(file: File): String {
            val head = runCatching { file.inputStream().use { s -> ByteArray(12).also { s.read(it) } } }.getOrNull() ?: return "wav"
            fun at(offset: Int, text: String) = text.indices.all { head[offset + it] == text[it].code.toByte() }
            return when {
                at(0, "RIFF") && at(8, "WAVE") -> "wav"
                at(4, "ftyp") -> "m4a"
                at(0, "ID3") || (head[0] == 0xFF.toByte() && (head[1].toInt() and 0xE0) == 0xE0) -> "mp3"
                at(0, "OggS") -> "ogg"
                at(0, "fLaC") -> "flac"
                head[0] == 0x1A.toByte() && head[1] == 0x45.toByte() && head[2] == 0xDF.toByte() && head[3] == 0xA3.toByte() -> "webm"
                else -> "wav"
            }
        }
    }
}

/** Where a song was left in practice: the second of the recording, the speed in per cent, and the bars repeated. */
data class PracticePlace(val at: Double, val speed: Int, val repeat: RepeatBars?)

/**
 * Where each song was left in practice, kept on the phone beside the song's recording ([PracticeRecordings]), by the
 * id of the song's job: one small file to a song. A song deleted from Your songs keeps its file until a song that is
 * still in Your songs is next opened on the tab, when the places of the songs no longer there are pruned.
 */
class PracticePlaces(private val dir: File) {
    private fun named(job: String): File? = PracticeRecordings.fileName(job)?.let { File(dir, it) }

    /** Where [job]'s song was left; null when it was never practised, or what is kept can't be read. */
    fun read(job: String): PracticePlace? {
        val words = named(job)?.takeIf { it.isFile }?.let { runCatching { it.readText() }.getOrNull() }?.trim()?.split(' ') ?: return null
        val at = words.getOrNull(0)?.toDoubleOrNull()?.takeIf { it.isFinite() && it >= 0 } ?: return null
        val speed = words.getOrNull(1)?.toIntOrNull() ?: return null
        val first = words.getOrNull(2)?.toIntOrNull()
        val last = words.getOrNull(3)?.toIntOrNull()
        return PracticePlace(at, speed, if (first != null && last != null && first in 0..last) RepeatBars(first, last) else null)
    }

    /** Keeps [place] for [job]'s song: written whole, then put in the place of what was there. */
    fun save(job: String, place: PracticePlace) {
        val to = named(job) ?: return
        runCatching {
            dir.mkdirs()
            val part = File(dir, to.name + ".part")
            part.writeText(listOfNotNull(place.at.toString(), place.speed.toString(), place.repeat?.first?.toString(), place.repeat?.last?.toString()).joinToString(" "))
            if (!part.renameTo(to)) part.delete()
        }.onFailure { android.util.Log.w(PlayViewModel.TAG, "where the song was left could not be kept", it) }
    }

    /** Drops the places of every song but [jobs]: a song deleted from Your songs takes its place with it. */
    fun prune(jobs: Set<String>) {
        val kept = jobs.mapNotNull { PracticeRecordings.fileName(it) }.toSet()
        dir.listFiles()?.filter { it.name !in kept }?.forEach { it.delete() }
    }

    companion object {
        /** The places of the app on [context]. */
        fun of(context: android.content.Context): PracticePlaces = PracticePlaces(File(context.noBackupFilesDir, "practice"))
    }
}

/**
 * Practice: the recording of the song on screen, where it is, how fast it plays and which bars it repeats.
 * It outlives the tab's views (a new size or a turn of the phone is a new view) and is kept for each song
 * while the app runs, in the saved state for the song being practised, and on the phone ([PracticePlaces])
 * for every song in Your songs, so a song opened after the app was closed is where it was left.
 */
class PracticeModel(app: Application, private val saved: SavedStateHandle) : AndroidViewModel(app), RecordingPlayer.Listener {
    private val store = PracticeRecordings.of(app)
    private val places = PracticePlaces.of(app)
    /** The places are written one at a time, in order: an older one never lands after a newer one. */
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    private val writing = Dispatchers.IO.limitedParallelism(1)
    private var player: RecordingPlayer? = null
    private var clock: TabClock? = null
    private var song: String? = null
    private var job: String? = null
    private var looking = 0
    private var fetching: kotlinx.coroutines.Job? = null
    /** Counts the player's changes: a place read from the phone is not taken over one made since it was asked for. */
    private var changes = 0
    /** The song on screen has a place on the phone that is not read yet. */
    private var unread = false

    private val left = HashMap<String, PracticePlace>()

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
            val state = saved.get<String>(KEY_SONG) == song
            val was = left[song] ?: if (state) PracticePlace(
                saved.get<Double>(KEY_AT) ?: 0.0,
                saved.get<Int>(KEY_SPEED) ?: PracticeSpeed.FULL,
                saved.get<IntArray>(KEY_REPEAT)?.takeIf { it.size == 2 }?.let { RepeatBars(it[0], it[1]) },
            ) else null
            // Neither in memory nor in the saved state: the place kept on the phone is read with the recording.
            unread = was == null
            take(was ?: PracticePlace(0.0, PracticeSpeed.FULL, null))
        }
        this.job = job
        repeat = repeat?.takeIf { fits(it) }
        if (player != null || fetching?.isActive == true) { stretch(); return }
        val file = inHand?.takeIf { it.isFile && it.length() > 0 }
        val look = ++looking
        val since = changes
        val ask = unread
        recording = RecordingState.LOOKING
        viewModelScope.launch {
            val (found, kept) = withContext(Dispatchers.IO) {
                if (job != null && songs != null && job in songs) {
                    store.prune(songs)
                    // In order with the writes of the places: a prune never runs beside a write.
                    withContext(writing) { places.prune(songs) }
                }
                val found = if (job == null) file else file?.let { store.keep(job, it) } ?: store.find(job)
                found to job?.takeIf { ask }?.let(places::read)
            }
            if (look != looking) return@launch
            if (unread && kept != null && changes == since) {
                take(kept)
                repeat = repeat?.takeIf { fits(it) }
                // The page goes to where the song was left, as it does when the player moves it.
                jumps++
            }
            unread = false
            if (found != null) load(found) else recording = RecordingState.NOT_HERE
        }
    }

    private fun take(place: PracticePlace) {
        at = place.at; speed = place.speed.coerceIn(PracticeSpeed.MIN, PracticeSpeed.MAX); repeat = place.repeat
    }

    /** [bars] are bars of the tab on screen. */
    private fun fits(bars: RepeatBars): Boolean = clock.let { it == null || (bars.first in 0..bars.last && bars.last < it.bars) }

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
            // This fetch's own file: a fetch given up on leaving the screen clears it, also after the next one has begun.
            var part: File? = null
            val got = try {
                withContext(Dispatchers.IO) {
                    val into = store.arriving(job)?.also { part = it } ?: throw IllegalStateException("no place to keep the recording")
                    engine.jobInput(job, into)
                    store.arrived(job, into) ?: throw java.io.IOException("the recording came empty")
                }
            } catch (e: CancellationException) {
                withContext(kotlinx.coroutines.NonCancellable + Dispatchers.IO) { store.dropped(part) }
                throw e
            } catch (e: Exception) {
                android.util.Log.w(PlayViewModel.TAG, "the recording could not be fetched", e)
                val why = withContext(Dispatchers.IO) { store.dropped(part); PracticeRecordings.whyNot(e, store.room) }
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
        changes++
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
        if (bars > 0 && !hasBarOn(bar)) return
        toBar(bar + bars)
    }

    /** There is a bar after [bar] to step on to: it is not the last of the tab, nor the last of the bars being repeated. */
    fun hasBarOn(bar: Int): Boolean {
        val clock = clock ?: return false
        return bar < (repeat?.last ?: (clock.bars - 1))
    }

    /** Back to where the repeat starts; to the start of the tab when nothing is repeated. */
    fun toStart() = toBar(repeat?.first ?: 0)

    fun slower() = speedTo(PracticeSpeed.slower(speed))
    fun faster() = speedTo(PracticeSpeed.faster(speed))

    private fun speedTo(percent: Int) {
        changes++
        speed = percent
        player?.speed = percent / 100f
        remember()
    }

    /**
     * One bar again and again, slowly, from its start: to listen to a note Fretscribe is not sure of. [bar] is counted
     * from 0; it plays when the recording is on the phone.
     */
    fun playBarSlowly(bar: Int) {
        val clock = clock ?: return
        if (bar !in 0 until clock.bars) return
        // The player's own speed and repeat, to go back to when the note is left (the first of several bars played slowly).
        val slow = beforeSlow
        if (slow == null || speed != PracticeSpeed.SLOW || repeat != slow.second) beforeSlow = PracticePlace(at, speed, repeat) to RepeatBars(bar, bar)
        else beforeSlow = slow.first to RepeatBars(bar, bar)
        speedTo(PracticeSpeed.SLOW)
        repeat(RepeatBars(bar, bar))
        toBar(bar)
        if (!playing) toggle()
    }

    /** The speed and repeat before [playBarSlowly], and the bar it repeats. */
    private var beforeSlow: Pair<PracticePlace, RepeatBars>? = null

    /**
     * The note a bar was played slowly for is left: the speed and repeat the player had come back, unless the player
     * changed them since. The song plays on, or stays paused, where it is.
     */
    fun endSlowly() {
        val (was, bar) = beforeSlow ?: return
        beforeSlow = null
        if (speed != PracticeSpeed.SLOW || repeat != bar) return
        speedTo(was.speed)
        repeat(was.repeat)
    }

    /** Repeats [bars]; null plays on. The song goes to the first of them when it is outside them. */
    fun repeat(bars: RepeatBars?) {
        changes++
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
        val place = PracticePlace(now, speed, repeat)
        left[song] = place
        saved[KEY_SONG] = song
        saved[KEY_AT] = now
        saved[KEY_SPEED] = speed
        saved[KEY_REPEAT] = repeat?.let { intArrayOf(it.first, it.last) }
        // Not before the place kept on the phone was read: what is there is not written over with the defaults.
        val job = job?.takeIf { !unread } ?: return
        viewModelScope.launch(writing) { places.save(job, place) }
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

    /**
     * As a new process would start: nothing in memory and nothing in the saved state, only what is kept on the phone.
     * For the tests (a JVM test can't end the process).
     */
    @VisibleForTesting
    internal fun forgetAllButThePhone() {
        leave()
        left.clear()
        saved.keys().forEach { saved.remove<Any>(it) }
        song = null
        job = null
        at = 0.0; speed = PracticeSpeed.FULL; repeat = null
    }

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
