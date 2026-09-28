package no.brasscribe.play.audio

import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import android.net.Uri
import java.io.File
import java.nio.ByteBuffer

/**
 * An imported file, ready to use: [file] is what goes to the engine (for a video, only its sound),
 * [audio] the decoded mono PCM (null when too long to hold in memory).
 */
data class ImportedMedia(val file: File, val audio: PcmAudio?, val hasVideo: Boolean, val durationS: Double, val mime: String)

/**
 * Brings an audio or video file in without ever holding the file in memory.
 *
 * A video's sound track is taken out on the phone before anything else: AAC (almost every phone
 * and camera video) is copied into an .m4a sample by sample, without re-encoding; any other codec
 * is decoded once into a mono WAV on disk. The engine then gets a few MB instead of the video.
 * An audio file is copied as it is. Either way the PCM is decoded from the local file a buffer at a time.
 */
object MediaImport {
    private const val AAC = "audio/mp4a-latm"
    private const val DEFAULT_SAMPLE_BUFFER = 1 shl 20

    /** Progress phases; [onProgress] receives the phase and its fraction. */
    enum class Phase { COPY, EXTRACT, DECODE }

    /**
     * Reads [uri] (a picked content Uri or a file) straight through MediaExtractor when the provider
     * allows it, and copies it into [dir] first when it doesn't. [dir] holds the result.
     */
    fun import(
        context: Context, uri: Uri, name: String, dir: File,
        onProgress: (Phase, Double) -> Unit = { _, _ -> },
    ): ImportedMedia {
        dir.mkdirs()
        val safe = name.replace('/', '_')
        val base = safe.substringBeforeLast('.').ifBlank { "import" }
        val tracks = runCatching { probe(context, uri) }.getOrNull()
        var copy: File? = null
        // Some providers give a stream but no seekable descriptor: copy the file first (a buffer at a time).
        val readable = if (tracks != null) uri else {
            copy = dir.resolve(safe).also { f -> copyTo(context, uri, f) { onProgress(Phase.COPY, it) } }
            Uri.fromFile(copy)
        }
        val (hasAudio, hasVideo) = tracks ?: probe(context, readable)
        if (!hasAudio) { copy?.delete(); throw UnsupportedMediaException("no audio track") }
        if (!hasVideo) {
            // An audio file goes to the engine as it is.
            val file = copy ?: dir.resolve(safe).also { f -> copyTo(context, uri, f) { onProgress(Phase.COPY, it) } }
            val decoded = AudioDecoder.decode(context, Uri.fromFile(file), { onProgress(Phase.DECODE, it) })
            return ImportedMedia(file, decoded.audio, false, decoded.durationS, decoded.mime)
        }
        try {
            val m4a = dir.resolve("$base.m4a")
            if (remuxAac(context, readable, m4a) { onProgress(Phase.EXTRACT, it) }) {
                val decoded = AudioDecoder.decode(context, Uri.fromFile(m4a), { onProgress(Phase.DECODE, it) })
                return ImportedMedia(m4a, decoded.audio, true, decoded.durationS, decoded.mime)
            }
            // Not AAC, or the muxer refused it: decode once, writing the WAV and keeping the PCM in the same pass.
            val wavFile = dir.resolve("$base.wav")
            val decoded = WavWriter(wavFile, 44100).use { w ->
                AudioDecoder.decode(context, readable, { onProgress(Phase.EXTRACT, it) }, wav = w)
            }
            return ImportedMedia(wavFile, decoded.audio, true, decoded.durationS, decoded.mime)
        } finally {
            copy?.delete()
        }
    }

    /** (has an audio track, has a video track), or an exception when the file can't be opened. */
    fun probe(context: Context, uri: Uri): Pair<Boolean, Boolean> {
        val ex = MediaExtractor()
        try {
            ex.setDataSource(context, uri, null)
            var audio = false
            var video = false
            for (i in 0 until ex.trackCount) {
                val mime = ex.getTrackFormat(i).getString(MediaFormat.KEY_MIME).orEmpty()
                if (mime.startsWith("audio/")) audio = true
                if (mime.startsWith("video/")) video = true
            }
            return audio to video
        } finally {
            ex.release()
        }
    }

    private fun copyTo(context: Context, uri: Uri, out: File, onProgress: (Double) -> Unit) {
        val total = runCatching { context.contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } }.getOrNull() ?: -1L
        val input = context.contentResolver.openInputStream(uri) ?: throw java.io.IOException("the file could not be opened")
        input.use { i ->
            out.outputStream().use { o ->
                val buf = ByteArray(1 shl 16)
                var done = 0L
                while (true) {
                    val n = i.read(buf)
                    if (n < 0) break
                    o.write(buf, 0, n)
                    done += n
                    if (total > 0) onProgress((done.toDouble() / total).coerceIn(0.0, 1.0))
                }
            }
        }
    }

    /**
     * Copies the first audio track into [out] as MPEG-4 audio when it is AAC. Returns false (and
     * leaves no file) when it is another codec or the muxer refuses the track.
     */
    fun remuxAac(context: Context, uri: Uri, out: File, onProgress: (Double) -> Unit = {}): Boolean {
        val ex = MediaExtractor()
        var muxer: MediaMuxer? = null
        var started = false
        try {
            ex.setDataSource(context, uri, null)
            val track = (0 until ex.trackCount).firstOrNull {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME).orEmpty().startsWith("audio/")
            } ?: return false
            val format = ex.getTrackFormat(track)
            if (format.getString(MediaFormat.KEY_MIME) != AAC) return false
            val durationUs = if (format.containsKey(MediaFormat.KEY_DURATION)) format.getLong(MediaFormat.KEY_DURATION) else 0L
            ex.selectTrack(track)
            val m = MediaMuxer(out.path, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4).also { muxer = it }
            val outTrack = m.addTrack(format)
            m.start()
            started = true
            val capacity = if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE).coerceAtLeast(8192)
                else DEFAULT_SAMPLE_BUFFER
            var buffer = ByteBuffer.allocateDirect(capacity)
            val info = MediaCodec.BufferInfo()
            var first = Long.MIN_VALUE
            var last = -1L
            var samples = 0
            while (true) {
                if (ex.sampleSize > buffer.capacity()) buffer = ByteBuffer.allocateDirect(ex.sampleSize.toInt())
                val size = ex.readSampleData(buffer, 0)
                if (size < 0) break
                val t = ex.sampleTime
                if (first == Long.MIN_VALUE) first = t
                // Starts at 0 and never runs backwards, which MPEG-4 requires.
                val pts = maxOf(t - first, last)
                last = pts
                info.set(0, size, pts, MediaCodec.BUFFER_FLAG_KEY_FRAME)
                m.writeSampleData(outTrack, buffer, info)
                samples++
                if (durationUs > 0 && samples % 64 == 0) onProgress((t.toDouble() / durationUs).coerceIn(0.0, 1.0))
                ex.advance()
            }
            m.stop()
            started = false
            onProgress(1.0)
            return samples > 0 || run { out.delete(); false }
        } catch (e: Exception) {
            android.util.Log.w("BrasscribePlay", "AAC remux failed; decoding to WAV instead", e)
            runCatching { if (started) muxer?.stop() }
            out.delete()
            return false
        } finally {
            runCatching { muxer?.release() }
            ex.release()
        }
    }
}
