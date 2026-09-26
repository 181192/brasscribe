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

/** 16-bit PCM WAV reading and writing (mono out; any channel count in, mixed to mono). */
object WavFile {
    fun write(file: File, audio: PcmAudio) {
        val data = ByteBuffer.allocate(audio.samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (s in audio.samples) data.putShort((s.coerceIn(-1f, 1f) * 32767f).roundToInt().toShort())
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt(36 + data.capacity()); put("WAVE".toByteArray())
            put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(1); putInt(audio.sampleRate)
            putInt(audio.sampleRate * 2); putShort(2); putShort(16)
            put("data".toByteArray()); putInt(data.capacity())
        }
        file.outputStream().use { it.write(header.array()); it.write(data.array()) }
    }

    fun read(file: File): PcmAudio = RandomAccessFile(file, "r").use { raf ->
        val bytes = ByteArray(raf.length().toInt()).also { raf.readFully(it) }
        parse(bytes)
    }

    fun parse(bytes: ByteArray): PcmAudio {
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        require(String(bytes, 0, 4) == "RIFF" && String(bytes, 8, 4) == "WAVE") { "not a WAV file" }
        var pos = 12
        var channels = 1
        var rate = 44100
        var bits = 16
        var format = 1
        while (pos + 8 <= bytes.size) {
            val id = String(bytes, pos, 4)
            val size = b.getInt(pos + 4)
            val body = pos + 8
            when (id) {
                "fmt " -> {
                    format = b.getShort(body).toInt(); channels = b.getShort(body + 2).toInt()
                    rate = b.getInt(body + 4); bits = b.getShort(body + 14).toInt()
                }
                "data" -> {
                    val len = minOf(size, bytes.size - body)
                    val frameBytes = channels * bits / 8
                    val frames = len / frameBytes
                    val out = FloatArray(frames)
                    for (f in 0 until frames) {
                        var sum = 0f
                        for (c in 0 until channels) {
                            val at = body + f * frameBytes + c * bits / 8
                            sum += when {
                                format == 3 && bits == 32 -> b.getFloat(at)
                                bits == 16 -> b.getShort(at) / 32768f
                                bits == 24 -> ((bytes[at].toInt() and 0xff) or ((bytes[at + 1].toInt() and 0xff) shl 8) or (bytes[at + 2].toInt() shl 16)) / 8388608f
                                bits == 32 -> b.getInt(at) / 2147483648f
                                else -> (bytes[at].toInt() and 0xff) / 128f - 1f
                            }
                        }
                        out[f] = sum / channels
                    }
                    return PcmAudio(out, rate)
                }
            }
            pos = body + size + (size and 1)
        }
        error("WAV file has no data chunk")
    }
}
