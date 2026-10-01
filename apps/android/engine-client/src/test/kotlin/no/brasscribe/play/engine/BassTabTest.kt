package no.brasscribe.play.engine

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import no.brasscribe.play.model.BrasscribeJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * The bass-tab profile against apps/fixtures/bass-line: what the engine answered for a job on a short
 * synthesized bass line (apps/fixtures/make-bass-line.py records it).
 */
class BassTabTest {
    private val fixture = File(System.getProperty("brasscribe.fixtures"), "bass-line")
    private val json = headersOf(HttpHeaders.ContentType, "application/json")

    private fun text(name: String) = File(fixture, name).readText()
    private fun tabOf(text: String) = BrasscribeJson.decodeFromString(Tab.serializer(), text)
    private fun encoded(job: JobCreate) = BrasscribeJson.encodeToJsonElement(JobCreate.serializer(), job).jsonObject

    /** The options of the recorded job. */
    private val recorded = TabOptions(FrettedInstrument.BASS_4, "standard", 0, FingeringStyle.AS_PLAYED, Recording.INSTRUMENT, Octave.AUTO, TabLayout.TAB)

    @Test
    fun decodesTheRecordedTab() {
        val tab = tabOf(text("tab.json"))
        assertEquals(FrettedInstrument.BASS_4.preset(), tab.preset)
        assertEquals(FingeringStyle.AS_PLAYED, tab.style)
        assertEquals(TabLayout.TAB, tab.layout)
        assertEquals(OctaveSource.AUTO, tab.octaveSource)
        assertEquals(0, tab.octaveShift)
        assertEquals(TabKey("Em", 1, KeyMode.MINOR), tab.key)
        assertEquals(100.0, tab.tempoBpm, 0.0)
        assertEquals(24, tab.ticksPerBeat)
        assertEquals(listOf(43, 38, 33, 28), tab.instrument.tuning.strings.map { it.openPitch })
        assertEquals("Standard", tab.instrument.tuning.name)
        assertEquals(0, tab.instrument.capo)
        assertTrue(tab.violations.isEmpty())
        assertNull("the tab was made for the tuning that fits best", tab.suggestedTuning)
        assertEquals(FrettedInstrument.BASS_4.tunings.map { FrettedInstrument.BASS_4.preset(it) }.toSet(), tab.tuningSuggestions.map { it.preset }.toSet())
        assertEquals(false, tab.referencePitch!!.retuned)
        assertTrue(tab.beatTimes.size > 25 && tab.beatTimes.zipWithNext().all { (a, b) -> b > a })

        // Every note is where its string and fret say: the open string, the capo and the fret add up to the pitch.
        assertTrue(tab.notes.size > 25)
        for (n in tab.notes) {
            val at = n.position!!
            assertEquals(n.pitch, tab.instrument.tuning.strings[at.string - 1].openPitch + tab.instrument.capo + at.fret)
            assertFalse(n.outOfRange || n.pinned || n.octaveMoved || n.doubtful)
            assertTrue(n.onsetS!! < n.offsetS!!)
        }
        assertEquals(TabPosition(4, 0), tab.notes.first().position)  // the line starts on the open E string
        assertEquals(tab.notes.map { it.start }.sorted(), tab.notes.map { it.start })
    }

    @Test
    fun theRecordedJobAndItsFilesAgreeWithTheTab() {
        val job = BrasscribeJson.decodeFromString(Job.serializer(), text("job.json"))
        assertEquals(Profile.BASS_TAB, Profile.of(job.profile))
        assertEquals(JobStatus.SUCCEEDED, job.status)
        assertEquals(FixtureEngineApi.stagesOf(Profile.BASS_TAB, wholeRecording = true), job.stages.map { it.name })
        assertEquals(job.stages.map { it.kind }, job.stages.map { FixtureEngineApi.kindOf(it.name) })
        assertTrue(job.stages.all { it.status.done })
        assertEquals(listOf("composition.json", "tab.json", "tab.musicxml"), job.outputs)

        val tab = tabOf(text("tab.json"))
        val xml = text("tab.musicxml")
        assertTrue(xml.contains("<work-title>${job.title}</work-title>") && xml.contains("<sign>TAB</sign>"))
        // A note held over a bar line is written once in each bar, tied.
        assertTrue(Regex("<fret>").findAll(xml).count() >= tab.notes.size)
        val bass = no.brasscribe.play.model.CompositionJson.decode(text("composition.json")).voices.single()
        assertEquals(tab.notes.map { it.pitch }, bass.notes.map { it.pitch })
    }

