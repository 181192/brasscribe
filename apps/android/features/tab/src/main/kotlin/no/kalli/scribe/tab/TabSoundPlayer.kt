package no.kalli.scribe.tab

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * The tab's own sound on the phone: a [TabSynth] rendered on a thread of its own into the phone's sound
 * output, on the recording's time, so it is played, slowed down, moved and repeated as the recording is
 * ([RecordingPlayer]). It can also count a bar in before the song moves, and tick the beats.
 *
 * [voices] makes the instrument on the sound thread (reading a SoundFont takes a moment). Everything else
 * is used from the main thread only.
 */
class TabSoundPlayer(
    context: Context,
    score: TabSoundScore,
    voices: () -> TabVoices,
    private val listener: RecordingPlayer.Listener,
    silent: Boolean = false,
    /** Told once the instrument is made and the sound can be heard. */
    private val onReady: () -> Unit = {},
) : RecordingPlayer {
    private val app = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val commands = ConcurrentLinkedQueue<(TabSynth) -> Unit>()
    private val lock = Object()
    private val end = score.end

    // What the sound thread last rendered, read together under [told]: where the song is after it, the frames written
    // since the output was last emptied, whether a bar is being counted in and the frame its count ended at, the turns
    // of the stretch (and how many there were at the last jump), and the speed it ran at.
    private val told = Object()
    private var toldPosition = 0.0
    private var toldWritten = 0L
    private var toldCounting = false
    private var toldCountedBy = 0L
    private var toldTurns = 0
    private var toldTurnsAtJump = 0
    private var toldSpeed = 1.0

    // The sound thread's own: the frames written since the output was last emptied, and the frame a count-in ended at.
    private var written = 0L
    private var countedBy = 0L
    private var turned = 0

    @Volatile private var running = false
    @Volatile private var released = false
    private var at = 0.0

    /** Times the sound was moved while it played: each one stops every note that rings. */
    @Volatile var jumps = 0
        private set

    private val track = AudioTrack.Builder()
        .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
        .setAudioFormat(AudioFormat.Builder().setSampleRate(RATE).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).build())
        .setTransferMode(AudioTrack.MODE_STREAM)
        .setBufferSizeInBytes(maxOf(AudioTrack.getMinBufferSize(RATE, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT), (QUEUE + FRAMES) * 4))
        .build().also { if (silent) it.setVolume(0f) }

    /** Says what was rendered, for the main thread to read. */
    private fun tell(synth: TabSynth, jumped: Boolean = false) = synchronized(told) {
        toldPosition = synth.position
        toldWritten = written
        toldCounting = synth.countingIn
        toldCountedBy = countedBy
        toldTurns = synth.turns
        if (jumped) toldTurnsAtJump = synth.turns
        toldSpeed = synth.speed
    }

    /** Empties the output: what was rendered ahead is dropped, and the frames are counted from here. On the sound thread. */
    private fun empty() {
        track.pause()
        track.flush()
        written = 0
        countedBy = 0
    }

    private val thread = Thread({
        // As a sound thread is run: ahead of the app's other work.
        runCatching { android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_AUDIO) }
        val synth = try {
            TabSynth(score, voices(), RATE)
        } catch (e: Exception) {
            android.util.Log.w(TAG, "the tab's sound could not be made", e)
            main.post { if (!released) listener.onFailed() }
            return@Thread
        }
        main.post { if (!released) onReady() }
        val block = FloatArray(FRAMES * 2)
        val bytes = ByteBuffer.allocateDirect(FRAMES * 4).order(ByteOrder.nativeOrder())
        while (!released) {
            while (true) (commands.poll() ?: break)(synth)
            if (!running) {
                synchronized(lock) { if (!running && !released && commands.isEmpty()) lock.wait() }
                continue
            }
            // No more than a moment of sound is rendered ahead, so a change is heard at once.
            if (written - head() > QUEUE) {
                Thread.sleep(4)
                continue
            }
            val wasCounting = synth.countingIn
            val more = synth.render(block, FRAMES)
            TabSoundLevel.process(block)
            bytes.clear()
            for (v in block) bytes.putShort((v * Short.MAX_VALUE).toInt().toShort())
            bytes.flip()
            track.write(bytes, bytes.remaining(), AudioTrack.WRITE_BLOCKING)
            written += FRAMES
            if (wasCounting && !synth.countingIn) countedBy = written
            // (A turn of the stretch is told when it is rendered, a moment before it is heard.)
            if (synth.turns != turned) { turned = synth.turns; main.post { if (asked) listener.onTurned() } }
            tell(synth)
            if (!more) {
                // The end of the tab: what is rendered plays out, then the song has ended.
                while (running && !released && head() < written) Thread.sleep(4)
                if (running && !released) main.post { if (asked) ended() }
                running = false
            }
        }
    }, "tab-sound").also { it.start() }

    /** Frames the output has taken. */
    private fun head(): Long = track.playbackHeadPosition.toLong() and 0xFFFFFFFFL

    private val stamp = android.media.AudioTimestamp()

    /** Frames that have been heard: the output says when it presents a frame, where it can; else as many as it has taken. */
    private fun heard(): Long {
        val taken = head()
        // (An output that has no word on it yet says frame 0: then it is as many as it has taken.)
        if (!track.getTimestamp(stamp) || stamp.framePosition <= 0) return taken
        val since = (System.nanoTime() - stamp.nanoTime).coerceAtLeast(0)
        val presented = stamp.framePosition + since * RATE / 1_000_000_000L
        // More than a second behind what was taken is not a delay of the output's: the word is an old one.
        return if (presented in taken - RATE..taken) presented else taken
    }

    private fun ask(command: (TabSynth) -> Unit) {
        commands += command
        synchronized(lock) { lock.notifyAll() }
    }

    override var asked = false
        private set
    override val playing: Boolean get() = asked

    /** A count-in is still heard: the song has not started to move. */
    val countingIn: Boolean get() = asked && synchronized(told) { !running || toldCounting || heard() < toldCountedBy }

    /** Times the stretch being repeated has turned back to its start. */
    val turns: Int get() = synchronized(told) { toldTurns }

    override val position: Double
        get() {
            if (!asked || !running || moving) return at
            synchronized(told) {
                if (toldWritten == 0L || toldCounting) return at
                // What is heard now was rendered a moment ago.
                var heard = toldPosition - (toldWritten - heard()).coerceAtLeast(0) / RATE.toDouble() * toldSpeed
                // Rendered past a turn of the stretch that has not been heard yet: the song is still before its end.
                val again = repeat
                if (again != null && heard < again.start && toldTurns > toldTurnsAtJump) heard += again.endInclusive - again.start
                return heard.coerceIn(minOf(at, toldPosition), maxOf(end, at))
            }
        }

    override val duration: Double get() = end

    override var speed: Float = 1f
        set(value) {
            field = value
            ask { it.speed = value * trim }
        }

    /**
     * A little faster or slower than [speed] (1: as it is), to come back beside a recording it plays along with
     * without a jump: the notes come a little sooner or later, at their own pitch.
     */
    var trim: Double = 1.0
        set(value) {
            if (value == field) return
            field = value
            val s = speed
            ask { it.speed = s * value }
        }

    override var repeat: ClosedFloatingPointRange<Double>? = null
        set(value) {
            field = value
            ask { it.repeat = value }
        }

    /** The notes sound; without them only the count-in and the metronome do. */
    var notes = true
        set(value) {
            field = value
            ask { it.notes = value }
        }

    /** The beats tick. */
    var metronome = false
        set(value) {
            field = value
            ask { it.metronome = value }
        }

    /** It asks the phone for the sound itself (it plays alone); when it plays along with the recording, the recording has asked. */
    var ownsFocus = true

    /** The next [play] counts in first: [beats] clicks, [beatSeconds] apart at the recording's own speed. */
    fun countIn(beats: Int, beatSeconds: Double) = ask {
        it.countIn(beats, beatSeconds)
        tell(it)
    }

    override fun play() {
        if (asked || released) return
        if (ownsFocus && !focus(true)) return
        if (at >= end - 0.05 && repeat == null) seekTo(0.0)
        asked = true
        ask {
            track.play()
            running = true
        }
        listener.onPlaying(true)
    }

    override fun pause() {
        if (!asked) return
        at = position
        asked = false
        halt(at)
        if (ownsFocus) focus(false)
        listener.onPlaying(false)
    }

    private fun ended() {
        at = end
        asked = false
        halt(at)
        if (ownsFocus) focus(false)
        listener.onEnded()
    }

    /** Stops the sound at once, with the song at [seconds]: what was rendered ahead is dropped. */
    private fun halt(seconds: Double) = ask {
        running = false
        empty()
        it.seek(seconds)
        tell(it, jumped = true)
    }

    /** A move has been asked for and the sound thread has not made it yet: the song is where it was put. */
    @Volatile private var moving = false

    override fun seekTo(seconds: Double) {
        at = seconds.coerceAtLeast(0.0)
        val to = at
        moving = true
        ask {
            // While it plays, what was rendered ahead from the old place is dropped: the new place is heard at once.
            val playing = running
            if (playing) { empty(); jumps++ }
            it.seek(to)
            tell(it, jumped = true)
            if (to == at) moving = false
            if (playing) track.play()
        }
    }

    override fun release() {
        if (released) return
        if (asked && ownsFocus) focus(false)
        asked = false
        released = true
        running = false
        synchronized(lock) { lock.notifyAll() }
        main.removeCallbacksAndMessages(null)
        runCatching { app.unregisterReceiver(noisy) }
        // The sound thread lets go of the output when it has written its last block.
        Thread({
            thread.join(2_000)
            runCatching { track.pause(); track.flush() }
            track.release()
        }, "tab-sound-release").start()
    }

    // Headphones pulled out: the sound stops, as the recording's does.
    private val noisy = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (asked) pause()
        }
    }

    private val manager = app.getSystemService(AudioManager::class.java)
    private val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
        .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
        // Another app's sound, or a call: the tab's sound stops, and the player starts it again.
        .setOnAudioFocusChangeListener({ change -> if (change < 0 && asked) pause() }, main)
        .build()

    private fun focus(take: Boolean): Boolean =
        if (take) manager.requestAudioFocus(request) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        else { manager.abandonAudioFocusRequest(request); true }

    init {
        app.registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY), Context.RECEIVER_NOT_EXPORTED)
    }

    companion object {
        /** Frames a second. */
        const val RATE = 44_100
        /** Frames rendered at a time. */
        private const val FRAMES = 1024
        /** Frames rendered ahead of what is heard, at most: about a fifteenth of a second. */
        private const val QUEUE = 3072
    }
}
