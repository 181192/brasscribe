package no.brasscribe.play.audio

import android.content.Context
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import java.nio.ByteOrder

/**
 * What an imported file held. [audio] is null when the sound is too long to hold in memory (more
 * than [AudioDecoder.maxSamplesInMemory]); the file itself can still go to the engine.
 */
data class DecodedMedia(val audio: PcmAudio?, val mime: String, val hasVideo: Boolean, val durationS: Double)

class UnsupportedMediaException(message: String) : Exception(message)

/**
 * Decodes the first audio track of an audio or video file (anything MediaExtractor opens: MP3, AAC,
 * M4A, FLAC, Ogg, WAV, MP4, MKV, WebM, 3GP) to mono float PCM with MediaCodec. The file is read a
 * sample at a time; only the decoded mono PCM is kept, and only up to the sample limit.
 */
object AudioDecoder {
    private const val TIMEOUT_US = 10_000L

    /**
     * Mono samples one import may hold in memory: a sixth of the heap (the builder and its trimmed
     * copy briefly hold two). A 512 MB heap holds about 7 minutes at 48 kHz.
     */
    val maxSamplesInMemory: Int
        get() = (Runtime.getRuntime().maxMemory() / 6 / 4).coerceAtMost(Int.MAX_VALUE - 8L).toInt()

    /**
     * [wav], when given, receives every mono sample as it is decoded (a WAV written to disk as it
     * goes), so the whole track is decoded even when it is too long to keep in memory. Without it,
     * decoding stops once the track is known to be longer than [maxSamples].
     */
    fun decode(
        context: Context, uri: Uri, onProgress: (Double) -> Unit = {},
        maxSamples: Int = maxSamplesInMemory, wav: WavWriter? = null,
    ): DecodedMedia {
        val extractor = MediaExtractor()
        try {
            extractor.setDataSource(context, uri, null)
            var audioTrack = -1
            var hasVideo = false
            for (i in 0 until extractor.trackCount) {
                val mime = extractor.getTrackFormat(i).getString(MediaFormat.KEY_MIME).orEmpty()
                if (mime.startsWith("audio/") && audioTrack < 0) audioTrack = i
                if (mime.startsWith("video/")) hasVideo = true
            }
            if (audioTrack < 0) throw UnsupportedMediaException("no audio track")
            extractor.selectTrack(audioTrack)
            val format = extractor.getTrackFormat(audioTrack)
            val mime = format.getString(MediaFormat.KEY_MIME)!!
            val durationUs = if (format.containsKey(MediaFormat.KEY_DURATION)) format.getLong(MediaFormat.KEY_DURATION) else 0L
            var sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            var channels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            wav?.sampleRate = sampleRate
            fun expected(rate: Int): Long = if (durationUs > 0) durationUs * rate / 1_000_000L else -1L
            // Known to be too long before a sample is decoded: say so without decoding it.
            if (wav == null && expected(sampleRate) > maxSamples) {
                return DecodedMedia(null, mime, hasVideo, durationUs / 1e6)
            }
            val codec = try {
                MediaCodec.createDecoderByType(mime)
            } catch (e: Exception) {
                throw UnsupportedMediaException("no decoder for $mime")
            }
            codec.configure(format, null, null, 0)
            codec.start()
            var encoding = AudioFormat.ENCODING_PCM_16BIT
            // Sized from the duration up front (plus a second): doubling a large array briefly holds three copies.
            fun capacity(rate: Int): Int = expected(rate).let { if (it < 0) 1 shl 16 else (it + rate).coerceIn(1024L, maxSamples.toLong()).toInt() }
            var out: FloatBuilder? = if (expected(sampleRate) > maxSamples) null else FloatBuilder(capacity(sampleRate))
            var decodedSamples = 0L
            val info = MediaCodec.BufferInfo()
            var inputDone = false
            var outputDone = false
            fun add(v: Float) {
                wav?.write(v)
                decodedSamples++
                val o = out ?: return
                if (o.size >= maxSamples) out = null else o.add(v)
            }
            try {
                while (!outputDone) {
                    if (out == null && wav == null) break
                    if (!inputDone) {
                        val inIndex = codec.dequeueInputBuffer(TIMEOUT_US)
                        if (inIndex >= 0) {
                            val buf = codec.getInputBuffer(inIndex)!!
                            val size = extractor.readSampleData(buf, 0)
                            if (size < 0) {
                                codec.queueInputBuffer(inIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                inputDone = true
                            } else {
                                codec.queueInputBuffer(inIndex, 0, size, extractor.sampleTime, 0)
                                if (durationUs > 0) onProgress((extractor.sampleTime.toDouble() / durationUs).coerceIn(0.0, 1.0))
                                extractor.advance()
                            }
                        }
                    }
                    val outIndex = codec.dequeueOutputBuffer(info, TIMEOUT_US)
                    when {
                        outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                            val f = codec.outputFormat
                            val rate = f.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                            channels = f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                            if (f.containsKey(MediaFormat.KEY_PCM_ENCODING)) encoding = f.getInteger(MediaFormat.KEY_PCM_ENCODING)
                            if (rate != sampleRate) {
                                // HE-AAC (SBR) decodes at twice the container's rate.
                                sampleRate = rate
                                wav?.sampleRate = rate
                                out = if (expected(rate) > maxSamples) null else out?.apply { ensureCapacity(capacity(rate)) }
                            }
                        }
                        outIndex >= 0 -> {
                            val buf = codec.getOutputBuffer(outIndex)!!.order(ByteOrder.nativeOrder())
                            buf.position(info.offset)
                            buf.limit(info.offset + info.size)
                            if (encoding == AudioFormat.ENCODING_PCM_FLOAT) {
                                val fb = buf.asFloatBuffer()
                                while (fb.remaining() >= channels) {
                                    var sum = 0f
                                    repeat(channels) { sum += fb.get() }
                                    add(sum / channels)
                                }
                            } else {
                                val sb = buf.asShortBuffer()
                                while (sb.remaining() >= channels) {
                                    var sum = 0
                                    repeat(channels) { sum += sb.get() }
                                    add(sum / (32768f * channels))
                                }
                            }
                            codec.releaseOutputBuffer(outIndex, false)
                            if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outputDone = true
                        }
                    }
                }
            } finally {
                runCatching { codec.stop() }
                codec.release()
            }
            val audio = out?.let { PcmAudio(it.toArray(), sampleRate) }
            onProgress(1.0)
            val seconds = if (durationUs > 0) durationUs / 1e6 else decodedSamples.toDouble() / sampleRate
            return DecodedMedia(audio, mime, hasVideo, seconds)
        } finally {
            extractor.release()
        }
    }
}

/** Growable float array without boxing. */
class FloatBuilder(initial: Int = 1 shl 16) {
    private var data = FloatArray(initial)
    var size = 0
        private set

    fun add(v: Float) {
        if (size == data.size) data = data.copyOf(data.size * 2)
        data[size++] = v
    }

    fun addAll(src: FloatArray, n: Int) {
        while (size + n > data.size) data = data.copyOf(data.size * 2)
        System.arraycopy(src, 0, data, size, n)
        size += n
    }

    fun ensureCapacity(n: Int) {
        if (n > data.size) data = data.copyOf(n)
    }

    /** The samples; the backing array itself when it is exactly full, so no second copy is made. */
    fun toArray(): FloatArray = if (size == data.size) data else data.copyOf(size)
}
