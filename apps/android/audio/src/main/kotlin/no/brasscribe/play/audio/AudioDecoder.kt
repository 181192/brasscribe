package no.brasscribe.play.audio

import android.content.Context
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import java.nio.ByteOrder

/** What an imported file held. */
data class DecodedMedia(val audio: PcmAudio, val mime: String, val hasVideo: Boolean, val durationS: Double)

class UnsupportedMediaException(message: String) : Exception(message)

/**
 * Decodes the first audio track of an audio or video file (anything MediaExtractor opens: MP3, AAC,
 * M4A, FLAC, Ogg, WAV, MP4, MKV, WebM, 3GP) to mono float PCM with MediaCodec.
 */
object AudioDecoder {
    private const val TIMEOUT_US = 10_000L

    fun decode(context: Context, uri: Uri, onProgress: (Double) -> Unit = {}): DecodedMedia {
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
            val codec = try {
                MediaCodec.createDecoderByType(mime)
            } catch (e: Exception) {
                throw UnsupportedMediaException("no decoder for $mime")
            }
            codec.configure(format, null, null, 0)
            codec.start()
            var sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            var channels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            var encoding = AudioFormat.ENCODING_PCM_16BIT
            val out = FloatBuilder()
            val info = MediaCodec.BufferInfo()
            var inputDone = false
            var outputDone = false
            try {
                while (!outputDone) {
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
                            sampleRate = f.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                            channels = f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                            if (f.containsKey(MediaFormat.KEY_PCM_ENCODING)) encoding = f.getInteger(MediaFormat.KEY_PCM_ENCODING)
                        }
                        outIndex >= 0 -> {
                            val buf = codec.getOutputBuffer(outIndex)!!.order(ByteOrder.nativeOrder())
                            buf.position(info.offset)
                            buf.limit(info.offset + info.size)
                            if (encoding == AudioFormat.ENCODING_PCM_FLOAT) {
                                val fb = buf.asFloatBuffer()
                                val frame = FloatArray(channels)
                                while (fb.remaining() >= channels) { fb.get(frame); out.add(frame.average().toFloat()) }
                            } else {
                                val sb = buf.asShortBuffer()
                                while (sb.remaining() >= channels) {
                                    var sum = 0
                                    repeat(channels) { sum += sb.get() }
                                    out.add(sum / (32768f * channels))
                                }
                            }
                            codec.releaseOutputBuffer(outIndex, false)
                            if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outputDone = true
                        }
                    }
                }
            } finally {
                codec.stop()
                codec.release()
            }
            val audio = PcmAudio(out.toArray(), sampleRate)
            onProgress(1.0)
            return DecodedMedia(audio, mime, hasVideo, if (durationUs > 0) durationUs / 1e6 else audio.seconds)
        } finally {
            extractor.release()
        }
    }

    private fun FloatArray.average(): Double = if (isEmpty()) 0.0 else sum().toDouble() / size
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

    fun toArray(): FloatArray = data.copyOf(size)
}
