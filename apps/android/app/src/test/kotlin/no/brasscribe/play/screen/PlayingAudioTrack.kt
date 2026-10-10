package no.brasscribe.play.screen

import android.media.AudioTrack
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements
import org.robolectric.annotation.RealObject
import org.robolectric.shadows.ShadowAudioTrack

/**
 * An AudioTrack on the JVM that plays its sound out at its sample rate, by the clock on the wall, as a phone's does.
 *
 * Robolectric's own takes every byte at once and counts it as played: its playback head is at the end of what it was
 * given. A player that writes ahead (Media3's ExoPlayer) then has its place at the end of all it has read for a moment
 * after each jump, which on the JVM is often the end of the recording, and a song repeating its bars turns back from
 * there a second time. Here the head moves on from where it is while the track plays, never past what it was given;
 * it stands still while the track is paused, and goes back to 0 when the track is flushed. A stopped track plays out
 * what it holds, as a stopped stream does.
 */
@Implements(AudioTrack::class)
class PlayingAudioTrack : ShadowAudioTrack() {
    @RealObject private lateinit var track: AudioTrack

    private var head = 0L
    /** When the head was last moved on while playing (System.nanoTime), or -1 while paused. */
    private var since = -1L

    /** Moves the head on by the time since it was last moved, up to what the track was given. */
    @Synchronized
    private fun advance(): Long {
        val now = System.nanoTime()
        if (since >= 0) head = minOf(super.getPlaybackHeadPosition().toLong(), head + (now - since) * track.sampleRate / 1_000_000_000L)
        if (since >= 0) since = now
        return head
    }

    @Implementation
    override fun getPlaybackHeadPosition(): Int = advance().toInt()

    @Implementation
    @Synchronized
    protected fun native_start() {
        advance()
        if (since < 0) since = System.nanoTime()
    }

    @Implementation
    @Synchronized
    protected fun native_pause() {
        advance()
        since = -1
    }

    @Implementation
    @Synchronized
    override fun flush() {
        super.flush()
        head = 0
        if (since >= 0) since = System.nanoTime()
    }
}
