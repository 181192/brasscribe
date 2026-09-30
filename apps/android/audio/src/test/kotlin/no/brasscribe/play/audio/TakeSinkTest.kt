package no.brasscribe.play.audio

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import kotlin.math.sin

/** A recording goes to disk as it comes; memory holds it only while it is short, and it stops at the limit. */
class TakeSinkTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun tone(n: Int, from: Int = 0) = FloatArray(n) { (0.5 * sin((from + it) * 0.01)).toFloat() }

    /** Feeds [total] samples in recorder-sized buffers, as the capture loops do. */
    private fun feed(sink: TakeSink, total: Int, buffer: Int = 4096): FloatArray {
        val all = tone(total)
        var at = 0
        val buf = FloatArray(buffer)
        while (at < total) {
            val n = minOf(buffer, total - at)
            System.arraycopy(all, at, buf, 0, n)
            sink.add(buf, n)
            at += n
        }
        return all
    }

    @Test
    fun aShortTakeIsOnDiskAndInMemory() {
        val sink = TakeSink(tmp.newFile("short.wav"), 48_000, maxInMemory = 100_000)
        val sent = feed(sink, 48_000)
        assertTrue(sink.inMemory)
        val take = sink.finish()
        assertEquals(48_000L, take.samples)
        assertEquals(1.0, take.seconds, 1e-9)
        assertNotNull(take.audio)
        assertArrayEquals(sent, take.audio!!.samples, 0f)
        // A valid WAV of the same samples, to 16-bit precision.
        assertEquals(44L + 2 * 48_000, take.file.length())
        val read = WavFile.read(take.file)
        assertEquals(48_000, read.sampleRate)
        assertArrayEquals(sent, read.samples, 1f / 32_000)
    }

    @Test
    fun aLongTakeLeavesMemoryAndStaysWhole() {
        val limit = 20_000
        val sink = TakeSink(tmp.newFile("long.wav"), 16_000, maxInMemory = limit)
        feed(sink, limit)
        assertTrue("at the limit exactly, still in memory", sink.inMemory)
        val buf = tone(1)
        sink.add(buf, 1)
        assertFalse("one past the limit, memory lets go", sink.inMemory)
        feed(sink, 100_000)
        val take = sink.finish()
        assertNull("too long for memory", take.audio)
        assertEquals(limit + 1L + 100_000, take.samples)
        assertEquals(44L + 2 * take.samples, take.file.length())
        assertEquals(take.samples.toInt(), WavFile.read(take.file).samples.size)
    }

    @Test
    fun memoryStaysFlatPastTheLimit() {
        // 20 minutes at 48 kHz (57.6 M samples, 230 MB as floats) through a sink holding 1 s in memory.
        val sink = TakeSink(tmp.newFile("flat.wav"), 48_000, maxInMemory = 48_000)
        val rt = Runtime.getRuntime()
        fun used(): Long { repeat(2) { System.gc(); Thread.sleep(20) }; return rt.totalMemory() - rt.freeMemory() }
        val buf = tone(4096)
        repeat(100) { sink.add(buf, buf.size) }
        val before = used()
        repeat(20 * 60 * 48_000 / 4096) { sink.add(buf, buf.size) }
        val after = used()
        sink.finish()
        assertTrue("heap grew ${(after - before) shr 20} MB over 20 minutes of samples", after - before < 16L shl 20)
    }

    @Test
    fun theTakeStopsAtItsLength() {
        val sink = TakeSink(tmp.newFile("full.wav"), 8_000, maxInMemory = 1_000, maxSamples = 10_000)
        val buf = tone(4096)
        assertEquals(4096, sink.add(buf, 4096))
        assertEquals(4096, sink.add(buf, 4096))
        assertFalse(sink.full)
        assertEquals("only what fits", 10_000 - 8192, sink.add(buf, 4096))
        assertTrue(sink.full)
        assertEquals("nothing after", 0, sink.add(buf, 4096))
        val take = sink.finish()
        assertEquals(10_000L, take.samples)
        assertEquals(44L + 20_000, take.file.length())
    }

    /** A file that takes [capacity] bytes and then fails, part-way through a write, as a full disk does. */
    private class FullDisk(file: java.io.File, private val capacity: Long) : WavOutput {
        private val raf = java.io.RandomAccessFile(file, "rw").apply { setLength(0); write(ByteArray(44)) }
        var closed = false
        override fun append(bytes: ByteArray, off: Int, len: Int) {
            val room = (capacity - raf.length()).coerceAtLeast(0).toInt()
            raf.write(bytes, off, minOf(room, len))
            if (room < len) throw java.io.IOException("No space left on device")
        }
        override val length: Long get() = raf.length()
        override fun truncate(length: Long) = raf.setLength(length)
        override fun writeHeader(header: ByteArray) { raf.seek(0); raf.write(header) }
        override fun close() { closed = true; raf.close() }
    }

    @Test
    fun aFullDiskEndsTheTakeWithAReadableWav() {
        val file = tmp.newFile("fulldisk.wav")
        // Room for 50 001 bytes of samples: the write that fills it stops half-way through a sample.
        val disk = FullDisk(file, 44L + 100_001)
        val sink = TakeSink(file, 48_000, maxInMemory = 1_000_000, output = disk)
        val sent = feed(sink, 200_000)
        assertTrue(sink.failed)
        assertTrue(sink.full)
        val take = sink.finish()
        assertTrue("the file is closed", disk.closed)
        assertEquals("only the whole samples that reached the disk", 50_000L, take.samples)
        assertEquals(44L + 2 * 50_000, file.length())
        val read = WavFile.read(file)
        assertEquals(50_000, read.samples.size)
        assertArrayEquals(sent.copyOf(50_000), read.samples, 1f / 32_000)
        // Memory holds the same samples as the file, not the ones the disk refused.
        assertEquals(50_000, take.audio!!.samples.size)
    }

    @Test
    fun aDiskFullAtTheLastBufferStillGetsItsHeader() {
        val file = tmp.newFile("lastbuffer.wav")
        // Everything fits but the final flush at close.
        val disk = FullDisk(file, 44L + 65_536)
        val sink = TakeSink(file, 48_000, maxInMemory = 1_000_000, output = disk)
        feed(sink, 40_000)
        assertFalse(sink.failed)
        val take = sink.finish()
        assertTrue(disk.closed)
        assertEquals(32_768L, take.samples)
        assertEquals(32_768, WavFile.read(file).samples.size)
    }

    @Test
    fun aDiscardedTakeLeavesNoFile() {
        val file = tmp.newFile("gone.wav")
        val sink = TakeSink(file, 48_000)
        feed(sink, 10_000)
        sink.discard()
        assertFalse(file.exists())
    }

    @Test
    fun threeHoursAtFortyEightKilohertzIsTheLimit() {
        val sink = TakeSink(tmp.newFile("limit.wav"), 48_000)
        assertEquals(3L * 3600 * 48_000, sink.maxSamples)
        // Well inside a 16-bit WAV's 4 GB.
        assertTrue(44 + 2 * sink.maxSamples < 0xFFFFFFFFL)
        sink.discard()
    }
}