    @Test
    fun nothingInTheFixtureNamesTheComputerItWasRecordedOn() {
        val files = fixture.listFiles()!!.filter { it.isFile }
        assertEquals(setOf("request.json", "job.json", "tab.json", "tab.musicxml", "composition.json"), files.map { it.name }.toSet())
        for (f in files) {
            val machine = Regex("/Users/|/home/|/tmp/|/var/|[A-Za-z]:\\\\\\\\|\\.local\\b|\\b\\d{1,3}(\\.\\d{1,3}){3}\\b").find(f.readText())
            assertNull("${f.name}: ${machine?.value}", machine)
        }
    }

    @Test
    fun theOptionsAreSentAsTheEngineAcceptedThem() {
        // request.json is the body the engine accepted when the fixture was recorded.
        val accepted = BrasscribeJson.parseToJsonElement(text("request.json")).jsonObject
        val audioId = (accepted.getValue("audio_id") as kotlinx.serialization.json.JsonPrimitive).content
        assertEquals(accepted, encoded(JobCreate.bassTab(audioId, recorded, "Bass line")))
    }

    @Test
    fun everyOptionGoesOutUnderTheEnginesNameAndValue() {
        val body = encoded(JobCreate.bassTab("a1", TabOptions(FrettedInstrument.BASS_5, "drop-a", 2, FingeringStyle.OPEN_POSITION, Recording.SONG,
            Octave.UP, TabLayout.TAB_AND_NOTATION)))
        val sent = listOf("profile", "instrument", "tuning", "capo", "style", "recording", "octave", "layout").associateWith { body.getValue(it).toString() }
        assertEquals(mapOf("profile" to "\"bass-tab\"", "instrument" to "\"bass-5\"", "tuning" to "\"drop-a\"", "capo" to "2",
            "style" to "\"open-position\"", "recording" to "\"song\"", "octave" to "\"+12\"", "layout" to "\"tab-and-notation\""), sent)
        assertEquals("\"-12\"", encoded(JobCreate.bassTab("a1", TabOptions(octave = Octave.DOWN))).getValue("octave").toString())
        assertEquals("\"0\"", encoded(JobCreate.bassTab("a1", TabOptions(octave = Octave.AS_HEARD))).getValue("octave").toString())
    }

    @Test
    fun anOptionLeftOutIsNotSent() {
        val tabKeys = setOf("instrument", "tuning", "capo", "style", "recording", "octave", "layout")
        // The engine refuses a tab option on any other profile, and fills in its own defaults for a tab.
        assertEquals(emptySet<String>(), encoded(JobCreate("a1", Profile.BRASS_BAND.id)).keys intersect tabKeys)
        assertEquals(emptySet<String>(), encoded(JobCreate.bassTab("a1")).keys intersect tabKeys)
        assertEquals(setOf("capo"), encoded(JobCreate.bassTab("a1", TabOptions(capo = 3))).keys intersect tabKeys)
    }

    @Test
    fun theStandInForAnUnknownValueIsNeverSent() {
        val e = runCatching { encoded(JobCreate.bassTab("a1", TabOptions(style = FingeringStyle.UNKNOWN))) }.exceptionOrNull()
        assertTrue("$e", e is SerializationException)
        assertTrue(runCatching { TabOptions(octave = Octave.UNKNOWN).formFields() }.exceptionOrNull() is IllegalArgumentException)
    }

