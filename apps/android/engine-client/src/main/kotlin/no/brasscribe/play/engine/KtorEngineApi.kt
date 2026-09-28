package no.brasscribe.play.engine

import io.ktor.client.HttpClient
import io.ktor.client.HttpClientConfig
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.onUpload
import io.ktor.client.plugins.timeout
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.forms.ChannelProvider
import io.ktor.client.request.delete
import io.ktor.client.request.forms.formData
import io.ktor.client.request.forms.submitFormWithBinaryData
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.prepareGet
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsBytes
import io.ktor.client.statement.bodyAsChannel
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import io.ktor.utils.io.jvm.javaio.toByteReadChannel
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import no.brasscribe.play.model.BrasscribeJson
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.CompositionJson

/**
 * HTTP client for a brasscribe engine. Loopback and emulator-host clients are trusted by the engine;
 * LAN clients pair once with the code the engine prints and then send the bearer [token].
 */
class KtorEngineApi(
    private val baseUrl: String,
    engine: HttpClientEngine,
    @Volatile var token: String? = null,
    configure: HttpClientConfig<*>.() -> Unit = {},
) : EngineApi, AutoCloseable {
    private val http = HttpClient(engine) {
        expectSuccess = false
        install(ContentNegotiation) { json(BrasscribeJson) }
        // No timeouts of its own: requests keep the engine's (OkHttp: 10 s); the event stream sets a longer one.
        install(HttpTimeout)
        defaultRequest { url(baseUrl.trimEnd('/') + "/") }
        configure()
    }

    private fun HttpRequestBuilder.auth() {
        token?.let { header(HttpHeaders.Authorization, "Bearer $it") }
    }

    private suspend fun HttpResponse.ok(): HttpResponse {
        if (!status.isSuccess()) throw EngineException(status.value, "${call.request.url.encodedPath}: ${status.value} ${bodyAsText().take(300)}")
        return this
    }

    override suspend fun health(): Health = http.get("v1/health") { auth() }.ok().body()

    // The current token goes along: the engine then replaces this device's entry instead of adding a second one.
    override suspend fun pair(code: String, deviceName: String?, platform: String?): PairResponse =
        http.post("v1/pair") {
            auth()
            contentType(ContentType.Application.Json)
            setBody(PairRequest(code, deviceName, platform))
        }.ok().body<PairResponse>().also { token = it.token }

    override suspend fun thisDevice(): DeviceSelf = http.get("v1/devices/me") { auth() }.ok().body()

    override suspend fun rotateToken(): RotateResponse = http.post("v1/devices/me/rotate") { auth() }.ok().body()

    override suspend fun unpairThisDevice() {
        http.delete("v1/devices/me") { auth() }.ok()
    }

    override suspend fun requestPairing(deviceName: String?, platform: String?): PairRequestInfo =
        http.post("v1/pair/requests") {
            contentType(ContentType.Application.Json)
            setBody(PairRequestCreate(deviceName, platform))
        }.ok().body()

    override suspend fun pollPairingRequest(requestId: String): PairRequestResult =
        http.get("v1/pair/requests/$requestId").ok().body()

    override suspend fun profiles(): List<ProfileInfo> = http.get("v1/profiles") { auth() }.ok().body()

    override suspend fun uploadAudio(source: UploadSource, onProgress: UploadProgress): AudioRef =
        http.submitFormWithBinaryData("v1/audio", formData { appendFile(source) }) { auth(); onUpload { sent, total -> onProgress(sent, total ?: source.size) } }.ok().body()

    override suspend fun createJob(request: JobCreate): Job =
        http.post("v1/jobs") {
            auth()
            contentType(ContentType.Application.Json)
            setBody(request)
        }.ok().body()

    override suspend fun braille(jobId: String, part: String?): ByteArray =
        http.get("v1/jobs/$jobId/braille") { auth(); part?.let { parameter("part", it) } }.ok().bodyAsBytes()

    override suspend fun talkingScore(jobId: String, format: String, lang: String, part: String?, pitchMode: String?, verbosity: String): String =
        http.get("v1/jobs/$jobId/talking-score") {
            auth()
            parameter("format", format); parameter("lang", lang); parameter("verbosity", verbosity)
            part?.let { parameter("part", it) }
            pitchMode?.let { parameter("pitch_mode", it) }
        }.ok().bodyAsText()

    override suspend fun createJobFromUpload(source: UploadSource, profile: Profile, title: String?, renderAudio: Boolean, onProgress: UploadProgress): Job =
        http.submitFormWithBinaryData("v1/jobs/upload", formData {
            appendFile(source)
            append("profile", profile.id)
            append("render_audio", renderAudio.toString())
            title?.let { append("title", it) }
        }) { auth(); onUpload { sent, total -> onProgress(sent, total ?: source.size) } }.ok().body()

    override suspend fun job(jobId: String): Job = http.get("v1/jobs/$jobId") { auth() }.ok().body()
    override suspend fun jobs(): List<Job> = http.get("v1/jobs") { auth() }.ok().body()
    override suspend fun cancel(jobId: String): Job = http.delete("v1/jobs/$jobId") { auth() }.ok().body()

    override fun events(jobId: String, after: Int): Flow<JobEvent> = flow {
        var last = after
        var failures = 0
        while (true) {
            var terminal = false
            try {
                http.prepareGet("v1/jobs/$jobId/events") {
                    auth()
                    parameter("after", last)
                    header(HttpHeaders.Accept, "text/event-stream")
                    // The engine only sends a keepalive every 15 s while a stage runs.
                    timeout { socketTimeoutMillis = EVENTS_SOCKET_TIMEOUT_MS }
                    if (last >= 0) header("Last-Event-ID", last.toString())
                }.execute { response ->
                    response.ok()
                    val channel = response.bodyAsChannel()
                    val parser = SseParser()
                    while (true) {
                        val line = channel.readUTF8Line() ?: break
                        val message = parser.feed(line) ?: continue
                        val event = BrasscribeJson.decodeFromString(JobEvent.serializer(), message.data)
                        last = event.id
                        failures = 0
                        emit(event)
                        if (event.type == "job" && event.status in TERMINAL) terminal = true
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: EngineException) {
                throw e
            } catch (e: Exception) {
                if (++failures > MAX_RECONNECTS) throw EngineException(0, "event stream lost: ${e.message}")
            }
            if (terminal) return@flow
            // The stream ended without a terminal event: the engine closes it once the job is done.
            if (job(jobId).status.terminal) return@flow
            delay(RECONNECT_MS)
        }
    }

    override suspend fun composition(jobId: String): Composition =
        CompositionJson.decode(http.get("v1/jobs/$jobId/composition") { auth() }.ok().bodyAsText())

    override suspend fun musicXml(jobId: String): String = http.get("v1/jobs/$jobId/musicxml") { auth() }.ok().bodyAsText()
    override suspend fun midi(jobId: String): ByteArray = bytes("v1/jobs/$jobId/midi")
    override suspend fun pdf(jobId: String): ByteArray = bytes("v1/jobs/$jobId/pdf")
    override suspend fun renderedAudio(jobId: String): ByteArray = bytes("v1/jobs/$jobId/audio")
    override suspend fun artifacts(jobId: String): List<Artifact> = http.get("v1/jobs/$jobId/artifacts") { auth() }.ok().body()
    override suspend fun artifact(jobId: String, name: String): ByteArray = bytes("v1/jobs/$jobId/artifacts/$name")
    override suspend fun manifest(jobId: String): String = http.get("v1/jobs/$jobId/manifest") { auth() }.ok().bodyAsText()
    override suspend fun evidence(jobId: String): Evidence = http.get("v1/jobs/$jobId/evidence") { auth() }.ok().body()

    override suspend fun renameRun(jobId: String, title: String): Job =
        http.patch("v1/runs/$jobId") {
            auth()
            contentType(ContentType.Application.Json)
            setBody(RunUpdate(title))
        }.ok().body()

    override suspend fun deleteRun(jobId: String) {
        http.delete("v1/runs/$jobId") { auth() }.ok()
    }

    private suspend fun bytes(path: String): ByteArray = http.get(path) { auth() }.ok().bodyAsBytes()

    override fun close() = http.close()

    /**
     * The file part is a stream with a known size: the multipart body then has a Content-Length and
     * the HTTP engine writes it straight from the file, a buffer at a time. The stream is opened
     * when the body is written (again on a retry), never read into memory.
     */
    private fun io.ktor.client.request.forms.FormBuilder.appendFile(source: UploadSource) {
        append("file", ChannelProvider(source.size) { source.open().toByteReadChannel() }, Headers.build {
            append(HttpHeaders.ContentType, "application/octet-stream")
            append(HttpHeaders.ContentDisposition, "filename=\"${source.filename.replace("\"", "")}\"")
        })
    }

    private companion object {
        val TERMINAL = setOf("succeeded", "failed", "cancelled")
        const val MAX_RECONNECTS = 5
        const val RECONNECT_MS = 1000L
        const val EVENTS_SOCKET_TIMEOUT_MS = 60_000L
    }
}

/** Minimal text/event-stream parser: returns a message when a blank line ends one. */
class SseParser {
    data class Message(val id: String?, val event: String?, val data: String)

    private var id: String? = null
    private var event: String? = null
    private val data = StringBuilder()

    fun feed(line: String): Message? {
        if (line.isEmpty()) {
            if (data.isEmpty()) { event = null; return null }
            val m = Message(id, event, data.toString().removeSuffix("\n"))
            data.clear(); event = null
            return m
        }
        if (line.startsWith(":")) return null
        val colon = line.indexOf(':')
        val field = if (colon < 0) line else line.substring(0, colon)
        val value = if (colon < 0) "" else line.substring(colon + 1).removePrefix(" ")
        when (field) {
            "id" -> id = value
            "event" -> event = value
            "data" -> data.append(value).append('\n')
        }
        return null
    }
}
