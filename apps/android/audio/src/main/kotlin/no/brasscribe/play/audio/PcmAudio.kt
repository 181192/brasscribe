package no.brasscribe.play.audio

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.roundToInt

/** Mono float audio in memory. */
class PcmAudio(val samples: FloatArray, val sampleRate: Int) {
    val seconds: Double get() = samples.size.toDouble() / sampleRate

    fun peak(): Float = samples.maxOfOrNull { abs(it) } ?: 0f

    /** A section in seconds, clamped to the recording. */
    fun slice(fromS: Double, toS: Double): PcmAudio {
        val a = (fromS * sampleRate).roundToInt().coerceIn(0, samples.size)
        val b = (toS * sampleRate).roundToInt().coerceIn(a, samples.size)
        return PcmAudio(samples.copyOfRange(a, b), sampleRate)
    }
}

/** Where a [WavWriter]'s bytes go: the file on disk, or a stand-in in tests (a disk that fills up). */
interface WavOutput : AutoCloseable {
    /** Appends; may write part of [len] before it throws (a full disk). */
    fun append(bytes: ByteArray, off: Int, len: Int)
    /** Bytes in the file now, header included. */
    val length: Long
    fun truncate(length: Long)
    /** Writes the 44-byte header over the start of the file (it never needs new space). */
    fun writeHeader(header: ByteArray)
}

private class FileWavOutput(file: File) : WavOutput {
    private val raf = RandomAccessFile(file, "rw").apply { setLength(0); write(ByteArray(WavFile.HEADER_BYTES.toInt())) }
    override fun append(bytes: ByteArray, off: Int, len: Int) = raf.write(bytes, off, len)
    override val length: Long get() = raf.length()
    override fun truncate(length: Long) = raf.setLength(length)
    override fun writeHeader(header: ByteArray) { raf.seek(0); raf.write(header) }
    override fun close() = raf.close()
}

/**
 * Writes a mono 16-bit WAV to disk a buffer at a time; the header is patched with the sizes on
 * [close]. [sampleRate] may change before the first sample (a decoder's real output rate).
 *
 * A write that fails (the disk is full) throws, and the buffer it held is dropped. [close] still
 * writes a header for the samples that reached the disk and closes the file, so what was recorded
 * up to then stays a readable WAV.
 */
class WavWriter(private val out: WavOutput, var sampleRate: Int) : AutoCloseable {
    constructor(file: File, sampleRate: Int) : this(FileWavOutput(file), sampleRate)

    private val buf = ByteBuffer.allocate(1 shl 16).order(ByteOrder.LITTLE_ENDIAN)
    private var failed = false
    private var closed = false

    private var closedSamples = 0L

    /** Whole samples in the file (a write cut short can leave half of one). */
    val samples: Long get() = if (closed) closedSamples else (out.length - WavFile.HEADER_BYTES).coerceAtLeast(0) / 2

    fun write(v: Float) {
        if (failed) throw java.io.IOException("an earlier write to the WAV failed")
        buf.putShort((v.coerceIn(-1f, 1f) * 32767f).roundToInt().toShort())
        if (!buf.hasRemaining()) flush()
    }

    private fun flush() {
        if (buf.position() == 0) return
        try {
            out.append(buf.array(), 0, buf.position())
        } catch (e: java.io.IOException) {
            failed = true
            throw e
        } finally {
            buf.clear()
        }
    }

    override fun close() {
        if (closed) return
        var error: Throwable? = null
        fun keep(e: Throwable) { error?.addSuppressed(e) ?: run { error = e } }
        try {
            if (!failed) flush()
        } catch (e: java.io.IOException) {
            keep(e)
        }
        closedSamples = runCatching { samples }.getOrDefault(0L)
        closed = true
        try {
            val data = closedSamples * 2
            if (out.length != WavFile.HEADER_BYTES + data) out.truncate(WavFile.HEADER_BYTES + data)
            require(data + 36 <= 0xFFFFFFFFL) { "WAV file larger than 4 GB" }
            out.writeHeader(WavFile.header(sampleRate, data.toInt()))
        } catch (e: Throwable) {
            keep(e)
        } finally {
            try { out.close() } catch (e: Throwable) { keep(e) }
        }
        error?.let { throw it }
    }
}

