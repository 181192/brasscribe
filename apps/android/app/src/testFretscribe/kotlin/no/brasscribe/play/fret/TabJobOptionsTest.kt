package no.brasscribe.play.fret

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import no.brasscribe.play.Product
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.Octave
import no.brasscribe.play.engine.OctaveSource
import no.brasscribe.play.engine.Tab
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.engine.Recording
import no.brasscribe.play.engine.TabLayout
import no.brasscribe.play.engine.TabOptions
import no.brasscribe.play.model.BrasscribeJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Every tab job Fretscribe can send, for every instrument, tuning, layout, answer and capo the screens can
 * produce: what it carries, and that the computer's own option check takes it and reads it as it was meant.
 */
class TabJobOptionsTest {
    /** One job: the body as it goes to the computer, and what it is meant to be once the computer has filled in its defaults. */
    private class Sent(val body: JsonObject, val instrument: String, val tuning: String, val capo: Int, val layout: String, val recording: String, val octave: String)

    /** The request as the app makes it before the product completes it: the recording, a title, and a band seat left from Brasscribe's choices. */
    private fun request(profile: Profile) = JobCreate("audio-1", profile.id, renderAudio = true, allowHeavy = true, title = "Riff", seat = "2nd-cornet", reads = "treble")

    /** A computer with every profile, and one from before the tab profile: it has the bass tab's id only. */
    private val current = Profile.entries.map { it.id }.toSet()
    private val older = current - Profile.TAB.id

    private fun sent(options: TabOptions, listed: Set<String>? = current): Sent {
        val job = tabJob(request(Profile.TAB), options, listed)
        val kind = options.instrument!!
        return Sent(BrasscribeJson.encodeToJsonElement(JobCreate.serializer(), job).jsonObject, kind.id!!, options.tuning!!, options.capo!!,
            options.layout!!.id!!, (options.recording ?: kind.defaultRecording).id!!, options.octave!!.id!!)
    }

    /** The computers a job for [kind] is sent to: one with the tab profile, and for a bass also one from before it. */
    private fun computers(kind: FrettedInstrument): List<Set<String>> = if (kind.isBass) listOf(current, older) else listOf(current)

    /**
     * Your instrument's choices with What is this?'s answers: the first job of a song. (The hand on the neck is
     * not among them: it never reaches the job, which YourInstrumentTest checks.)
     */
    private fun firstJobs(): List<Sent> = buildList {
        for (instrument in Instrument.entries) for (kind in instrument.kinds) for (tuning in kind.tunings) for (reads in Reads.entries)
            for (answer in listOf(Recording.INSTRUMENT, Recording.SONG, null)) for (listed in computers(kind)) {
                add(sent(tabOptions(YourInstrument(kind, tuning, reads = reads), SongAnswer(answer)), listed))
            }
        // (No answer is sent as the computer's own default for the instrument: the same job as that answer.)
    }.distinctBy { it.body.toString() }

    /** The recorded guitar tab: what Check the song reads a song's options back from. */
    private fun recorded(): Tab? = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("apps/fixtures/guitar-line/tab.json")
        ?.takeIf { it.isFile }?.let { BrasscribeJson.decodeFromString(Tab.serializer(), it.readText()) }

    /**
     * Check the song's changes, as the screen makes them: the options are read back from the tab and its job's
     * stages (SongCheck.optionsOf), for a tab of every instrument, tuning, layout and answer, with the octave
     * as Fretscribe chose it or as the player did; then one thing is changed: the capo, the tuning, or the octave.
     */
    private fun changedJobs(tab: Tab): List<Sent> = buildList {
        val octaves = listOf(OctaveSource.AUTO to 0, OctaveSource.AUTO to -12, OctaveSource.CHOSEN to -12, OctaveSource.CHOSEN to 12, OctaveSource.CHOSEN to 0)
        for (instrument in Instrument.entries) for (kind in instrument.kinds) for (tuning in kind.tunings) for (layout in TabLayout.entries.filter { it.id != null })
            for (song in listOf(false, true)) for ((source, shift) in octaves) for (listed in computers(kind)) {
                val written = tab.copy(preset = kind.preset(tuning), layout = layout, octaveSource = source, octaveShift = shift)
                val stages = listOf("beats") + (if (song) listOf("stems") else emptyList()) + listOf("transcribe.x.basic-pitch", "transcribe.x.swift-f0", "notes", "arrange", "export")
                val made = SongCheck.optionsOf(written, stages)
                assertEquals(kind to tuning, made.instrument to made.tuning)
                assertEquals(if (song) Recording.SONG else Recording.INSTRUMENT, made.recording)
                fun again(options: TabOptions) = add(sent(tabOptions(YourInstrument(), SongAnswer(options.recording, again = options)), listed))
                for (fret in SongCheck.CAPO_FRETS) again(made.copy(capo = fret))
                for (other in kind.tunings) again(made.copy(tuning = other))
                // The octave row's two buttons.
                again(made.copy(octave = Octave.AUTO))
                again(made.copy(octave = Octave.AS_HEARD))
            }
    }.distinctBy { it.body.toString() }

