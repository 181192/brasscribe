package no.brasscribe.play.screen

import java.io.BufferedInputStream
import java.io.Closeable
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.concurrent.thread

/**
 * An engine on this device that answers `GET /v1/health` with [interfaceVersion] (null: with none, as an engine
 * from before the number did) and remembers every request it got. Anything else it is asked gets 404: a test
 * reads [requests] to see that nothing else was asked.
 */
class StubEngine(private val interfaceVersion: Int?, private val name: String = "Brasscribe on Studio") : Closeable {
    private val server = ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))
    val url: String = "http://127.0.0.1:${server.localPort}"
    val address: String = "127.0.0.1:${server.localPort}"

    /** "GET /v1/health", in the order they came. */
    val requests = CopyOnWriteArrayList<String>()

    init {
        thread(isDaemon = true) {
            while (!server.isClosed) {
                val socket = runCatching { server.accept() }.getOrNull() ?: break
                thread(isDaemon = true) { runCatching { socket.use(::answer) } }
            }
        }
    }

    private fun answer(socket: Socket) {
        val input = BufferedInputStream(socket.getInputStream())
        val out = socket.getOutputStream()
        while (true) {
            val head = StringBuilder()
            while (!head.endsWith("\r\n\r\n")) {
                val b = input.read()
                if (b < 0) return
                head.append(b.toChar())
            }
            val lines = head.split("\r\n")
            val length = lines.firstOrNull { it.startsWith("content-length:", ignoreCase = true) }?.substringAfter(':')?.trim()?.toLong() ?: 0
            repeat(length.toInt()) { if (input.read() < 0) return }
            val (method, target) = lines.first().split(" ")
            val path = target.substringBefore('?')
            requests += "$method $path"
            val (status, body) = if (method == "GET" && path == "/v1/health") {
                val version = interfaceVersion?.let { ""","interface_version":$it""" }.orEmpty()
                "200 OK" to """{"status":"ok","version":"0.0.0","device":"cpu","auth_required":true,"server_id":"$SERVER_ID","server_name":"$name"$version}"""
            } else "404 Not Found" to """{"detail":"not found"}"""
            val bytes = body.toByteArray()
            out.write("HTTP/1.1 $status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\n\r\n".toByteArray())
            out.write(bytes)
            out.flush()
        }
    }

    override fun close() = server.close()

    companion object {
        const val SERVER_ID = "0123456789abcdef0123456789abcdef"
    }
}
