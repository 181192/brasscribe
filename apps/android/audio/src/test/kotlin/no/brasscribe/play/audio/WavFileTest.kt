package no.brasscribe.play.audio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.sin

class WavFileTest {
    @Test
    fun writeThenReadRoundTripsWithinOneStep() {
        // Not a multiple of the writer's 64 KB buffer, nor of the reader's chunk.
        val n = 100_003
        val samples = FloatArray(n) { (sin(it * 0.01) * 0.8).toFloat() }
        val file = File.createTempFile("wav", ".wav")
        try {
            WavFile.write(file, PcmAudio(samples, 22050))
            assertEquals(44L + n * 2, file.length())
            val back = WavFile.read(file)
            assertEquals(22050, back.sampleRate)
            assertEquals(n, back.samples.size)
            for (i in 0 until n) assertTrue("sample $i", abs(back.samples[i] - samples[i]) <= 1.5f / 32768f)
        } finally {
            file.delete()
        }
    }

    @Test
    fun writerPatchesTheHeaderAndTakesALateRate() {
        val file = File.createTempFile("wav", ".wav")
        try {
            WavWriter(file, 44100).use { w ->
                w.sampleRate = 48000
                repeat(70_000) { w.write(if (it % 2 == 0) 0.5f else -0.5f) }
            }
            val b = ByteBuffer.wrap(file.readBytes()).order(ByteOrder.LITTLE_ENDIAN)
            assertEquals(36 + 140_000, b.getInt(4))
            assertEquals(48000, b.getInt(24))
            assertEquals(140_000, b.getInt(40))
            assertEquals(70_000, WavFile.read(file).samples.size)
        } finally {
            file.delete()
        }
    }

    @Test
    fun parsesStereo24BitWithAnOddChunkBefore() {
        val frames = 5000
        val data = ByteArrayOutputStream()
        for (f in 0 until frames) {
            val l = (f % 100) * 1000
            val r = -l
            for (v in intArrayOf(l, r)) { data.write(v and 0xff); data.write((v shr 8) and 0xff); data.write((v shr 16) and 0xff) }
        }
        val body = data.toByteArray()
        val out = ByteArrayOutputStream()
        fun le32(v: Int) = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(v).array()
        fun le16(v: Int) = ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(v.toShort()).array()
        out.write("RIFF".toByteArray()); out.write(le32(0)); out.write("WAVE".toByteArray())
        // An odd-sized chunk the reader skips, with its pad byte.
        out.write("LIST".toByteArray()); out.write(le32(3)); out.write(byteArrayOf(1, 2, 3, 0))
        out.write("fmt ".toByteArray()); out.write(le32(16)); out.write(le16(1)); out.write(le16(2)); out.write(le32(44100))
        out.write(le32(44100 * 6)); out.write(le16(6)); out.write(le16(24))
        out.write("data".toByteArray()); out.write(le32(body.size)); out.write(body)
        val pcm = WavFile.parse(out.toByteArray())
        assertEquals(44100, pcm.sampleRate)
        assertEquals(frames, pcm.samples.size)
        // Left and right cancel in the mono mix.
        assertTrue(pcm.samples.all { abs(it) < 1e-6f })
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsSomethingElse() {
        WavFile.parse("not a wav file at all".toByteArray())
    }
}
