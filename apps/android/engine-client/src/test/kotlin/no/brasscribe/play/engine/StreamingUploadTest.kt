package no.brasscribe.play.engine

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf
import io.ktor.utils.io.ByteChannel
import io.ktor.utils.io.readAvailable
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.RandomAccessFile

/**
 * Uploads stream from the file: runs in its own test task with a small heap (see build.gradle.kts),
 * and sends a file several times larger than that heap. Reading the file into a ByteArray, or a
 * multipart body that buffers its parts, fails here with OutOfMemoryError.
 */
class StreamingUploadTest {
    private val json = headersOf(HttpHeaders.ContentType, "application/json")
    private val audioRef = """{"audio_id":"a1","sha256":"00","filename":"big.m4a","bytes":1}"""
    private val files = mutableListOf<File>()

    @After fun cleanUp() { files.forEach { it.delete() } }

    private fun tempFile(): File = File.createTempFile("upload", ".m4a").also { files += it }

    /** Writes the body to a channel and reads it back a buffer at a time; [keep] collects it when small. */
    private suspend fun drain(body: OutgoingContent, keep: ByteArrayOutputStream?): Long = coroutineScope {
        val channel = when (body) {
            // onUpload wraps the multipart body to count what is read from it.
            is OutgoingContent.ReadChannelContent -> body.readFrom()
            is OutgoingContent.WriteChannelContent -> ByteChannel().also { ch -> launch { body.writeTo(ch); ch.flushAndClose() } }
            else -> error("unexpected body ${body::class}")
        }
        val buf = ByteArray(1 shl 16)
        var total = 0L
        while (true) {
            val n = channel.readAvailable(buf, 0, buf.size)
            if (n < 0) break
            total += n
            keep?.write(buf, 0, n)
        }
        total
    }

    @Test
    fun largeFileStreamsWithFlatMemory() = runBlocking {
        val maxHeap = Runtime.getRuntime().maxMemory()
        val size = maxOf(768L shl 20, maxHeap * 3)
        val file = tempFile()
        // Sparse: the disk holds almost nothing, the reader still sees every byte.
        RandomAccessFile(file, "rw").use { it.setLength(size); it.seek(size - 4); it.write(byteArrayOf(1, 2, 3, 4)) }
        var sent = 0L
        var declared: Long? = null
        var progressCalls = 0
        val engine = MockEngine { req ->
            val body = req.body
            assertTrue(body.contentType.toString().startsWith("multipart/form-data"))
            declared = body.contentLength
            sent = drain(body, null)
            respond(audioRef, HttpStatusCode.Created, json)
        }
        val api = KtorEngineApi("http://host", engine)
        val runtime = Runtime.getRuntime()
        System.gc()
        val before = runtime.totalMemory() - runtime.freeMemory()
        api.uploadAudio(UploadSource.of(file)) { done, total ->
            progressCalls++
            // The whole request body: the file plus the multipart framing.
            assertTrue(total >= size)
            assertTrue(done <= total)
        }
        val after = runtime.totalMemory() - runtime.freeMemory()
        println("streamed %d MB with a %d MB heap; used heap %d -> %d MB".format(size shr 20, maxHeap shr 20, before shr 20, after shr 20))
        assertTrue("the test heap must be smaller than the file ($maxHeap vs $size)", maxHeap < size)
        assertTrue("multipart body has a Content-Length", declared != null)
        assertEquals(declared, sent)
        assertTrue("the body carries the whole file", sent > size)
        assertTrue("upload progress was reported", progressCalls > 0)
    }

    @Test
    fun smallFileArrivesByteExact() = runBlocking {
        val bytes = ByteArray(300_000) { (it * 31 + 7).toByte() }
        val file = tempFile().apply { writeBytes(bytes) }
        val received = ByteArrayOutputStream()
        var path = ""
        val engine = MockEngine { req ->
            path = req.url.encodedPath
            drain(req.body, received)
            respond("""{"id":"r1","profile":"solo","status":"queued","created":1.5,"stages":[]}""", HttpStatusCode.Accepted, json)
        }
        val api = KtorEngineApi("http://host", engine)
        api.createJobFromUpload(UploadSource.of(file, "take \"1\".m4a"), Profile.SOLO, "Take 1")
        assertEquals("/v1/jobs/upload", path)
        val body = received.toByteArray()
        val at = indexOf(body, bytes.copyOfRange(0, 64))
        assertTrue("file bytes are in the body", at > 0)
        assertArrayEquals(bytes, body.copyOfRange(at, at + bytes.size))
        val text = String(body, Charsets.ISO_8859_1)
        assertTrue(text.contains("filename=\"take 1.m4a\""))
        assertTrue(text.contains("name=\"profile\""))
    }

    @Test
    fun streamIsReopenedForEachRequest() = runBlocking {
        var opened = 0
        val bytes = ByteArray(1000) { it.toByte() }
        val source = UploadSource("take.wav", bytes.size.toLong()) { opened++; bytes.inputStream() }
        val api = KtorEngineApi("http://host", MockEngine { req -> drain(req.body, null); respond(audioRef, HttpStatusCode.Created, json) })
        api.uploadAudio(source)
        api.uploadAudio(source)
        assertEquals(2, opened)
    }

    @Test
    fun fixtureHashesTheStream() = runBlocking {
        val bytes = ByteArray(200_000) { (it % 251).toByte() }
        val file = tempFile().apply { writeBytes(bytes) }
        val api = FixtureEngineApi({ null })
        val fromFile = api.uploadAudio(UploadSource.of(file, "a.wav"))
        val fromBytes = api.uploadAudio("a.wav", bytes)
        assertEquals(fromBytes.sha256, fromFile.sha256)
        assertEquals(bytes.size.toLong(), fromFile.bytes)
    }

    private fun indexOf(haystack: ByteArray, needle: ByteArray): Int {
        outer@ for (i in 0..haystack.size - needle.size) {
            for (j in needle.indices) if (haystack[i + j] != needle[j]) continue@outer
            return i
        }
        return -1
    }
}