/** 16-bit PCM WAV reading and writing (mono out; any channel count in, mixed to mono). */
object WavFile {
    internal const val HEADER_BYTES = 44L

    internal fun header(sampleRate: Int, dataBytes: Int): ByteArray = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
        put("RIFF".toByteArray()); putInt(36 + dataBytes); put("WAVE".toByteArray())
        put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(1); putInt(sampleRate)
        putInt(sampleRate * 2); putShort(2); putShort(16)
        put("data".toByteArray()); putInt(dataBytes)
    }.array()

    fun write(file: File, audio: PcmAudio) {
        WavWriter(file, audio.sampleRate).use { w -> for (s in audio.samples) w.write(s) }
    }

    /** Reads the file a buffer at a time: only the mono samples are held, never the file's bytes. */
    fun read(file: File): PcmAudio = file.inputStream().buffered(1 shl 16).use { read(it) }

    fun parse(bytes: ByteArray): PcmAudio = read(bytes.inputStream())

    fun read(input: java.io.InputStream): PcmAudio {
        val din = java.io.DataInputStream(input)
        fun int32(): Int = Integer.reverseBytes(din.readInt())
        fun int16(): Int = java.lang.Short.reverseBytes(din.readShort()).toInt()
        fun tag(): String = ByteArray(4).also { din.readFully(it) }.decodeToString()
        val riff = runCatching { tag() }.getOrNull()
        din.skipBytes(4)
        require(riff == "RIFF" && runCatching { tag() }.getOrNull() == "WAVE") { "not a WAV file" }
        var channels = 1
        var rate = 44100
        var bits = 16
        var format = 1
        while (true) {
            val id = try { tag() } catch (e: java.io.EOFException) { break }
            val size = int32().toLong() and 0xFFFFFFFFL
            when (id) {
                "fmt " -> {
                    format = int16(); channels = int16(); rate = int32(); int32(); int16(); bits = int16()
                    skipFully(din, size - 16)
                }
                "data" -> return PcmAudio(readData(din, size, format, channels, bits), rate)
                else -> skipFully(din, size)
            }
            if (size and 1L == 1L) skipFully(din, 1)
        }
        error("WAV file has no data chunk")
    }

    private fun skipFully(input: java.io.InputStream, n: Long) {
        var left = n
        while (left > 0) {
            val skipped = input.skip(left)
            if (skipped <= 0) { if (input.read() < 0) return; left-- } else left -= skipped
        }
    }

    private fun readData(input: java.io.InputStream, size: Long, format: Int, channels: Int, bits: Int): FloatArray {
        val bytesPerSample = bits / 8
        val frameBytes = channels * bytesPerSample
        val out = FloatBuilder(((size / frameBytes).coerceIn(1, Int.MAX_VALUE - 8L)).toInt())
        val chunk = ByteArray(frameBytes * 4096)
        val b = ByteBuffer.wrap(chunk).order(ByteOrder.LITTLE_ENDIAN)
        var left = size
        var carry = 0
        while (left > 0) {
            val n = input.read(chunk, carry, minOf(chunk.size - carry.toLong(), left).toInt())
            if (n < 0) break
            left -= n
            val have = carry + n
            val frames = have / frameBytes
            for (f in 0 until frames) {
                var sum = 0f
                for (c in 0 until channels) {
                    val at = f * frameBytes + c * bytesPerSample
                    sum += when {
                        format == 3 && bits == 32 -> b.getFloat(at)
                        bits == 16 -> b.getShort(at) / 32768f
                        bits == 24 -> ((chunk[at].toInt() and 0xff) or ((chunk[at + 1].toInt() and 0xff) shl 8) or (chunk[at + 2].toInt() shl 16)) / 8388608f
                        bits == 32 -> b.getInt(at) / 2147483648f
                        else -> (chunk[at].toInt() and 0xff) / 128f - 1f
                    }
                }
                out.add(sum / channels)
            }
            carry = have - frames * frameBytes
            if (carry > 0) System.arraycopy(chunk, frames * frameBytes, chunk, 0, carry)
        }
        return out.toArray()
    }
}
