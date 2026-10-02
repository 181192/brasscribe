package no.brasscribe.play.engine

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
 * The tab profile for every instrument, against apps/fixtures/guitar-line and ukulele-line: what the engine
 * answered for a job on a short synthesized take of each (apps/fixtures/make-fretted-lines.py records them).
 */
class TabProfileTest {
    private val fixtures = File(System.getProperty("brasscribe.fixtures"))
    private val takes = listOf("guitar-line", "ukulele-line")

    private fun text(take: String, name: String) = File(File(fixtures, take), name).readText()
    private fun tabOf(text: String) = BrasscribeJson.decodeFromString(Tab.serializer(), text)
    private fun tab(take: String) = tabOf(text(take, "tab.json"))
    private fun encoded(job: JobCreate) = BrasscribeJson.encodeToJsonElement(JobCreate.serializer(), job).jsonObject

    /** The options of the recorded jobs: what the app names for a first job (no fingering style, no chords). */
    private val recorded = mapOf(
        "guitar-line" to TabOptions(FrettedInstrument.GUITAR_6, "standard", 0, recording = Recording.INSTRUMENT, octave = Octave.AUTO, layout = TabLayout.TAB),
        "ukulele-line" to TabOptions(FrettedInstrument.UKULELE, "high-g", 0, recording = Recording.INSTRUMENT, octave = Octave.AUTO, layout = TabLayout.TAB),
    )

    @Test
    fun aTabJobIsOfEitherProfileIdAndABandJobIsNot() {
        assertEquals(listOf(Profile.TAB, Profile.BASS_TAB), Profile.entries.filter { it.writesTab })
        assertTrue(Profile.writesTab("tab") && Profile.writesTab("bass-tab"))
        listOf("solo", "brass-band", "orchestra-with-soloist", "pop-rock", "tabs", "", "a-newer-profile").forEach { assertFalse(it, Profile.writesTab(it)) }
        assertEquals("tab", JobCreate.tab("a1").profile)
        assertEquals("bass-tab", JobCreate.bassTab("a1").profile)
    }

    @Test
    fun everyPresetIsOneOfTheCratesAndNamesItsInstrumentAndTuning() {
        val ours = FrettedInstrument.entries.filter { it.id != null }.flatMap { i -> i.tunings.map { i.preset(it) } }
        assertEquals("two tunings share a preset", ours.size, ours.toSet().size)
        for (i in FrettedInstrument.entries.filter { it.id != null }) for (tuning in i.tunings) {
            assertEquals(i to tuning, FrettedInstrument.ofPreset(i.preset(tuning)))
        }
        // The ones whose id is not "<instrument>-<tuning>".
        assertEquals("guitar-standard", FrettedInstrument.GUITAR_6.preset())
        assertEquals("guitar-drop-d", FrettedInstrument.GUITAR_6.preset("drop-d"))
        assertEquals("guitar-7-standard", FrettedInstrument.GUITAR_7.preset())
        assertEquals("ukulele-high-g", FrettedInstrument.UKULELE.preset())
        assertEquals("ukulele-baritone", FrettedInstrument.UKULELE_BARITONE.preset())
        assertEquals("mandolin", FrettedInstrument.MANDOLIN.preset())
        assertEquals(FrettedInstrument.UKULELE_BARITONE to "standard", FrettedInstrument.ofPreset("ukulele-baritone"))
        // One this client does not know, or only the start of one, names nothing.
        listOf("banjo-open-g", "guitar", "ukulele", "bass-4", "guitar-6-standard", "mandolin-standard", "").forEach { assertNull(it, FrettedInstrument.ofPreset(it)) }

        val source = File(System.getProperty("brasscribe.presets") ?: "missing")
        assumeTrue("core/target-fretted is not in this checkout", source.isFile)
        val list = source.readText().substringAfter("pub const PRESET_IDS: &[&str] = &[").substringBefore("];")
        val crate = Regex("\"([^\"]+)\"").findAll(list).map { it.groupValues[1] }.toList()
        assertTrue("no presets found in ${source.name}", crate.isNotEmpty())
        assertEquals(crate.toSet(), ours.toSet())
        // Within an instrument the order is the crate's: the usual tuning first.
        for (i in FrettedInstrument.entries.filter { it.id != null }) {
            assertEquals(i.id, crate.filter { FrettedInstrument.ofPreset(it)?.first == i }, i.tunings.map { i.preset(it) })
        }
    }

