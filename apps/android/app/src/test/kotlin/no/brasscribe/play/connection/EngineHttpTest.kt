package no.brasscribe.play.connection

import io.ktor.client.engine.HttpClientEngine
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.engine.KtorEngineApi
import no.brasscribe.play.engine.UploadSource
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.BufferedInputStream
import java.io.InputStream
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

/**
 * The engine's web server (uvicorn) closes a connection that has been idle for 5 s. OkHttp keeps one for
 * minutes and only checks it is still open when it has been idle for 10 s or more, so a recording sent
 * between those two moments went out on a connection the computer had already closed: "unexpected end of
 * stream", and an upload is not sent again by itself. That was the first send after the app started, after
 * the list of songs had been read.
 */
class EngineHttpTest {
    private val server = ServerSocket(0)
    private val connections = AtomicInteger()

    @After fun close() = server.close()

    /** Answers on each connection until it has been idle for [SERVER_IDLE_MS], then closes it, as uvicorn does. */
    private fun serve() = thread(isDaemon = true) {
        while (!server.isClosed) {
            val socket = runCatching { server.accept() }.getOrNull() ?: break
            connections.incrementAndGet()
            thread(isDaemon = true) { socket.use { answer(it) } }
        }
    }

    private fun answer(socket: Socket) {
        socket.soTimeout = SERVER_IDLE_MS.toInt()
        val input = BufferedInputStream(socket.getInputStream())
        val out = socket.getOutputStream()
        while (true) {
            val head = try { readHead(input) } catch (_: SocketTimeoutException) { return } ?: return
            val lines = head.split("\r\n")
            val headers = lines.drop(1).associate { it.substringBefore(':').trim().lowercase() to it.substringAfter(':').trim() }
            when {
                headers["transfer-encoding"]?.contains("chunked") == true -> skipChunked(input)
                else -> headers["content-length"]?.toLong()?.let { skip(input, it) }
            }
            val path = lines.first().split(" ")[1]
            val body = when {
                path.startsWith("/v1/audio") -> """{"audio_id":"a1","sha256":"00","filename":"take.wav","bytes":4}"""
                else -> """{"version":"x","device":"cpu","auth_required":false,"server_id":"s","server_name":"Fixture"}"""
            }
            out.write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${body.length}\r\n\r\n$body".toByteArray())
            out.flush()
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

    private fun skip(input: InputStream, n: Long) {
        var left = n
        while (left > 0) { if (input.read() < 0) return; left-- }
    }

    private fun skipChunked(input: InputStream) {
        while (true) {
            val size = generateSequence { input.read().takeIf { it >= 0 }?.toChar() }.takeWhile { it != '\n' }.joinToString("").trim().toLong(16)
            skip(input, size + 2)
            if (size == 0L) return
        }
    }

    private fun sendAfterAPause(engine: HttpClientEngine) = runBlocking {
        serve()
        KtorEngineApi("http://127.0.0.1:${server.localPort}", engine).use { api ->
            api.health()
            // Past the computer's 5 s, short of OkHttp's own check at 10 s.
            Thread.sleep(SERVER_IDLE_MS + 1_000)
            api.uploadAudio(UploadSource.of("take.wav", byteArrayOf(1, 2, 3, 4)))
        }
    }

    @Test
    fun aRecordingSentSecondsAfterTheLastRequestGetsThrough() {
        val sent = sendAfterAPause(EngineHttp.engine())
        assertEquals("a1", sent.audioId)
        assertEquals("a new connection for the upload", 2, connections.get())
    }

    @Test
    fun theAppLetsGoOfAConnectionBeforeTheComputerDoes() {
        assertTrue(EngineHttp.KEEP_ALIVE_MS < SERVER_IDLE_MS - 1_000)
    }

    private companion object {
        /** uvicorn's timeout_keep_alive, which the engine runs with (engine/src/brasscribe_engine/cli.py). */
        const val SERVER_IDLE_MS = 5_000L
    }
}
