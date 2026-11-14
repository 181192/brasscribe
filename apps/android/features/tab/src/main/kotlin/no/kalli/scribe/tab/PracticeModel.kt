package no.kalli.scribe.tab

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
import no.kalli.scribe.engine.EngineApi
import no.kalli.scribe.engine.EngineException
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
    /** The computer was not asked: this app is older than its Bandroom. */
    UPDATE_APP,
    /** The computer was not asked: its Bandroom is older than this app. */
    UPDATE_COMPUTER,
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
         * (no room, or the file could not be written); the computer was not asked because one of the two needs an
         * update; or the computer was not reached.
         */
        fun whyNot(error: Throwable, room: Long): RecordingState = when {
            error is no.kalli.scribe.engine.InterfaceMismatchException ->
                if (error.update == no.kalli.scribe.engine.InterfaceMatch.UPDATE_APP) RecordingState.UPDATE_APP else RecordingState.UPDATE_COMPUTER
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

/** What is heard in practice. The id is what is kept on the phone. */
enum class PracticeSound(val id: String) {
    /** The recording the tab was written from. */
    RECORDING("recording"),
    /** The tab's own notes, played on the instrument's sound. */
    TAB("tab"),
    /** The recording with the tab's notes over it. */
    BOTH("both"),
}

/** Whether the tab's own sound can be heard. */
enum class TabSoundState {
    /** The tab has no sound of its own: it does not follow the recording's beats, or has no notes. */
    NONE,
    /** The instrument is being made (its SoundFont read). */
    LOADING,
    READY,
    /** The instrument could not be made on this phone. */
    FAILED,
}

/** What the tab's own sound is made from: the page's notes, and the instrument's voices (made on the sound's own thread). */
class TabSoundSource(val index: TabIndex, val voices: () -> TabVoices)

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
        }.onFailure { android.util.Log.w(TAG, "where the song was left could not be kept", it) }
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
    private val choices = app.getSharedPreferences(CHOICES, android.content.Context.MODE_PRIVATE)
    private val main = android.os.Handler(android.os.Looper.getMainLooper())
    private var player: RecordingPlayer? = null
    /** The tab's own sound, when the tab can be followed. */
    private var tabPlayer: TabSoundPlayer? = null
    /** What [tabPlayer] plays: a new page or new beats make a new one. */
    private var tabOf: Pair<TabIndex, TabClock>? = null
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

    /** What the player chose to hear. Without the recording on the phone the tab's own sound is heard, whatever was chosen ([hears]). */
    var sound by mutableStateOf(PracticeSound.entries.firstOrNull { it.id == choices.getString(KEY_SOUND, null) } ?: PracticeSound.RECORDING)
        private set
    /** A bar is counted in before the song plays. */
    var countIn by mutableStateOf(choices.getBoolean(KEY_COUNT_IN, false))
        private set
    /** The beats tick while the song plays. */
    var metronome by mutableStateOf(choices.getBoolean(KEY_METRONOME, false))
        private set
    /** Where the tab's own sound is at: being made, there to play, or not to be had. */
    var tabSoundState by mutableStateOf(TabSoundState.NONE)
        private set

    /** The tab's own sound can be played: the tab follows the recording's beats, and its sound was made. */
    val tabSound: Boolean get() = tabSoundState == TabSoundState.READY
    /** A bar is being counted in: the song has not started to move. */
    var counting by mutableStateOf(false)
        private set

    /** There is something to play: the recording, or the tab's own sound. */
    val canPlay: Boolean get() = recording == RecordingState.HERE || tabSound

    /** What is heard: the choice, as far as there is a recording and a tab sound to play it with. */
    val hears: PracticeSound get() = when {
        !tabSound -> PracticeSound.RECORDING
        recording != RecordingState.HERE -> PracticeSound.TAB
        else -> sound
    }

    /** The player the song's place is read from: the recording when it is heard, else the tab's sound. */
    private val lead: RecordingPlayer? get() = if (hears == PracticeSound.TAB) tabPlayer else player

    /** The tab's sound plays along with the recording: its notes are heard, or its beats. */
    private val along: Boolean get() = tabPlayer != null && lead === player && (hears == PracticeSound.BOTH || metronome)

    /** The second of the recording the song is at. */
    fun now(): Double = lead?.takeIf { playing && !counting }?.position ?: at

    /**
     * The song on screen: [song] names it, [job] is its job on the computer (the recording is kept and fetched
     * by it), [clock] follows the recording in its tab, and [inHand] is the recording's file when the phone
     * sent it. [songs]: the jobs of Your songs, when the list is known; the recordings of the others go.
     */
    fun open(song: String, job: String?, clock: TabClock?, inHand: File?, songs: Set<String>? = null, tab: TabSoundSource? = null) {
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
        voice(tab, clock)
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
        // The tab's own sound was playing in the recording's place: the song goes on in the sound chosen.
        val was = playing
        if (was) halt()
        player = (recordingPlayers?.invoke(file, this) ?: MediaRecordingPlayer(getApplication(), file, this, silent)).also {
            it.speed = speed / 100f
            if (at > 0) it.seekTo(at)
        }
        stretch()
        recording = RecordingState.HERE
        if (was) start(counted = false)
    }

    /** Makes the tab's own sound for the page and beats on screen; the one of another page or other beats goes. */
    private fun voice(tab: TabSoundSource?, clock: TabClock?) {
        val of = if (tab != null && clock != null) tab.index to clock else null
        if (of == tabOf && (tabPlayer != null || of == null)) return
        val was = playing
        if (was) halt()
        tabPlayer?.release()
        tabPlayer = null
        tabOf = of
        tabSoundState = TabSoundState.NONE
        if (tab == null || clock == null) return
        val score = TabSoundScore.of(tab.index, clock)
        if (score.notes.isEmpty()) return
        // The instrument is made on the sound's own thread: until it says so, there is nothing to hear.
        tabSoundState = TabSoundState.LOADING
        lateinit var made: TabSoundPlayer
        made = TabSoundPlayer(getApplication(), score, tab.voices, tabListener, silent) {
            if (tabPlayer === made) tabSoundState = TabSoundState.READY
        }
        made.speed = speed / 100f
        made.seekTo(at)
        tabPlayer = made
        stretch()
    }

    /** What the tab's sound tells: it is listened to when the tab's sound is what the song's place is read from. */
    private val tabListener = object : RecordingPlayer.Listener {
        override fun onPlaying(playing: Boolean) {
            if (lead === tabPlayer && !counting) playingChanged(playing)
        }

        override fun onEnded() {
            if (lead === tabPlayer) endedNow()
        }

        override fun onFailed() {
            val led = lead === tabPlayer
            main.removeCallbacks(follow)
            tabPlayer?.release()
            tabPlayer = null
            tabSoundState = TabSoundState.FAILED
            if (led || counting) { counting = false; playing = false }
        }
    }

    /** Gives the players the seconds of the bars to repeat. */
    private fun stretch() {
        val span = repeat?.let { r -> clock?.span(r) }
        player?.repeat = span
        tabPlayer?.repeat = span
    }

    /** Hears the recording, the tab's own sound, or both. While the song plays it goes on in the new sound. */
    fun hear(sound: PracticeSound) {
        if (sound == this.sound) return
        val was = playing
        if (was) halt()
        this.sound = sound
        choices.edit().putString(KEY_SOUND, sound.id).apply()
        if (was) start(counted = false)
    }

    /** A bar is counted in before the song plays, or not. */
    fun countIn(on: Boolean) {
        countIn = on
        choices.edit().putBoolean(KEY_COUNT_IN, on).apply()
    }

    /** The beats tick while the song plays, or not. */
    fun metronome(on: Boolean) {
        metronome = on
        choices.edit().putBoolean(KEY_METRONOME, on).apply()
        val tab = tabPlayer ?: return
        tab.metronome = on
        // Beside the recording the tab's sound runs only while something of it is heard.
        if (playing && !counting && lead === player) {
            if (along && !tab.asked) join() else if (!along && tab.asked) tab.pause()
        }
    }

    /** Stops what sounds, with the song where it is. */
    private fun halt() {
        val now = now()
        main.removeCallbacks(follow)
        counting = false
        tabPlayer?.pause()
        player?.pause()
        at = now
        playing = false
    }

    /** Plays from where the song is: after a bar counted in when that is chosen ([counted]), in the sound chosen. */
    private fun start(counted: Boolean = countIn) {
        val lead = lead ?: return
        val tab = tabPlayer
        tab?.let {
            it.notes = hears != PracticeSound.RECORDING
            it.metronome = metronome
            it.ownsFocus = lead === it
        }
        val clock = clock
        tab?.trim = 1.0
        if (counted && tab != null && clock != null) {
            // A bar as it is counted where the song is: a bar of six-eight is two beats.
            val bar = clock.placeAt(at).bar
            val (beats, ticks) = TabSoundScore.counted(clock.measure(bar))
            val beat = clock.secondsAt(bar, ticks) - clock.secondsAt(bar)
            tab.seekTo(at)
            tab.countIn(beats, beat)
            counting = true
            playing = true
            tab.play()
            // The count's end is looked for closely from a moment before it is due, so the recording starts on the beat.
            countedBy = android.os.SystemClock.uptimeMillis() + (beats * beat / (speed / 100.0) * 1000).toLong()
            main.postDelayed(follow, FOLLOW_MS)
        } else {
            // The player that was not heard till now is where it was left: it starts where the song is.
            if (Math.abs(lead.position - at) > APART) lead.seekTo(at)
            lead.play()
            if (along) join()
        }
    }

    /** The tab's sound joins the recording where it is. */
    private fun join() {
        val tab = tabPlayer ?: return
        val recording = player ?: return
        tab.ownsFocus = false
        tab.trim = 1.0
        tab.seekTo(recording.position)
        tab.play()
        main.removeCallbacks(follow)
        main.postDelayed(follow, FOLLOW_MS)
    }

    /** When the bar being counted in is due to end, on the phone's clock (uptime, in milliseconds). */
    private var countedBy = 0L

    /**
     * Looked at a few times a second while the tab's sound plays beside the recording, or counts a bar in for it. The
     * recording starts when the bar has been counted (looked for every few milliseconds once that is nearly due). Then
     * the tab's sound is kept where the recording is: it stops when the recording does; heard a little apart, it runs a
     * little faster or slower until the two are together again, so no ringing note is cut; and only heard far apart (the
     * recording was moved) is it moved.
     */
    private val follow: Runnable = object : Runnable {
        override fun run() {
            val tab = tabPlayer ?: return
            val recording = player
            if (counting) {
                if (!tab.asked) { counting = false; playing = false; return }
                if (tab.countingIn) {
                    val due = countedBy - android.os.SystemClock.uptimeMillis()
                    main.postDelayed(this, if (due < 2 * FOLLOW_MS) COUNT_MS else FOLLOW_MS)
                    return
                }
                counting = false
                if (lead === tab) { playingChanged(true); return }
                if (!along) tab.pause()
                recording?.play()
            }
            if (recording == null || lead !== recording || !along) return
            if (!recording.playing) { if (tab.asked) tab.pause(); return }
            if (!tab.asked) { tab.trim = 1.0; tab.seekTo(recording.position); tab.play() }
            else {
                var ahead = tab.position - recording.position
                // Over a stretch being repeated, one of the two may have turned back a moment before the other: they are
                // as far apart as the shorter way round the stretch.
                val turn = repeat?.let { r -> clock?.span(r) }?.let { it.endInclusive - it.start }
                if (turn != null && turn > 2 * APART && Math.abs(ahead) > turn / 2) ahead -= Math.copySign(turn, ahead)
                if (Math.abs(ahead) > APART) { tab.trim = 1.0; tab.seekTo(recording.position) }
                else tab.trim = (1.0 - ahead * PULL).coerceIn(1.0 - MOST, 1.0 + MOST)
            }
            main.removeCallbacks(this)
            main.postDelayed(this, FOLLOW_MS)
        }
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
                android.util.Log.w(TAG, "the recording could not be fetched", e)
                val why = withContext(Dispatchers.IO) { store.dropped(part); PracticeRecordings.whyNot(e, store.room) }
                if (look == looking) recording = why
                null
            }
            if (got != null && look == looking) load(got)
        }
    }

    fun toggle() {
        val p = lead ?: return
        if (playing || p.playing) { halt(); remember(); return }
        // Asked to play while the phone holds the sound back: asked again, from the start of the asking.
        if (p.asked) p.pause()
        // From the end, or from outside the bars being repeated, it starts over.
        val span = repeat?.let { clock?.span(it) }
        val end = clock?.end
        if (span != null && (at < span.start - EDGE || at >= span.endInclusive - EDGE)) seek(span.start)
        else if (end != null && at >= end - EDGE) seek(0.0)
        start()
    }

    fun pause() {
        if (playing || lead?.asked == true) { halt(); remember() }
    }

    private fun seek(seconds: Double) {
        changes++
        val to = seconds.coerceAtLeast(0.0)
        // A bar being counted in is given up: the song plays on from where it is moved to.
        val counted = counting
        if (counted) halt()
        player?.seekTo(to)
        tabPlayer?.seekTo(to)
        at = to
        jumps++
        remember()
        if (counted) start(counted = false)
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
        tabPlayer?.speed = percent / 100f
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
        at = now()
        main.removeCallbacks(follow)
        player?.release()
        player = null
        tabPlayer?.release()
        tabPlayer = null
        tabOf = null
        tabSoundState = TabSoundState.NONE
        counting = false
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

    // What the recording tells is the song's while the recording is what is heard.
    override fun onPlaying(playing: Boolean) {
        if (lead === player && !counting) playingChanged(playing)
    }

    override fun onEnded() {
        if (lead === player) endedNow()
    }

    private fun playingChanged(playing: Boolean) {
        if (!playing) lead?.let { at = it.position }
        this.playing = playing
        if (playing && along) { main.removeCallbacks(follow); main.postDelayed(follow, FOLLOW_MS) }
        if (!playing) { if (lead === player) tabPlayer?.pause(); remember() }
    }

    private fun endedNow() {
        lead?.let { at = it.position }
        if (lead === player) tabPlayer?.pause()
        playing = false
    }

    override fun onFailed() {
        val now = now()
        main.removeCallbacks(follow)
        tabPlayer?.pause()
        player?.release()
        player = null
        counting = false
        playing = false
        at = now
        recording = RecordingState.UNPLAYABLE
    }

    override fun onCleared() = release()

    /**
     * As a new process would start: nothing in memory and nothing in the saved state, only what is kept on the phone.
     * For the tests (a JVM test can't end the process).
     */
    @VisibleForTesting
    fun forgetAllButThePhone() {
        leave()
        left.clear()
        saved.keys().forEach { saved.remove<Any>(it) }
        song = null
        job = null
        at = 0.0; speed = PracticeSpeed.FULL; repeat = null
    }

    /** The player, for the tests that listen to what it does. */
    @get:VisibleForTesting
    val recordingPlayer: RecordingPlayer? get() = player

    /** The tab's own sound, for the tests that listen to what it does. */
    @get:VisibleForTesting
    val tabSoundPlayer: TabSoundPlayer? get() = tabPlayer

    companion object {
        /** How near the end of a stretch counts as its end, in seconds. */
        private const val EDGE = 0.05
        private const val KEY_SONG = "practice.song"
        private const val KEY_AT = "practice.at"
        private const val KEY_SPEED = "practice.speed"
        private const val KEY_REPEAT = "practice.repeat"

        /** The preferences the sound, the count-in and the metronome are kept in: the same for every song. */
        const val CHOICES = "practice_sound"
        private const val KEY_SOUND = "sound"
        private const val KEY_COUNT_IN = "count_in"
        private const val KEY_METRONOME = "metronome"

        /** How often the tab's sound is held against the recording, and the end of a count is looked for once it is nearly due, in milliseconds. */
        private const val FOLLOW_MS = 100L
        private const val COUNT_MS = 4L
        /**
         * How far apart the tab's sound and the recording may be heard, in seconds, before the tab's sound is moved: more
         * than what the two outputs can be apart by themselves (a phone's own delay, a wireless speaker's), so only a
         * move of the recording is followed by a move.
         */
        private const val APART = 0.35
        /** Heard apart by less, the tab's sound runs faster or slower by this much of its speed for each second apart, and by no more than [MOST]. */
        private const val PULL = 1.0
        private const val MOST = 0.05

        /** The tests' own player of a recording, in place of the phone's. */
        @VisibleForTesting
        @Volatile var recordingPlayers: ((File, RecordingPlayer.Listener) -> RecordingPlayer)? = null

        /** The tests play without sound. */
        @VisibleForTesting
        @Volatile var silent = false
    }
}