    @Test
    fun decodesTheRecordedGuitarAndUkuleleTabs() {
        val guitar = tab("guitar-line")
        assertEquals(FrettedInstrument.GUITAR_6 to "standard", FrettedInstrument.ofPreset(guitar.preset))
        assertEquals(NotationClef.TREBLE_8VB, guitar.instrument.notation)
        assertEquals(listOf(64, 59, 55, 50, 45, 40), guitar.instrument.tuning.strings.map { it.openPitch })
        // The synthesized take sounds lower than a guitar in places: another tuning fits it better.
        assertEquals(FrettedInstrument.GUITAR_6, guitar.suggestedTuning?.preset?.let(FrettedInstrument::ofPreset)?.first)
        assertEquals(FrettedInstrument.GUITAR_6.tunings.map { FrettedInstrument.GUITAR_6.preset(it) }.toSet(), guitar.tuningSuggestions.map { it.preset }.toSet())

        val ukulele = tab("ukulele-line")
        assertEquals(FrettedInstrument.UKULELE to "high-g", FrettedInstrument.ofPreset(ukulele.preset))
        assertEquals(NotationClef.TREBLE, ukulele.instrument.notation)
        assertEquals(listOf(69, 64, 60, 67), ukulele.instrument.tuning.strings.map { it.openPitch })
        // The G of its G chord sounds on two strings: heard once, written twice.
        assertTrue(ukulele.doubledNotes > 0)
        assertEquals(ukulele.doubledNotes, ukulele.notes.count { it.doubled })
        assertEquals(0, guitar.doubledNotes)

        for (tab in listOf(guitar, ukulele)) {
            assertEquals(0, tab.instrument.capo)
            assertEquals(0, tab.unplayableDropped)
            assertTrue(tab.leftoversDropped > 0)
            // Chords were written as they were heard: nothing was added.
            assertEquals(0, tab.inferredNotes)
            assertTrue(tab.notes.none { it.inferred })
            assertTrue(tab.notes.size > 40)
            // Chords: several notes on one onset, each on its own string.
            val strums = tab.notes.groupBy { it.start }.values.filter { it.size >= 3 }
            assertTrue(strums.size >= 5)
            strums.forEach { strum -> strum.mapNotNull { it.string }.let { strings -> assertEquals(strings.size, strings.toSet().size) } }
            // Every note with a place is where its string and fret say.
            for (n in tab.notes) {
                val at = n.position ?: continue
                assertEquals(n.pitch, tab.instrument.tuning.strings[at.string - 1].openPitch + tab.instrument.capo + at.fret)
            }
            assertEquals(tab.notes.count { it.outOfRange }, tab.notes.count { it.position == null })
        }
    }

    @Test
    fun theRecordedJobsAndTheirFilesAgreeWithTheTabs() {
        for (take in takes) {
            val job = BrasscribeJson.decodeFromString(Job.serializer(), text(take, "job.json"))
            assertEquals(take, Profile.TAB, Profile.of(job.profile))
            assertEquals(JobStatus.SUCCEEDED, job.status)
            assertEquals(FixtureEngineApi.stagesOf(Profile.TAB, wholeRecording = true, instrument = recorded.getValue(take).instrument), job.stages.map { it.name })
            assertEquals(job.stages.map { it.kind }, job.stages.map { FixtureEngineApi.kindOf(it.name) })
            assertEquals(listOf("composition.json", "tab.json", "tab.musicxml"), job.outputs)
            val xml = text(take, "tab.musicxml")
            assertTrue(xml.contains("<work-title>${job.title}</work-title>") && xml.contains("<sign>TAB</sign>"))
            assertTrue(Regex("<fret>").findAll(xml).count() >= tab(take).notes.count { it.position != null })
        }
    }