    @Test
    fun everyChoiceOfYourInstrumentAndWhatIsThisReachesTheJob() {
        val jobs = firstJobs()
        // Every instrument and tuning, read three ways, with either answer; a bass also for the older computer.
        assertEquals((11 + 2 + 1 + 5 + 2 + 1 + 2 + 1 + 1) * 3 * 2 + (5 + 2 + 1) * 3 * 2, jobs.size)
        // Every instrument and tuning the computer has is among them, in every layout.
        assertEquals(
            FrettedInstrument.entries.filter { it.id != null }.flatMap { k -> k.tunings.flatMap { t -> listOf("tab", "tab-and-notation", "notation").map { Triple(k.id, t, it) } } }.toSet(),
            jobs.map { Triple(it.instrument, it.tuning, it.layout) }.toSet(),
        )
        for (job in jobs) {
            fun text(name: String) = (job.body[name] as? JsonPrimitive)?.content
            // Every instrument goes as a tab job; a bass goes under the older id too, for the computer that has only that.
            assertTrue(text("profile"), text("profile") == "tab" || (text("profile") == "bass-tab" && job.instrument.startsWith("bass-")))
            assertEquals(job.instrument, text("instrument"))
            assertEquals(job.tuning, text("tuning"))
            assertEquals(job.layout, text("layout"))
            assertEquals(job.recording, text("recording"))
            // A first job has no capo and lets the computer check the octave.
            assertEquals("0", text("capo"))
            assertEquals("auto", text("octave"))
            // The fingering style and the chords are the computer's defaults: not named. The band's choices never go.
            for (unsent in listOf("style", "chords", "seat", "reads", "lead", "key", "transpose")) assertFalse("$unsent in ${job.body}", unsent in job.body)
        }
    }

    @Test
    fun anUnansweredJobIsTakenAsTheComputerTakesIt() {
        for (instrument in Instrument.entries) for (kind in instrument.kinds) {
            val alone = instrument == Instrument.UKULELE || instrument == Instrument.MANDOLIN
            assertEquals(kind.name, if (alone) Recording.INSTRUMENT else Recording.SONG, tabOptions(YourInstrument(kind), SongAnswer()).recording)
            // What is this? starts on "Just my instrument" for a ukulele and a mandolin, and with nothing chosen for a guitar and a bass.
            assertEquals(kind.name, if (alone) Recording.INSTRUMENT else null, startingAnswer(YourInstrument(kind)))
            // The player's answer always wins.
            assertEquals(Recording.SONG, tabOptions(YourInstrument(kind), SongAnswer(Recording.SONG)).recording)
            assertEquals(Recording.INSTRUMENT, tabOptions(YourInstrument(kind), SongAnswer(Recording.INSTRUMENT)).recording)
        }
        assertNull(startingAnswer(YourInstrument.DEFAULT))
    }

    @Test
    fun theProfileIdIsTheOneTheComputerHasForTheInstrument() {
        val all = Instrument.entries.flatMap { it.kinds }
        for (kind in all) {
            // A computer with the tab profile: every instrument goes under it, a bass too.
            assertEquals(kind.name, Profile.TAB, tabProfile(kind, current))
            assertEquals(kind.name, Profile.TAB, tabProfile(kind, setOf("tab")))
            // A computer from before it: a bass still goes, under the id it knows; nothing else can be written there.
            assertEquals(kind.name, if (kind.isBass) Profile.BASS_TAB else null, tabProfile(kind, older))
            // A computer that writes no tab at all.
            assertNull(kind.name, tabProfile(kind, setOf("solo", "brass-band")))
            assertNull(kind.name, tabProfile(kind, emptySet()))
            // Not known (the computer could not be asked): the id every computer that writes the instrument has.
            assertEquals(kind.name, if (kind.isBass) Profile.BASS_TAB else Profile.TAB, tabProfile(kind, null))
        }
        assertEquals(Profile.TAB, tabProfile(null, null))
        assertNull(tabProfile(null, older))
        // The job carries that id, whatever the request said, also for a song written down again.
        val bass = tabOptions(YourInstrument(FrettedInstrument.BASS_5, "drop-a"), SongAnswer(Recording.SONG))
        assertEquals("bass-tab", tabJob(request(Profile.TAB), bass, older).profile)
        assertEquals("bass-tab", tabJob(request(Profile.TAB), bass, null).profile)
        assertEquals("tab", tabJob(request(Profile.BASS_TAB), bass, current).profile)
        val again = SongAnswer(Recording.INSTRUMENT, again = bass.copy(tuning = "standard", capo = 2))
        assertEquals("bass-tab", tabJob(request(Profile.TAB), tabOptions(YourInstrument(), again), older).profile)
        val guitar = tabOptions(YourInstrument(), SongAnswer(Recording.SONG))
        assertEquals("tab", tabJob(request(Profile.TAB), guitar, current).profile)
        assertEquals("tab", tabJob(request(Profile.TAB), guitar, null).profile)
        // The words for a computer that is too old name the instrument; a bass that can't be written gets the tab words.
        assertEquals(no.brasscribe.play.R.string.fs_too_old_guitar, tooOldWords(FrettedInstrument.GUITAR_7))
        assertEquals(no.brasscribe.play.R.string.fs_too_old_ukulele, tooOldWords(FrettedInstrument.UKULELE_BARITONE))
        assertEquals(no.brasscribe.play.R.string.fs_too_old_mandolin, tooOldWords(FrettedInstrument.MANDOLIN))
        assertEquals(no.brasscribe.play.R.string.error_core_missing, tooOldWords(FrettedInstrument.BASS_4))
    }

