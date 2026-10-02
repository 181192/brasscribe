package no.brasscribe.play.fret

import android.content.Context
import android.net.Uri
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.PlayerMessage
import java.io.File

/**
 * The recording as the sound of the tab: played from its file at any speed with the pitch kept, from any
 * second, and over a stretch again and again. Used from the main thread only.
 */
interface RecordingPlayer {
    /**
     * The recording is sounding, or about to: asked to play, not at its end, and the phone lets it (a moment of
     * reading the file after a jump is still playing; a phone call that takes the sound away for a while is not).
     */
    val playing: Boolean

    /** It was asked to play and has not been paused, whether or not the phone lets it sound now. */
    val asked: Boolean

    /** Where the recording is, in seconds. */
    val position: Double

    /** How long the recording is, in seconds; 0 until it has been read. */
    val duration: Double

    /** 1 is the recording's own speed. The pitch is the recording's at every speed. */
    var speed: Float

    /** The stretch to play again and again, in seconds; null plays on to the end. */
    var repeat: ClosedFloatingPointRange<Double>?

    fun play()
    fun pause()
    fun seekTo(seconds: Double)
    fun release()

    /** What the screen is told of: playing began or stopped, the end was reached, or the file cannot be played. */
    interface Listener {
        fun onPlaying(playing: Boolean)
        fun onEnded()
        fun onFailed()
    }
}

/**
 * [RecordingPlayer] on Media3's ExoPlayer: it reads what the phone's own decoders read (the files the app
 * takes in), stretches time without moving the pitch, and seeks to the millisecond. It asks for the
 * audio focus, and pauses when headphones are pulled out.
 */
@OptIn(UnstableApi::class)
class MediaRecordingPlayer(context: Context, file: File, private val listener: RecordingPlayer.Listener, silent: Boolean = false) : RecordingPlayer {
    private val player: ExoPlayer = ExoPlayer.Builder(context.applicationContext).setLooper(Looper.getMainLooper()).build()
    private var turn: PlayerMessage? = null

    init {
        player.setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true)
        player.setHandleAudioBecomingNoisy(true)
        if (silent) player.volume = 0f
        player.addListener(object : Player.Listener {
            // Pause and play; headphones pulled out (the player pauses itself); and the phone taking the sound away for
            // a while (a call, another app's announcement): the player stays asked to play and goes on by itself after,
            // but nothing sounds meanwhile, so it is not playing.
            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) = tell()
            override fun onPlaybackSuppressionReasonChanged(playbackSuppressionReason: Int) = tell()

            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) {
                    // A stretch that reaches the end of the recording turns here, when it starts before that end (one that
                    // starts past it would end again at once, for ever); else the recording has been played.
                    val again = repeat
                    if (again != null && player.playWhenReady && turnsBack(again.start, duration)) seekTo(again.start)
                    else { player.playWhenReady = false; listener.onEnded() }
                }
                tell()
            }

            override fun onPlayerError(error: PlaybackException) {
                android.util.Log.w(no.brasscribe.play.PlayViewModel.TAG, "the recording cannot be played", error)
                listener.onFailed()
            }
        })
        player.setMediaItem(MediaItem.fromUri(Uri.fromFile(file)))
        player.prepare()
    }

    override val playing: Boolean
        get() = player.playWhenReady && player.playbackSuppressionReason == Player.PLAYBACK_SUPPRESSION_REASON_NONE &&
            player.playbackState != Player.STATE_ENDED && player.playbackState != Player.STATE_IDLE
    override val asked: Boolean get() = player.playWhenReady

    private var told = false

    /** Tells the listener when [playing] has changed. */
    private fun tell() {
        val now = playing
        if (now == told) return
        told = now
        listener.onPlaying(now)
    }
    override val position: Double get() = player.currentPosition / 1000.0
    override val duration: Double get() = player.duration.takeIf { it != C.TIME_UNSET }?.let { it / 1000.0 } ?: 0.0

    override var speed: Float = 1f
        set(value) {
            field = value
            // Pitch 1: the speed changes, the notes stay where they are.
            player.playbackParameters = PlaybackParameters(value, 1f)
        }

    override var repeat: ClosedFloatingPointRange<Double>? = null
        set(value) {
            field = value
            turn?.cancel()
            turn = value?.let { stretch ->
                // Told on the playback thread at the stretch's last millisecond, every time it is reached.
                player.createMessage { _, _ -> if (repeat == stretch) seekTo(stretch.start) }
                    .setLooper(Looper.getMainLooper())
                    .setPosition((stretch.endInclusive * 1000).toLong().coerceAtLeast(1))
                    .setDeleteAfterDelivery(false)
                    .send()
            }
        }

    override fun play() {
        if (player.playbackState == Player.STATE_IDLE) player.prepare()
        if (player.playbackState == Player.STATE_ENDED) seekTo(repeat?.start?.takeIf { turnsBack(it, duration) } ?: 0.0)
        player.playWhenReady = true
    }

    override fun pause() {
        player.playWhenReady = false
    }

    override fun seekTo(seconds: Double) = player.seekTo(TabClock.millisAt(seconds))

    override fun release() {
        turn?.cancel()
        player.release()
    }

    /** The pitch factor the player runs at, for the test that slows it down: 1 is the recording's own. */
    val pitch: Float get() = player.playbackParameters.pitch
}