    @Test
    fun nothingInTheFixturesNamesTheComputerTheyWereRecordedOn() {
        for (take in takes) {
            val files = File(fixtures, take).listFiles()!!.filter { it.isFile }
            assertEquals(setOf("request.json", "job.json", "tab.json", "tab.musicxml", "composition.json"), files.map { it.name }.toSet())
            for (f in files) {
                val machine = Regex("/Users/|/home/|/tmp/|/var/|[A-Za-z]:\\\\\\\\|\\.local\\b|\\b\\d{1,3}(\\.\\d{1,3}){3}\\b").find(f.readText())
                assertNull("$take/${f.name}: ${machine?.value}", machine)
            }
            // Which device each stage ran on differs from computer to computer: it is left out.
            val job = BrasscribeJson.decodeFromString(Job.serializer(), text(take, "job.json"))
            assertTrue(take, job.stages.all { it.device == null })
            assertNull(job.deviceName)
        }
    }

    @Test
    fun theOptionsAreSentAsTheEngineAcceptedThem() {
        for (take in takes) {
            // request.json is the body the engine accepted when the fixture was recorded.
            val accepted = BrasscribeJson.parseToJsonElement(text(take, "request.json")).jsonObject
            val audioId = (accepted.getValue("audio_id") as JsonPrimitive).content
            val title = (accepted.getValue("title") as JsonPrimitive).content
            assertEquals(take, accepted, encoded(JobCreate.tab(audioId, recorded.getValue(take), title)))
        }
        // Chords are sent only when they are named.
        assertFalse("chords" in encoded(JobCreate.tab("a1", recorded.getValue("guitar-line"))))
        assertEquals("\"completed\"", encoded(JobCreate.tab("a1", TabOptions(chords = TabChords.COMPLETED))).getValue("chords").toString())
        assertEquals("chords" to "heard", TabOptions(chords = TabChords.HEARD).formFields().single())
    }

    @Test
    fun aTabFromAnEngineBeforeTheseFieldsAndOneFromANewerEngineBothDecode() {
        // The bass line was recorded before the tab said what it left out: those read as nothing left out.
        val older = tab("bass-line")
        assertEquals(listOf(0, 0, 0, 0), listOf(older.unplayableDropped, older.leftoversDropped, older.doubledNotes, older.inferredNotes))
        assertTrue(older.notes.none { it.doubled || it.inferred })
        val recordedTab = BrasscribeJson.parseToJsonElement(text("guitar-line", "tab.json")).jsonObject
        val bare = JsonObject(recordedTab + ("instrument" to JsonObject(recordedTab.getValue("instrument").jsonObject - "notation")))
        assertNull(tabOf(bare.toString()).instrument.notation)

        // A clef, an instrument and a chords choice a newer engine added do not stop the answer from decoding.
        val newer = JsonObject(recordedTab + ("preset" to JsonPrimitive("banjo-open-g")) +
            ("instrument" to JsonObject(recordedTab.getValue("instrument").jsonObject + ("notation" to JsonPrimitive("tenor")))))
        val tab = tabOf(newer.toString())
        assertEquals(NotationClef.UNKNOWN, tab.instrument.notation)
        assertNull(FrettedInstrument.ofPreset(tab.preset))
        val job = BrasscribeJson.decodeFromString(JobCreate.serializer(), """{"audio_id":"a","profile":"tab","instrument":"banjo-5","chords":"guessed","tuning":"open-g"}""")
        assertEquals(Triple(FrettedInstrument.UNKNOWN, TabChords.UNKNOWN, "open-g"), Triple(job.instrument, job.chords, job.tuning))
        // The stand-in is never sent.
        assertTrue(runCatching { TabOptions(chords = TabChords.UNKNOWN).formFields() }.exceptionOrNull() is IllegalArgumentException)
    }

