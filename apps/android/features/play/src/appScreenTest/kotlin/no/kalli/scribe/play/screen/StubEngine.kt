package no.kalli.scribe.play.screen

import java.io.BufferedInputStream
import java.io.Closeable
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.concurrent.thread

/**
 * An engine on this device that answers `GET /v1/health`, and `GET /v1/devices/me` to the phone that holds [TOKEN],
 * with [interfaceVersion] as its interface version (as it is written in JSON; null: with none, as an engine from
 * before the number did), and remembers every request it got. Anything else it is asked gets 404: a test reads
 * [requests] to see that nothing else was asked.
 */
class StubEngine(@Volatile var interfaceVersion: String?, private val serverId: String = SERVER_ID, private val name: String = "Brasscribe on Studio") : Closeable {
    constructor(interfaceVersion: Int?) : this(interfaceVersion?.toString())

    /** When set, what `GET /v1/devices/me` answers in place of the phone's entry: 401 (this phone is not known), 404, 500. */
    @Volatile var deviceStatus: Int? = null

    /** When set, the whole body of `GET /v1/health` (something that is no engine's answer). */
    @Volatile var healthBody: String? = null

    /** When set, health answers with this status (an engine that is there and cannot answer). */
    @Volatile var healthStatus: Int? = null

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
            fun header(name: String) = lines.firstOrNull { it.startsWith("$name:", ignoreCase = true) }?.substringAfter(':')?.trim()
            repeat(header("content-length")?.toInt() ?: 0) { if (input.read() < 0) return }
            val (method, target) = lines.first().split(" ")
            val path = target.substringBefore('?')
            requests += "$method $path"
            val version = interfaceVersion?.let { ""","interface_version":$it""" }.orEmpty()
            val (status, body) = when {
                method == "GET" && path == "/v1/health" && healthStatus != null -> "$healthStatus Error" to """{"detail":"no"}"""
                method == "GET" && path == "/v1/health" && healthBody != null -> "200 OK" to healthBody!!
                method == "GET" && path == "/v1/devices/me" && deviceStatus != null -> "$deviceStatus Error" to """{"detail":"no"}"""
                method == "GET" && path == "/v1/health" ->
                    "200 OK" to """{"status":"ok","version":"0.0.0","device":"cpu","auth_required":true,"server_id":"$serverId","server_name":"$name"$version}"""
                method == "GET" && path == "/v1/devices/me" && header("authorization") == "Bearer $TOKEN" ->
                    "200 OK" to """{"device_id":"d1","name":"Phone","platform":"android","paired_at":"2026-01-01T00:00:00+00:00",""" +
                        """"last_seen":"2026-01-01T00:00:00+00:00","online":true,"server_id":"$serverId",""" +
                        """"rotate_after":"2099-01-01T00:00:00+00:00","expires_if_idle_after":"2099-01-01T00:00:00+00:00"$version}"""
                method == "GET" && path == "/v1/devices/me" -> "401 Unauthorized" to """{"detail":"unknown token"}"""
                else -> "404 Not Found" to """{"detail":"not found"}"""
            }
            val bytes = body.toByteArray()
            out.write("HTTP/1.1 $status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\n\r\n".toByteArray())
            out.write(bytes)
            out.flush()
        }
    }

    override fun close() = server.close()

    companion object {
        const val SERVER_ID = "0123456789abcdef0123456789abcdef"

        /** The credential of the phone this engine knows. */
        const val TOKEN = "stub-token"
    }
}