    @Test
    fun whatAComputerSaidIsKeptForThatComputerOnlyAndIsGoneWhileItIsAskedAgain() {
        ComputerProfiles.clear()
        assertNull(ComputerProfiles.listed)
        ComputerProfiles.asking("mac-1")
        assertEquals(ComputerProfiles.Answer("mac-1", asking = true, listed = null), ComputerProfiles.answer)
        ComputerProfiles.answered("mac-1", current)
        assertEquals(current, ComputerProfiles.listed)
        // Another computer is asked: what the first said does not count for it, also before it answers.
        ComputerProfiles.asking("mac-2")
        assertNull(ComputerProfiles.listed)
        // The first one's late answer is not taken for the second's.
        ComputerProfiles.answered("mac-1", current)
        assertNull(ComputerProfiles.listed)
        assertTrue(ComputerProfiles.answer!!.asking)
        ComputerProfiles.answered("mac-2", older)
        assertEquals(older, ComputerProfiles.listed)
        // Asked again, its own earlier answer is gone until the new one is there; a request that fails leaves nothing known.
        ComputerProfiles.asking("mac-2")
        assertNull(ComputerProfiles.listed)
        ComputerProfiles.answered("mac-2", null)
        assertEquals(ComputerProfiles.Answer("mac-2", asking = false, listed = null), ComputerProfiles.answer)
        ComputerProfiles.clear()
        assertNull(ComputerProfiles.answer)
    }

    @Test
    fun aJobOfEitherIdIsSentAsATabJobAndABandJobIsLeftAlone() {
        val options = tabOptions(YourInstrument(FrettedInstrument.UKULELE, "low-g"), SongAnswer(Recording.INSTRUMENT))
        for (profile in listOf(Profile.TAB, Profile.BASS_TAB)) {
            val job = tabJob(request(profile), options, current)
            assertEquals("tab", job.profile)
            assertEquals(listOf(null, null, null), listOf(job.seat, job.reads, job.lead))
            assertEquals(FrettedInstrument.UKULELE to "low-g", job.instrument to job.tuning)
            assertNull(job.chords)
        }
        assertTrue(Product.makes("tab") && Product.makes("bass-tab"))
    }

    /** The computer's check of the options (the engine's profiles.job_options), on every job above. */
    @Test
    fun theComputersOwnOptionCheckTakesEveryJobAndReadsItAsMeant() {
        // The repository root is two up from the sounds folder the build passes in.
        val root = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }
        val script = root?.resolve("apps/android/scripts/check-tab-options.py")
        assumeTrue("the engine is not in this checkout", script?.isFile == true && root.resolve("engine/src/brasscribe_engine/tab.py").isFile)
        val tab = recorded()
        assumeTrue("apps/fixtures/guitar-line is not in this checkout", tab != null)
        val jobs = firstJobs() + changedJobs(tab!!)
        val file = File.createTempFile("tab-jobs", ".jsonl")
        try {
            file.writeText(jobs.joinToString("\n") { job ->
                buildJsonObject {
                    put("body", job.body)
                    put("expect", buildJsonObject {
                        put("instrument", job.instrument); put("tuning", job.tuning); put("capo", job.capo)
                        put("layout", job.layout); put("recording", job.recording); put("octave", job.octave)
                    })
                }.toString()
            })
            val process = try {
                ProcessBuilder("pixi", "run", "python", script!!.path, file.path).directory(root).redirectErrorStream(true).start()
            } catch (e: java.io.IOException) {
                assumeTrue("pixi is not installed, so the engine's option check cannot run: ${e.message}", false)
                return
            }
            val output = process.inputStream.bufferedReader().readText()
            assertTrue("the engine's option check did not finish in five minutes", process.waitFor(5, TimeUnit.MINUTES))
            assumeTrue("the engine cannot check tab options here (scripts/worktree-setup.sh builds the core's command line): $output", process.exitValue() != 3)
            assertEquals(output, 0, process.exitValue())
            println(output.trim().lines().last())
            assertTrue(output, output.trim().endsWith("${jobs.size} of ${jobs.size} jobs accepted and read as meant"))
        } finally {
            file.delete()
        }
    }
}
