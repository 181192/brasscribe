package no.kalli.scribe.engine

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf
import io.ktor.utils.io.ByteChannel
import io.ktor.utils.io.readAvailable
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Printed music sent as pages (`POST /v1/jobs/pages`): the request the client makes, and the fixture computer's part
 * of it, on apps/fixtures/old-hundredth (a score) and guitar-line (a tab).
 */
class PagesJobTest {
    private val json = headersOf(HttpHeaders.ContentType, "application/json")
    private val fixtures = File(System.getProperty("scribe.fixtures"))

    /** The first bytes of a PNG and of a PDF, with something after them: the fixture computer looks no further. */
    private val png = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A) + ByteArray(40) { it.toByte() }
    private val pdf = "%PDF-1.7\n".toByteArray() + ByteArray(60) { (it + 3).toByte() }

    private fun computer(folder: String, only: List<String>? = null, also: Map<String, String> = emptyMap()) = FixtureEngineApi({ name ->
        if (name == FixtureEngineApi.PROFILES_FILE) only?.joinToString(",", "[", "]") { "\"$it\"" }?.toByteArray()
        else if (name in also) also.getValue(name).toByteArray()
        else File(File(fixtures, folder), name).takeIf { it.isFile }?.readBytes()
    }, stageSeconds = 0.0)

    private suspend fun bodyOf(body: OutgoingContent): ByteArray = coroutineScope {
        val channel = when (body) {
            is OutgoingContent.ReadChannelContent -> body.readFrom()
            is OutgoingContent.WriteChannelContent -> ByteChannel().also { ch -> launch { body.writeTo(ch); ch.flushAndClose() } }
            else -> error("unexpected body ${body::class}")
        }
        val out = ByteArrayOutputStream()
        val buf = ByteArray(1 shl 14)
        while (true) {
            val n = channel.readAvailable(buf, 0, buf.size)
            if (n < 0) break
            out.write(buf, 0, n)
        }
        out.toByteArray()
    }

    @Test
    fun theTwoProfilesReadPagesEachForItsTarget() {
        assertEquals(listOf(Profile.SHEET, Profile.SHEET_TAB), Profile.entries.filter { it.readsPages })
        assertEquals(Profile.SHEET, Profile.pagesOf(Target.BRASS))
        assertEquals(Profile.SHEET_TAB, Profile.pagesOf(Target.FRETTED))
        assertEquals("sheet", Profile.SHEET.id)
        assertEquals("sheet-tab", Profile.SHEET_TAB.id)
        assertTrue(Profile.SHEET_TAB.writesTab)
        assertFalse(Profile.SHEET.writesTab)
    }

    @Test
    fun thePagesGoInOrderInOneRequestWithTheTabOptions() = runBlocking {
        var path = ""
        var method: HttpMethod? = null
        var received = ByteArray(0)
        var type = ""
        val engine = MockEngine { req ->
            path = req.url.encodedPath
            method = req.method
            type = req.body.contentType.toString()
            received = bodyOf(req.body)
            respond("""{"id":"r1","profile":"sheet-tab","target":"fretted","status":"queued","created":1.5,"stages":[]}""", HttpStatusCode.Accepted, json)
        }
        val api = matchingEngine("http://host", engine)
        val progress = mutableListOf<Pair<Long, Long>>()
        val job = api.createJobFromPages(listOf(UploadSource.of("page \"1\".png", png), UploadSource.of("page 2.pdf", pdf)), Profile.SHEET_TAB, "A hymn",
            onProgress = { sent, total -> progress += sent to total },
            tab = TabOptions(FrettedInstrument.GUITAR_6, "drop-d", 2, octave = Octave.AUTO, layout = TabLayout.TAB))
        assertEquals("r1", job.id)
        assertEquals(HttpMethod.Post, method)
        assertEquals("/v1/jobs/pages", path)
        assertTrue(type, type.startsWith("multipart/form-data"))
        val text = String(received, Charsets.ISO_8859_1)
        // Both under the one field, the first page first, each byte for byte.
        assertEquals(2, Regex("name=\"?files\"?").findAll(text).count())
        val first = text.indexOf(String(png, Charsets.ISO_8859_1))
        val second = text.indexOf(String(pdf, Charsets.ISO_8859_1))
        assertTrue("$first, $second", first in 1 until second)
        assertTrue(text.contains("filename=\"page 1.png\"") && text.contains("filename=\"page 2.pdf\""))
        fun field(name: String) = Regex("name=\"?$name\"?\\s*\r\n(?:[^\r\n]+\r\n)*\r\n([^\r\n]*)\r\n").find(text)?.groupValues?.get(1)
        assertEquals("sheet-tab", field("profile"))
        assertEquals("A hymn", field("title"))
        assertEquals("true", field("render_audio"))
        assertEquals("guitar-6", field("instrument"))
        assertEquals("drop-d", field("tuning"))
        assertEquals("2", field("capo"))
        assertEquals("auto", field("octave"))
        assertEquals("tab", field("layout"))
        // Nothing about a recording, which the engine refuses for pages.
        assertNull(field("recording"))
        assertNull(field("chords"))
        // The bytes sent of the whole request, growing to its end.
        assertTrue(progress.toString(), progress.isNotEmpty())
        assertEquals(progress.map { it.first }.sorted(), progress.map { it.first })
        assertTrue(progress.last().let { (sent, total) -> sent == total && total > png.size + pdf.size })
    }

    @Test
    fun aScoreProfileSendsNoTabOptions() = runBlocking {
        var received = ByteArray(0)
        val api = matchingEngine("http://host", MockEngine { req ->
            received = bodyOf(req.body)
            respond("""{"id":"r1","profile":"sheet","target":"brass","status":"queued","created":1.5,"stages":[]}""", HttpStatusCode.Accepted, json)
        })
        api.createJobFromPages(listOf(UploadSource.of("page.png", png)), Profile.SHEET, null)
        val text = String(received, Charsets.ISO_8859_1)
        assertTrue(text.contains("name=\"profile\"") || text.contains("name=profile"))
        listOf("title", "instrument", "tuning", "capo", "lineup", "seat").forEach { assertFalse(it, Regex("name=\"?$it\"?\\s").containsMatchIn(text)) }
    }

    @Test
    fun theEnginesRefusalsKeepTheirCodes() = runBlocking {
        val notAPage = matchingEngine("http://host", MockEngine { respond("""{"code":"not_a_page","detail":"take.heic is not a picture or a PDF"}""", HttpStatusCode.UnsupportedMediaType, json) })
        val refused = runCatching { notAPage.createJobFromPages(listOf(UploadSource.of("take.heic", ByteArray(8))), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(415, refused.status)
        assertEquals(InputRefusal.NOT_A_PAGE, refused.code)
        // An engine from before the pages has no such address.
        val older = matchingEngine("http://host", MockEngine { respond("""{"detail":"Not Found"}""", HttpStatusCode.NotFound, json) })
        val missing = runCatching { older.createJobFromPages(listOf(UploadSource.of("page.png", png)), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(404, missing.status)
        assertNull(missing.code)
    }

    @Test
    fun theInputCodesAreTheEngines() {
        val pages = File(checkNotNull(System.getProperty("scribe.engine")) { "scribe.engine is not set by the build" }, "pages.py")
        assertTrue("$pages is not there", pages.isFile)
        val text = pages.readText()
        fun code(name: String) = Regex("^$name = \"([a-z_]+)\"", RegexOption.MULTILINE).find(text)?.groupValues?.get(1)
        assertEquals(InputRefusal.NOT_A_PAGE, code("NOT_A_PAGE"))
        assertEquals(InputRefusal.WRONG_INPUT, code("WRONG_INPUT"))
        assertEquals(InputRefusal.PAGE_TOO_LARGE, code("PAGE_TOO_LARGE"))
        assertEquals("MAX_PAGE_BYTES = 50 * 1024 * 1024", Regex("^MAX_PAGE_BYTES = [^#\n]*", RegexOption.MULTILINE).find(text)?.value?.trim())
        assertEquals(50L * 1024 * 1024, EngineApi.MAX_PAGE_BYTES)
        val sheet = File(pages.parentFile, "sheet.py").readText()
        assertEquals(InputRefusal.READER_MISSING, Regex("^READER_MISSING = \"([a-z_]+)\"", RegexOption.MULTILINE).find(sheet)?.groupValues?.get(1))
        assertEquals(EngineApi.MAX_PAGES, Regex("^MAX_PAGES = (\\d+)", RegexOption.MULTILINE).find(text)?.groupValues?.get(1)?.toInt())
    }

    @Test
    fun theFixtureComputerReadsPagesIntoTheHymnsScore() = runTest {
        val api = computer("old-hundredth")
        assertEquals(listOf("sheet", "sheet-tab"), api.profiles().filter { it.input == Profile.INPUT_PAGES }.map { it.name })
        assertTrue(api.profiles().filter { it.input != Profile.INPUT_PAGES }.all { it.input == "audio" })
        val progress = mutableListOf<Pair<Long, Long>>()
        val job = api.createJobFromPages(listOf(UploadSource.of("p1.png", png), UploadSource.of("p2.pdf", pdf)), Profile.SHEET, "Old Hundredth",
            onProgress = { sent, total -> progress += sent to total })
        assertEquals("sheet", job.profile)
        assertEquals("brass", job.target)
        assertEquals("Old Hundredth", job.title)
        assertEquals(listOf("read", "arrange", "export"), job.stages.map { it.name })
        assertEquals((png.size + pdf.size).toLong() to (png.size + pdf.size).toLong(), progress.last())
        assertEquals(progress.map { it.first }.sorted(), progress.map { it.first })
        assertEquals("succeeded", api.events(job.id).toList().last().status)
        assertTrue(api.musicXml(job.id).contains("score-partwise"))
        assertTrue(api.composition(job.id).voices.isNotEmpty())
    }

    @Test
    fun theFixtureComputerReadsPagesIntoATab() = runTest {
        val api = computer("guitar-line")
        val job = api.createJobFromPages(listOf(UploadSource.of("p1.png", png)), Profile.SHEET_TAB, "A line",
            tab = TabOptions(FrettedInstrument.GUITAR_6, "standard", 0, octave = Octave.AUTO, layout = TabLayout.TAB))
        assertEquals(listOf("read", "notes", "arrange", "export"), job.stages.map { it.name })
        assertEquals("fretted", job.target)
        api.events(job.id).toList()
        assertTrue(api.tab(job.id).notes.isNotEmpty())
        // What is asked about a recording is refused, as the engine refuses it.
        val refused = runCatching {
            api.createJobFromPages(listOf(UploadSource.of("p1.png", png)), Profile.SHEET_TAB, null, tab = TabOptions(recording = Recording.SONG))
        }.exceptionOrNull() as EngineException
        assertEquals(422, refused.status)
    }

    @Test
    fun theNewerRefusalsKeepTheirCodes() = runBlocking {
        fun answers(status: HttpStatusCode, code: String) = matchingEngine("http://host", MockEngine { respond("""{"code":"$code","detail":"..."}""", status, json) })
        val large = runCatching { answers(HttpStatusCode.PayloadTooLarge, "page_too_large").createJobFromPages(listOf(UploadSource.of("big.pdf", pdf)), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(413 to InputRefusal.PAGE_TOO_LARGE, large.status to large.code)
        val missing = runCatching { answers(HttpStatusCode.ServiceUnavailable, "reader_missing").createJobFromPages(listOf(UploadSource.of("p.png", png)), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(503 to InputRefusal.READER_MISSING, missing.status to missing.code)
    }

    @Test
    fun theFixtureComputerPlaysTheEnginesOtherAnswers() = runTest {
        // Only PNG, JPEG, WebP and PDF are pages: a TIFF and a BMP are not.
        val api = computer("old-hundredth")
        for (other in listOf(byteArrayOf(0x49, 0x49, 0x2A, 0x00, 8, 0, 0, 0), "BM".toByteArray() + ByteArray(12))) {
            val e = runCatching { api.createJobFromPages(listOf(UploadSource.of("page", other)), Profile.SHEET, null) }.exceptionOrNull() as EngineException
            assertEquals(415 to InputRefusal.NOT_A_PAGE, e.status to e.code)
        }
        // A file over the engine's size, by the size it says it has.
        val big = UploadSource("big.pdf", EngineApi.MAX_PAGE_BYTES + 1) { pdf.inputStream() }
        val large = runCatching { api.createJobFromPages(listOf(big), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(413 to InputRefusal.PAGE_TOO_LARGE, large.status to large.code)
        // A computer without the reader: no profile that reads pages, and the address says why.
        val bare = computer("old-hundredth", also = mapOf(FixtureEngineApi.NO_READER_FILE to ""))
        assertTrue(bare.profiles().none { it.input == Profile.INPUT_PAGES })
        assertTrue(bare.profiles().any { it.name == "solo" })
        val missing = runCatching { bare.createJobFromPages(listOf(UploadSource.of("p.png", png)), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(503 to InputRefusal.READER_MISSING, missing.status to missing.code)
        // A job that fails, in the engine's fixed words after its stage's name.
        val failing = computer("old-hundredth", also = mapOf(FixtureEngineApi.JOB_ERROR_FILE to "no notes were found on the page\n"))
        val job = failing.createJobFromPages(listOf(UploadSource.of("p.png", png)), Profile.SHEET, null)
        val events = failing.events(job.id).toList()
        assertEquals("failed", events.last().status)
        assertEquals(JobStatus.FAILED, failing.job(job.id).status)
        assertEquals("read: no notes were found on the page", failing.job(job.id).error)
    }

    @Test
    fun theFixtureComputerRefusesWhatTheEngineRefuses() = runTest {
        val api = computer("old-hundredth")
        val wav = "RIFF".toByteArray() + ByteArray(4) + "WAVEfmt ".toByteArray()
        val notAPage = runCatching { api.createJobFromPages(listOf(UploadSource.of("p1.png", png), UploadSource.of("take.wav", wav)), Profile.SHEET, null) }.exceptionOrNull() as EngineException
        assertEquals(415, notAPage.status)
        assertEquals(InputRefusal.NOT_A_PAGE, notAPage.code)
        val wrong = runCatching { api.createJobFromPages(listOf(UploadSource.of("p1.png", png)), Profile.SOLO, null) }.exceptionOrNull() as EngineException
        assertEquals(InputRefusal.WRONG_INPUT, wrong.code)
        assertEquals(422, (runCatching { api.createJobFromPages(emptyList(), Profile.SHEET, null) }.exceptionOrNull() as EngineException).status)
        val many = List(EngineApi.MAX_PAGES + 1) { UploadSource.of("p$it.png", png) }
        assertEquals(422, (runCatching { api.createJobFromPages(many, Profile.SHEET, null) }.exceptionOrNull() as EngineException).status)
        // A computer from before the pages: no such address, and no such profile.
        val older = computer("old-hundredth", only = listOf("solo", "brass-band", "orchestra-with-soloist", "pop-rock", "tab", "bass-tab"))
        assertTrue(older.profiles().none { it.input == Profile.INPUT_PAGES })
        assertEquals(404, (runCatching { older.createJobFromPages(listOf(UploadSource.of("p1.png", png)), Profile.SHEET, null) }.exceptionOrNull() as EngineException).status)
    }
}
