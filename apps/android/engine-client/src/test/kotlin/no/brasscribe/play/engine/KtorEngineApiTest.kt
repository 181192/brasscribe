package no.brasscribe.play.engine

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class KtorEngineApiTest {
    private val json = headersOf(HttpHeaders.ContentType, "application/json")

    private val job = """{"id":"r1","profile":"solo","status":"queued","created":1.5,"stages":[{"name":"beats","status":"pending"}],"unknown_field":1}"""

    @Test
    fun sendsBearerTokenAndDecodesJob() = runTest {
        val seen = mutableListOf<String?>()
        val engine = MockEngine { req ->
            seen += req.headers[HttpHeaders.Authorization]
            when (req.url.encodedPath) {
                "/v1/pair" -> respond("""{"token":"t0k","device_id":"d1","server_id":"s1","server_name":"Brasscribe on Mac"}""", HttpStatusCode.OK, json)
                "/v1/jobs/r1" -> respond(job, HttpStatusCode.OK, json)
                else -> respond("", HttpStatusCode.NotFound)
            }
        }
        val api = KtorEngineApi("http://10.0.2.2:8765", engine)
        api.pair("123456", "Pixel")
        val j = api.job("r1")
        assertEquals(JobStatus.QUEUED, j.status)
        assertEquals(listOf(null, "Bearer t0k"), seen)
    }

    @Test
    fun pairAgainSendsTheCurrentTokenAndPlatform() = runTest {
        var auth: String? = null
        var body = ""
        val engine = MockEngine { req ->
            auth = req.headers[HttpHeaders.Authorization]
            body = String(req.body.toByteArray())
            respond("""{"token":"new","device_id":"d1","server_id":"s1","server_name":"Brasscribe on Mac"}""", HttpStatusCode.OK, json)
        }
        val api = KtorEngineApi("http://host", engine, token = "old")
        val r = api.pair("123456", "Pixel")
        assertEquals("Bearer old", auth)
        assertTrue(body, body.contains("\"platform\":\"android\""))
        assertEquals("s1", r.serverId)
        assertEquals("new", api.token)
    }

    @Test
    fun thisDeviceRotationAndApproveOnComputer() = runTest {
        val seen = mutableListOf<String>()
        val engine = MockEngine { req ->
            seen += "${req.method.value} ${req.url.encodedPath}"
            when (req.url.encodedPath) {
                "/v1/devices/me" -> respond("""{"device_id":"d1","name":"Pixel","platform":"android","paired_at":"2026-09-01T10:00:00+00:00",
                    "last_seen":"2026-09-27T10:00:00+00:00","online":true,"server_id":"s1","rotate_after":"2026-10-01T10:00:00+00:00",
                    "expires_if_idle_after":"2026-12-26T10:00:00+00:00","rotated_at":null}""", HttpStatusCode.OK, json)
                "/v1/devices/me/rotate" -> respond("""{"token":"t2","device_id":"d1"}""", HttpStatusCode.OK, json)
                "/v1/pair/requests" -> respond("""{"request_id":"q1","name":"Pixel","platform":"android","match_code":"4821",
                    "created_at":"2026-09-27T10:00:00+00:00","status":"pending"}""", HttpStatusCode.Accepted, json)
                "/v1/pair/requests/q1" -> respond("""{"status":"approved","token":"t3","device_id":"d1","server_id":"s1","server_name":"Brasscribe on Mac"}""",
                    HttpStatusCode.OK, json)
                else -> respond("", HttpStatusCode.NotFound)
            }
        }
        val api = KtorEngineApi("http://host", engine, token = "t1")
        assertEquals("2026-10-01T10:00:00+00:00", api.thisDevice().rotateAfter)
        assertEquals("t2", api.rotateToken().token)
        assertEquals("4821", api.requestPairing("Pixel").matchCode)
        assertEquals("t3", api.pollPairingRequest("q1").token)
        assertEquals(listOf("GET /v1/devices/me", "POST /v1/devices/me/rotate", "POST /v1/pair/requests", "GET /v1/pair/requests/q1"), seen)
    }

    @Test
    fun revokedCredentialIs401() = runTest {
        val api = KtorEngineApi("http://host", MockEngine { respond("""{"detail":"unknown token"}""", HttpStatusCode.Unauthorized, json) }, token = "x")
        assertEquals(401, (runCatching { api.thisDevice() }.exceptionOrNull() as EngineException).status)
    }

    @Test
    fun uploadsMultipartWithProfile() = runTest {
        var body: io.ktor.http.content.OutgoingContent? = null
        val engine = MockEngine { req ->
            assertEquals(HttpMethod.Post, req.method)
            assertEquals("/v1/jobs/upload", req.url.encodedPath)
            body = req.body
            respond(job, HttpStatusCode.Accepted, json)
        }
        val api = KtorEngineApi("http://host:8765/", engine)
        val j = api.createJobFromUpload("take.wav", ByteArray(10), Profile.SOLO, "Take 1")
        assertEquals("r1", j.id)
        assertTrue(body!!.contentType.toString().startsWith("multipart/form-data"))
    }

    @Test
    fun mapsErrorsToEngineException() = runTest {
        val api = KtorEngineApi("http://host", MockEngine { respond("""{"detail":"bad code"}""", HttpStatusCode.Forbidden, json) })
        val e = runCatching { api.pair("0", null) }.exceptionOrNull() as EngineException
        assertEquals(403, e.status)
    }

    @Test
    fun evidenceRenameAndDelete() = runTest {
        val seen = mutableListOf<String>()
        val engine = MockEngine { req ->
            seen += "${req.method.value} ${req.url.encodedPath}"
            when (req.url.encodedPath) {
                "/v1/jobs/r1/evidence" -> respond(
                    """{"models":[{"model":"basic-pitch","name":"Basic Pitch"}],"notes":[{"voice":"melody","start":24,"pitch":67,
                    "confidence":0.5,"onset_s":1.0,"models":[{"model":"basic-pitch","name":"Basic Pitch","pitch":69,"agrees":false}]}]}""",
                    HttpStatusCode.OK, json)
                "/v1/runs/r1" -> if (req.method == HttpMethod.Delete) respond("", HttpStatusCode.NoContent) else respond(job, HttpStatusCode.OK, json)
                else -> respond("", HttpStatusCode.NotFound)
            }
        }
        val api = KtorEngineApi("http://host", engine)
        val note = api.evidence("r1").notes.single()
        assertEquals(0.5, note.confidence, 0.0)
        assertEquals(ModelHeard("basic-pitch", "Basic Pitch", false, 69), note.models.single())
        assertEquals(2, note.alternativeShift)
        api.renameRun("r1", "Rehearsal")
        api.deleteRun("r1")
        assertEquals(listOf("GET /v1/jobs/r1/evidence", "PATCH /v1/runs/r1", "DELETE /v1/runs/r1"), seen)
    }

    @Test
    fun streamsServerSentEventsUntilTerminal() = runTest {
        val stream = buildString {
            append(": keepalive\n\n")
            append("id: 0\nevent: job\ndata: {\"id\":0,\"type\":\"job\",\"status\":\"queued\",\"run\":\"r1\",\"time\":1.0}\n\n")
            append("id: 1\nevent: stage\ndata: {\"id\":1,\"type\":\"stage\",\"stage\":\"beats\",\"kind\":\"beats\",\"status\":\"ran\",\"fraction\":0.5,\"time\":3.0,\"key\":\"abc\"}\n\n")
            append("id: 2\nevent: job\ndata: {\"id\":2,\"type\":\"job\",\"status\":\"succeeded\",\"time\":5.0}\n\n")
        }
        var afterParam: String? = null
        val engine = MockEngine { req ->
            afterParam = req.url.parameters["after"]
            respond(stream, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "text/event-stream"))
        }
        val events = KtorEngineApi("http://host", engine).events("r1").toList()
        assertEquals("-1", afterParam)
        assertEquals(listOf(0, 1, 2), events.map { it.id })
        val tracker = ProgressTracker(stagesTotal = 2)
        val last = events.map { tracker.onEvent(it) }.last()
        assertEquals(JobStatus.SUCCEEDED, last.status)
        assertEquals(1.0, last.fraction, 0.0)
    }

    @Test
    fun anEngineThatCannotBeReachedAfterTheStreamEndsIsRetriedThenGivenUp() = runTest {
        val requests = mutableListOf<String>()
        val engine = MockEngine { req ->
            requests += req.url.encodedPath
            throw java.io.IOException("connection refused")
        }
        val e = runCatching { KtorEngineApi("http://host", engine).events("r1").toList() }.exceptionOrNull()
        assertTrue("$e", e is EngineException && e.status == 0)
        // Each attempt is one stream request; the status check is never reached, and never escapes the retries.
        assertEquals(List(6) { "/v1/jobs/r1/events" }, requests)
    }

    @Test
    fun aLostStatusCheckCountsAsALostStreamAndTheStreamResumes() = runTest {
        val done = "id: 3\nevent: job\ndata: {\"id\":3,\"type\":\"job\",\"status\":\"succeeded\",\"time\":5.0}\n\n"
        val first = "id: 2\nevent: stage\ndata: {\"id\":2,\"type\":\"stage\",\"stage\":\"beats\",\"status\":\"ran\",\"time\":3.0}\n\n"
        var streams = 0
        var statusChecks = 0
        val afters = mutableListOf<String?>()
        val engine = MockEngine { req ->
            when (req.url.encodedPath) {
                "/v1/jobs/r1/events" -> {
                    afters += req.url.parameters["after"]
                    // The first stream ends early; the next one has the job's end.
                    respond(if (streams++ == 0) first else done, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "text/event-stream"))
                }
                // The engine drops out for the status check right after the first stream.
                "/v1/jobs/r1" -> { statusChecks++; throw java.io.IOException("unreachable") }
                else -> respond("", HttpStatusCode.NotFound)
            }
        }
        val events = KtorEngineApi("http://host", engine).events("r1").toList()
        assertEquals(listOf(2, 3), events.map { it.id })
        assertEquals(1, statusChecks)
        assertEquals(listOf("-1", "2"), afters)
    }

    @Test
    fun anErrorFromTheEngineEndsTheStreamAtOnce() = runTest {
        var requests = 0
        val engine = MockEngine { requests++; respond("""{"detail":"no such job"}""", HttpStatusCode.NotFound, json) }
        val e = runCatching { KtorEngineApi("http://host", engine).events("r1").toList() }.exceptionOrNull()
        assertTrue("$e", e is EngineException && e.status == 404)
        assertEquals(1, requests)
    }

    @Test
    fun theCollectorsOwnFailureIsNotRetried() = runTest {
        var requests = 0
        val stream = "id: 0\nevent: job\ndata: {\"id\":0,\"type\":\"job\",\"status\":\"queued\",\"time\":1.0}\n\n"
        val engine = MockEngine { requests++; respond(stream, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "text/event-stream")) }
        val e = runCatching { KtorEngineApi("http://host", engine).events("r1").collect { error("collector failed") } }.exceptionOrNull()
        assertEquals("collector failed", e?.message)
        assertEquals(1, requests)
    }

    @Test
    fun reconnectsWaitLongerAfterEachFailure() {
        assertEquals(listOf(1000L, 1000L, 2000L, 4000L, 8000L, 8000L), (0..5).map { KtorEngineApi.reconnectDelay(it) })
    }

    @Test
    fun sseParserJoinsMultilineData() {
        val p = SseParser()
        listOf("id: 7", "data: a", "data: b").forEach { assertEquals(null, p.feed(it)) }
        assertEquals(SseParser.Message("7", null, "a\nb"), p.feed(""))
    }

    @Test
    fun progressEstimatesTimeLeftFromPace() {
        val t = ProgressTracker(stagesTotal = 4)
        t.onEvent(JobEvent(0, "job", status = "running", time = 100.0))
        val p = t.onEvent(JobEvent(1, "stage", stage = "stems", kind = "stems", status = "ran", fraction = 0.25, time = 130.0))
        // 30 s for a quarter of the stages: 90 s to go.
        assertEquals(90, p.etaSeconds)
        assertEquals("stems", p.currentKind)
    }

    @Test
    fun theRecordingOfAJobIsWrittenToAFile() = runTest {
        val sound = ByteArray(200_000) { (it % 251).toByte() }
        val engine = MockEngine { req ->
            when (req.url.encodedPath) {
                "/v1/jobs/r1/input" -> respond(sound, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "audio/wav"))
                else -> respond("""{"detail":"input audio no longer exists, or is not in the engine's audio folders"}""", HttpStatusCode.NotFound, json)
            }
        }
        val api = KtorEngineApi("http://host", engine, token = "t")
        val file = java.io.File.createTempFile("input", ".wav")
        try {
            api.jobInput("r1", file)
            assertTrue(sound.contentEquals(file.readBytes()))
            val gone = runCatching { api.jobInput("r2", file) }.exceptionOrNull()
            assertEquals(404, (gone as? EngineException)?.status)
        } finally {
            file.delete()
        }
    }

    @Test
    fun aRecordingLargerThanTheLimitIsRefusedAndLeavesNothing() = runTest {
        val sound = ByteArray(50_000)
        // One computer says how much it will send, the other only sends it.
        for (declared in listOf(true, false)) {
            val engine = MockEngine { _ ->
                if (declared) respond(sound, HttpStatusCode.OK, headersOf(HttpHeaders.ContentLength, sound.size.toString()))
                else respond(io.ktor.utils.io.ByteReadChannel(sound), HttpStatusCode.OK)
            }
            val api = KtorEngineApi("http://host", engine)
            val file = java.io.File.createTempFile("input", ".wav")
            try {
                val refused = runCatching { api.jobInput("r1", file, maxBytes = 10_000) }.exceptionOrNull()
                assertEquals(413, (refused as? EngineException)?.status)
                assertTrue("nothing over the limit is kept (${file.length()})", file.length() <= 10_001)
                api.jobInput("r1", file, maxBytes = 50_000)
                assertEquals(50_000L, file.length())
            } finally {
                file.delete()
            }
        }
    }
}
