package no.brasscribe.play.connection

import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.okhttp.OkHttp
import okhttp3.ConnectionPool
import java.util.concurrent.TimeUnit
import javax.net.SocketFactory

/** The HTTP client under every request to the computer. */
object EngineHttp {
    /**
     * How long a connection is kept for the next request. Engines before the longer keep-alive close one that has
     * been idle for 5 s (uvicorn's default); OkHttp keeps them for minutes and only looks whether one is still open
     * after 10 s idle. A request sent in between went out on a connection the computer had closed: a recording sent
     * then failed with "unexpected end of stream", as OkHttp only sends a request again when it can read its body
     * again, and a streamed upload it cannot. Idle time stops counting while the phone is in deep sleep, so
     * [no.brasscribe.play.engine.KtorEngineApi.uploadAudio] also sends a recording once more when that happens.
     */
    const val KEEP_ALIVE_MS = 3_000L

    /** OkHttp for the computer, its sockets made by [socketFactory] when given (a network to bind to). */
    fun engine(socketFactory: SocketFactory? = null): HttpClientEngine = OkHttp.create {
        config {
            connectionPool(ConnectionPool(MAX_IDLE, KEEP_ALIVE_MS, TimeUnit.MILLISECONDS))
            if (socketFactory != null) socketFactory(socketFactory)
        }
    }

    /** OkHttp's own number of idle connections kept. */
    private const val MAX_IDLE = 5
}
