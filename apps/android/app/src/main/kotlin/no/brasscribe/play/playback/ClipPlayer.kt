package no.brasscribe.play.playback

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import no.brasscribe.play.audio.PcmAudio

/**
 * Loops short clips ("Listen to this bar": the original bar, a short gap, then the score's bar) with a
 * static AudioTrack. Only one clip plays at a time.
 */
class ClipPlayer {
    private var track: AudioTrack? = null

    val playing: Boolean get() = track?.playState == AudioTrack.PLAYSTATE_PLAYING

    fun playLooped(clips: List<PcmAudio>, gapS: Double = 0.4) {
        stop()
        if (clips.isEmpty()) return
        val rate = clips.first().sampleRate
        val gap = FloatArray((gapS * rate).toInt())
        val joined = clips.flatMap { c ->
            val samples = if (c.sampleRate == rate) c.samples else resampleLinear(c.samples, c.sampleRate, rate)
            listOf(samples, gap)
        }
        val total = joined.sumOf { it.size }
        if (total == 0) return
        val data = FloatArray(total)
        var at = 0
        for (part in joined) { System.arraycopy(part, 0, data, at, part.size); at += part.size }
        val t = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_FLOAT).setSampleRate(rate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(total * 4)
            .build()
        t.write(data, 0, total, AudioTrack.WRITE_BLOCKING)
        t.setLoopPoints(0, total, -1)
        t.play()
        track = t
    }

    fun stop() {
        track?.run { runCatching { stop() }; release() }
        track = null
    }

    private fun resampleLinear(x: FloatArray, from: Int, to: Int): FloatArray {
        val n = (x.size.toLong() * to / from).toInt()
        return FloatArray(n) { i ->
            val pos = i.toDouble() * from / to
            val a = pos.toInt().coerceAtMost(x.size - 1)
            val b = (a + 1).coerceAtMost(x.size - 1)
            val f = (pos - a).toFloat()
            x[a] * (1 - f) + x[b] * f
        }
    }
}