    @Test
    fun theFixtureEngineReplaysTheRecordedJobsAndRefusesWhatTheEngineRefuses() = runTest {
        for (take in takes) {
            val api = FixtureEngineApi(DirectoryFixtureSource(File(fixtures, take)), stageSeconds = 0.0)
            assertTrue(Profile.TAB.id in api.profiles().map { it.name })
            val job = api.createJobFromUpload("$take.wav", ByteArray(64), Profile.TAB, take, tab = recorded.getValue(take))
            val recordedJob = BrasscribeJson.decodeFromString(Job.serializer(), text(take, "job.json"))
            assertEquals(recordedJob.stages.map { it.name to it.kind }, job.stages.map { it.name to it.kind })
            api.events(job.id).toList()
            assertEquals(recordedJob.outputs, api.job(job.id).outputs)
            assertEquals(tab(take), api.tab(job.id))
            assertEquals(text(take, "tab.musicxml"), api.musicXml(job.id))
        }
        val api = FixtureEngineApi(DirectoryFixtureSource(File(fixtures, "guitar-line")), stageSeconds = 0.0)
        fun stages(job: JobCreate) = kotlinx.coroutines.runBlocking { api.createJob(job) }.stages.map { it.name }
        // A job that names nothing is a guitar in a song; a ukulele or a mandolin is taken alone unless the job says it is a song.
        assertEquals(listOf("beats", "stems", "transcribe.guitar.basic-pitch", "transcribe.guitar.swift-f0", "notes", "arrange", "export"), stages(JobCreate.tab("a1")))
        assertEquals(listOf("beats", "transcribe.ukulele.basic-pitch", "transcribe.ukulele.swift-f0", "notes", "arrange", "export"),
            stages(JobCreate.tab("a1", TabOptions(FrettedInstrument.UKULELE_BARITONE))))
        assertTrue("stems" in stages(JobCreate.tab("a1", TabOptions(FrettedInstrument.MANDOLIN, recording = Recording.SONG))))
        assertTrue("transcribe.mandolin.basic-pitch" in stages(JobCreate.tab("a1", TabOptions(FrettedInstrument.MANDOLIN))))
        // A bass under either id is the bass line's stages.
        assertEquals(stages(JobCreate.bassTab("a1", TabOptions(FrettedInstrument.BASS_5))), stages(JobCreate.tab("a1", TabOptions(FrettedInstrument.BASS_5))))
        fun refused(job: JobCreate) = (kotlinx.coroutines.runBlocking { runCatching { api.createJob(job) } }.exceptionOrNull() as? EngineException)?.refusal
        // The older id takes the basses only; a tuning is one of the instrument's; a bass has no chords to complete.
        assertEquals(Refusal.INVALID_OPTIONS, refused(JobCreate.bassTab("a1", TabOptions(FrettedInstrument.GUITAR_6))))
        assertEquals(Refusal.INVALID_OPTIONS, refused(JobCreate.tab("a1", TabOptions(FrettedInstrument.UKULELE, "standard"))))
        assertEquals(Refusal.INVALID_OPTIONS, refused(JobCreate.tab("a1", TabOptions(FrettedInstrument.MANDOLIN, "high-g"))))
        assertEquals(Refusal.INVALID_OPTIONS, refused(JobCreate.tab("a1", TabOptions(FrettedInstrument.BASS_4, chords = TabChords.COMPLETED))))
        assertEquals(Refusal.INVALID_OPTIONS, refused(JobCreate("a1", Profile.BRASS_BAND.id, chords = TabChords.HEARD)))
        assertNull(refused(JobCreate.tab("a1", TabOptions(FrettedInstrument.GUITAR_6, "dadgad", 12, chords = TabChords.COMPLETED))))
    }
}