    @Test
    fun aNewerEnginesValuesAndFieldsDoNotStopTheTabFromDecoding() {
        val recordedTab = BrasscribeJson.parseToJsonElement(text("tab.json")).jsonObject
        fun JsonObject.with(vararg changes: Pair<String, String>) =
            JsonObject(this + changes.associate { (k, v) -> k to BrasscribeJson.parseToJsonElement(v) })
        val note = recordedTab.getValue("notes").let { (it as kotlinx.serialization.json.JsonArray).first().jsonObject }
        val newer = recordedTab.with(
            "style" to "\"slap\"", "layout" to "\"chord-chart\"", "octave_source" to "\"player\"", "techniques_heard" to "{\"slides\":2}",
            "key" to "{\"name\":\"E dorian\",\"fifths\":2,\"mode\":\"dorian\",\"confidence\":0.6}",
            "notes" to "[${note.with("technique" to "\"slide\"", "finger" to "2")}]",
            "violations" to "[{\"kind\":\"finger-stretch\",\"notes\":[0,3],\"fingers\":[1,4]},{\"kind\":\"ring-cut\",\"string\":3,\"ringing\":4,\"note\":6}]",
        )
        val tab = tabOf(newer.toString())
        assertEquals(listOf(FingeringStyle.UNKNOWN, TabLayout.UNKNOWN, OctaveSource.UNKNOWN, KeyMode.UNKNOWN),
            listOf(tab.style, tab.layout, tab.octaveSource, tab.key.mode))
        assertEquals("E dorian", tab.key.name)
        assertEquals(tabOf(text("tab.json")).notes.first(), tab.notes.single())
        // A kind this client has no words for keeps the notes it names.
        assertEquals(listOf("finger-stretch" to listOf(0, 3), "ring-cut" to listOf(4, 6)), tab.violations.map { it.kind to it.noteIndices })

        // A field the schema has a default for may be missing; a note with no place has no string and no fret.
        val older = recordedTab.with("notes" to "[{\"pitch\":20,\"start\":0,\"dur\":24,\"string\":null,\"alternatives\":[],\"out_of_range\":true}]",
            "reference_pitch" to "null") - "octave_notes_moved" - "ticks_per_beat"
        val bare = tabOf(JsonObject(older).toString())
        assertEquals(TabNote(20, 0, 24, null, emptyList(), true), bare.notes.single())
        assertNull(bare.notes.single().position)
        assertEquals(1.0, bare.notes.single().confidence, 0.0)
        assertNull(bare.referencePitch)
        assertEquals(0 to 24, bare.octaveNotesMoved to bare.ticksPerBeat)

        // The same holds for a job that names its options back, and for the options an engine may add.
        val job = BrasscribeJson.decodeFromString(JobCreate.serializer(), """{"audio_id":"a","profile":"bass-tab","instrument":"bass-7","octave":"-24","tuning":"f#-standard","frets":24}""")
        assertEquals(Triple(FrettedInstrument.UNKNOWN, Octave.UNKNOWN, "f#-standard"), Triple(job.instrument, job.octave, job.tuning))
    }

    @Test
    fun aTuningTheSongSoundsLikeIsSuggested() {
        val tab = tabOf(text("tab.json"))
        val dropD = tab.copy(tuningSuggestions = tab.tuningSuggestions.sortedByDescending { it.preset == "bass-4-drop-d" })
        assertEquals("Drop D", dropD.suggestedTuning?.tuning)
    }

    @Test
    fun readsTheTabAndItsFilesFromTheEngine() = runTest {
        val seen = mutableListOf<String>()
        val engine = MockEngine { req ->
            seen += "${req.method.value} ${req.url.encodedPath}"
            when (req.url.encodedPath) {
                "/v1/jobs/r1/tab" -> respond(text("tab.json"), HttpStatusCode.OK, json)
                "/v1/jobs/r1/musicxml" -> respond(text("tab.musicxml"), HttpStatusCode.OK)
                "/v1/jobs/r1/pdf" -> respond("%PDF-1.7", HttpStatusCode.OK)
                "/v1/jobs/r1/midi" -> respond("MThd", HttpStatusCode.OK)
                "/v1/jobs/r1/artifacts/tab.musicxml" -> respond(text("tab.musicxml"), HttpStatusCode.OK)
                // Another profile's job, or one that is not finished.
                else -> respond("""{"detail":"Not Found"}""", HttpStatusCode.NotFound, json)
            }
        }
        val api = KtorEngineApi("http://host", engine, token = "t")
        assertEquals(tabOf(text("tab.json")), api.tab("r1"))
        assertEquals(text("tab.musicxml"), api.musicXml("r1"))
        assertEquals("%PDF-1.7", String(api.pdf("r1")))
        assertEquals("MThd", String(api.midi("r1")))
        assertEquals(text("tab.musicxml"), String(api.artifact("r1", "tab.musicxml")))
        assertEquals(404, (runCatching { api.tab("r2") }.exceptionOrNull() as EngineException).status)
        assertEquals(listOf("GET /v1/jobs/r1/tab", "GET /v1/jobs/r1/musicxml", "GET /v1/jobs/r1/pdf", "GET /v1/jobs/r1/midi",
            "GET /v1/jobs/r1/artifacts/tab.musicxml", "GET /v1/jobs/r2/tab"), seen)
    }

    @Test
    fun theUploadFormCarriesTheOptionsThatAreSet() = runTest {
        var body = ""
        val engine = MockEngine { req ->
            body = String(req.body.toByteArray())
            respond(text("job.json"), HttpStatusCode.Accepted, json)
        }
        val api = KtorEngineApi("http://host", engine)
        fun field(name: String) = Regex("name=\"?$name\"?\\s*\\r\\n(?:[^\\r\\n]+\\r\\n)*\\r\\n([^\\r\\n]*)\\r\\n").find(body)?.groupValues?.get(1)
        val job = api.createJobFromUpload("take.wav", ByteArray(10), Profile.BASS_TAB, "Take 1",
            tab = TabOptions(FrettedInstrument.BASS_5, capo = 2, recording = Recording.INSTRUMENT, octave = Octave.UP))
        assertEquals(Profile.BASS_TAB.id, job.profile)
        assertEquals(listOf("bass-tab", "bass-5", "2", "instrument", "+12"), listOf("profile", "instrument", "capo", "recording", "octave").map { field(it) })
        assertEquals(listOf(null, null, null), listOf("tuning", "style", "layout").map { field(it) })
        api.createJobFromUpload("take.wav", ByteArray(10), Profile.SOLO, "Take 1")
        assertEquals("solo", field("profile"))
        assertNull(field("instrument"))
    }

    @Test
    fun aComputerThatCannotWriteTabIsAnErrorTheAppCanName() = runTest {
        // The engine's 422 bodies: the code first, then its English message.
        val refused = """{"code":"core_missing","detail":"this engine cannot write tab: brasscribe-core is not installed with it (build it with `cargo build --release -p brasscribe-cli` in core/)"}"""
        fun api(body: String, status: HttpStatusCode = HttpStatusCode.UnprocessableEntity) = KtorEngineApi("http://host", MockEngine { respond(body, status, json) })
        suspend fun refusal(api: KtorEngineApi) = runCatching { api.createJob(JobCreate.bassTab("a1")) }.exceptionOrNull() as EngineException

        val missing = refusal(api(refused))
        assertEquals(422, missing.status)
        assertEquals(Refusal.CORE_MISSING, missing.refusal)
        assertEquals("core_missing", missing.code)
        val upload = runCatching { api(refused).createJobFromUpload("take.wav", ByteArray(4), Profile.BASS_TAB, null) }.exceptionOrNull() as EngineException
        assertEquals(Refusal.CORE_MISSING, upload.refusal)

        assertEquals(Refusal.INVALID_OPTIONS, refusal(api("""{"code":"invalid_options","detail":"these job options don't fit together"}""")).refusal)
        // A code from a newer engine, a validation error without a code, and an error that is not a refusal.
        val newer = refusal(api("""{"code":"instrument_not_supported","detail":"..."}"""))
        assertEquals("instrument_not_supported" to null, newer.code to newer.refusal)
        assertNull(refusal(api("""{"detail":[{"type":"enum","loc":["body","octave"],"msg":"Input should be 'auto', '0', '-12' or '+12'"}]}""")).refusal)
        assertNull(refusal(api("""{"detail":"no such audio"}""", HttpStatusCode.NotFound)).refusal)
        assertNull(EngineException(0, "unreachable").refusal)
    }

    @Test
    fun theRefusalCodesAreTheEngines() {
        val profiles = File(System.getProperty("brasscribe.engine") ?: "missing", "profiles.py")
        assumeTrue("the engine is not in this checkout", profiles.isFile)
        val codes = Regex("^[A-Z_]+_CODE = \"([a-z_]+)\"", RegexOption.MULTILINE).findAll(profiles.readText()).map { it.groupValues[1] }.toSet()
        assertEquals(codes, Refusal.entries.map { it.code }.toSet())
    }

    @Test
    fun theFixtureEngineReplaysTheRecordedJob() = runTest {
        val api = FixtureEngineApi(DirectoryFixtureSource(fixture), stageSeconds = 0.0)
        assertTrue(Profile.BASS_TAB.id in api.profiles().map { it.name })
        val job = api.createJobFromUpload("bass-line.wav", ByteArray(64), Profile.BASS_TAB, "Bass line", tab = recorded)
        val recordedJob = BrasscribeJson.decodeFromString(Job.serializer(), text("job.json"))
        assertEquals(recordedJob.stages.map { it.name to it.kind }, job.stages.map { it.name to it.kind })
        assertEquals(404, (runCatching { api.tab("nope") }.exceptionOrNull() as EngineException).status)

        val events = api.events(job.id).toList()
        val tracker = ProgressTracker(job.stages.size)
        events.forEach { tracker.onEvent(it) }
        assertEquals(JobStatus.SUCCEEDED, tracker.progress.status)
        val done = api.job(job.id)
        assertEquals(recordedJob.outputs, done.outputs)

        assertEquals(tabOf(text("tab.json")), api.tab(job.id))
        assertEquals(text("tab.musicxml"), api.musicXml(job.id))
        assertEquals(text("tab.musicxml"), String(api.artifact(job.id, "tab.musicxml")))
        assertEquals(listOf("bass"), api.composition(job.id).voices.map { it.id })
        assertEquals(listOf("composition.json" to "application/json", "tab.json" to "application/json",
            "tab.musicxml" to "application/vnd.recordare.musicxml+xml"), api.artifacts(job.id).map { it.name to it.mediaType })
        // Recorded without MuseScore: no PDF and no MIDI, as on a computer that has none.
        assertEquals(404, (runCatching { api.pdf(job.id) }.exceptionOrNull() as EngineException).status)
        assertEquals(404, (runCatching { api.midi(job.id) }.exceptionOrNull() as EngineException).status)

        // A song is separated first; a band job has no tab and takes no tab options.
        val song = api.createJob(JobCreate.bassTab("a1", TabOptions(recording = Recording.SONG)))
        assertEquals(FixtureEngineApi.stagesOf(Profile.BASS_TAB), song.stages.map { it.name })
        assertTrue("stems" in song.stages.map { it.name } && "stems" !in job.stages.map { it.name })
        val band = api.createJob(JobCreate("a1", Profile.BRASS_BAND.id))
        assertEquals(404, (runCatching { api.tab(band.id) }.exceptionOrNull() as EngineException).status)
        val refused = runCatching { api.createJob(JobCreate("a1", Profile.BRASS_BAND.id, capo = 2)) }.exceptionOrNull() as EngineException
        assertEquals(Refusal.INVALID_OPTIONS, refused.refusal)
    }
}
