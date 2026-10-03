package no.brasscribe.play.engine

import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.BufferedInputStream
import java.io.InputStream
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

/**
 * A recording sent on a connection that breaks before the computer answers is sent once more. The engine keeps an
 * upload by its SHA-256, so twice is one upload. OkHttp does not do this by itself for a streamed upload: it can only
 * send a body again that it can read again.
 */
class UploadRetryTest {
    private val server = ServerSocket(0)
    private val uploads = AtomicInteger()
    /** The computer takes the upload and does not answer in time. */
    @Volatile private var hang = false

    @After fun close() = server.close()

    /** Closes the connection without an answer for the first [drop] uploads; [status] answers the rest. */
    private fun serve(drop: Int, status: Int = 201) = thread(isDaemon = true) {
        while (!server.isClosed) {
            val socket = runCatching { server.accept() }.getOrNull() ?: break
            thread(isDaemon = true) { socket.use { answer(it, drop, status) } }
        }
    }

    private fun answer(socket: Socket, drop: Int, status: Int) {
        val input = BufferedInputStream(socket.getInputStream())
        val head = readHead(input) ?: return
        val length = Regex("(?im)^content-length:\\s*(\\d+)").find(head)?.groupValues?.get(1)?.toLong()
        if (length != null) repeat(length.toInt()) { if (input.read() < 0) return }
        if (uploads.incrementAndGet() <= drop) return // the connection closes with no answer
        if (hang) { Thread.sleep(3_000); return }
        val body = if (status == 201) """{"audio_id":"a1","sha256":"00","filename":"take.wav","bytes":4}""" else """{"detail":"broken"}"""
        socket.getOutputStream().apply {
            write("HTTP/1.1 $status X\r\nContent-Type: application/json\r\nContent-Length: ${body.length}\r\nConnection: close\r\n\r\n$body".toByteArray())
            flush()
        }
    }

    private fun readHead(input: InputStream): String? {
        val head = StringBuilder()
        while (!head.endsWith("\r\n\r\n")) {
            val b = input.read()
            if (b < 0) return null
            head.append(b.toChar())
        }
        return head.toString()
    }

    private fun upload(engine: io.ktor.client.engine.HttpClientEngine = OkHttp.create()): AudioRef = runBlocking {
        KtorEngineApi("http://127.0.0.1:${server.localPort}", engine).use { it.uploadAudio("take.wav", byteArrayOf(1, 2, 3, 4)) }
    }

    @Test
    fun noAnswerInTimeIsNotTriedAgain() {
        hang = true
        serve(drop = 0)
        val slow = OkHttp.create { config { readTimeout(500, java.util.concurrent.TimeUnit.MILLISECONDS) } }
        val e = assertThrows(java.io.IOException::class.java) { upload(slow) }
        assertTrue("a timeout (${e::class})", KtorEngineApi.isTimeout(e))
        assertEquals(1, uploads.get())
    }

    @Test
    fun timeoutsAreKnownByTheirType() {
        assertTrue(KtorEngineApi.isTimeout(java.net.SocketTimeoutException("read")))
        assertTrue(KtorEngineApi.isTimeout(io.ktor.client.network.sockets.ConnectTimeoutException("connect", null)))
        assertFalse(KtorEngineApi.isTimeout(java.io.IOException("unexpected end of stream")))
        // A broken connection whose words say nothing of time, and one named like a timeout that is not one.
        assertFalse(KtorEngineApi.isTimeout(java.net.SocketException("Connection reset")))
        assertFalse(KtorEngineApi.isTimeout(object : java.io.IOException("x") {}))
    }

    @Test
    fun aConnectionThatBreaksBeforeTheAnswerIsTriedOnceMore() {
        serve(drop = 1)
        assertEquals("a1", upload().audioId)
        assertEquals(2, uploads.get())
    }

    @Test
    fun onlyOnce() {
        serve(drop = 2)
        assertThrows(java.io.IOException::class.java) { upload() }
        assertEquals(2, uploads.get())
    }

    @Test
    fun anAnswerFromTheComputerIsNotTriedAgain() {
        serve(drop = 0, status = 500)
        assertEquals(500, assertThrows(EngineException::class.java) { upload() }.status)
        assertEquals(1, uploads.get())
    }
}
