package no.brasscribe.play.engine

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.client.request.forms.MultiPartFormDataContent
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
                "/v1/pair" -> respond("""{"token":"t0k","device_id":"d1","server_id":"s1","server_name":"Brasscribe on studio"}""", HttpStatusCode.OK, json)
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
    fun uploadsMultipartWithProfile() = runTest {
        var body: MultiPartFormDataContent? = null
        val engine = MockEngine { req ->
            assertEquals(HttpMethod.Post, req.method)
            assertEquals("/v1/jobs/upload", req.url.encodedPath)
            body = req.body as MultiPartFormDataContent
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
}
