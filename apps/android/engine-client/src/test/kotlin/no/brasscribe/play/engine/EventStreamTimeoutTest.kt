package no.brasscribe.play.engine

import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

/**
 * The engine writes a keepalive comment every 15 s while a stage runs (HEARTBEAT_S in the engine's
 * api.py), and a model stage can be silent for minutes. OkHttp's default read timeout is 10 s, so
 * without a longer socket timeout every quiet stretch broke the stream and cost a reconnect; six in a
 * row ended the transcription with "event stream lost".
 */
class EventStreamTimeoutTest {
    private val server = ServerSocket(0)
    private val eventConnections = AtomicInteger()

    @After fun close() = server.close()

    private fun serve() = thread(isDaemon = true) {
        while (!server.isClosed) {
            val socket = runCatching { server.accept() }.getOrNull() ?: break
            thread(isDaemon = true) { socket.use { answer(it) } }
        }
    }

    private fun answer(socket: Socket) {
        val request = socket.getInputStream().bufferedReader().readLine() ?: return
        val out = socket.getOutputStream()
        fun write(s: String) { out.write(s.toByteArray()); out.flush() }
        val path = request.split(" ")[1]
        if (path.startsWith("/v1/jobs/j/events")) {
            val n = eventConnections.incrementAndGet()
            write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n")
            if (n == 1) {
                write("id: 0\nevent: job\ndata: {\"id\":0,\"type\":\"job\",\"status\":\"running\"}\n\n")
                Thread.sleep(QUIET_MS) // a stage running, like the engine between two heartbeats
                write(": keepalive\n\n")
            }
            write("id: 1\nevent: job\ndata: {\"id\":1,\"type\":\"job\",\"status\":\"succeeded\"}\n\n")
        } else {
            val body = """{"id":"j","profile":"solo","status":"running","created":1.0,"stages":[]}"""
            write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${body.length}\r\nConnection: close\r\n\r\n$body")
        }
    }

    @Test
    fun aQuietStretchLongerThanOkHttpsReadTimeoutKeepsTheStream() = runBlocking {
        serve()
        KtorEngineApi("http://127.0.0.1:${server.localPort}", OkHttp.create()).use { api ->
            val events = api.events("j").toList()
            assertEquals(listOf(0, 1), events.map { it.id })
            assertEquals("one connection for the whole job", 1, eventConnections.get())
        }
    }

    private companion object {
        const val QUIET_MS = 12_000L // longer than OkHttp's default 10 s read timeout, shorter than 15 s
    }
}
