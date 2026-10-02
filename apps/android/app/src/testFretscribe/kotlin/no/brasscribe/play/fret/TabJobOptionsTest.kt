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
    private class Sent(val body: JsonObject, val instrument: String, val tuning: String, val capo: Int, val layout: String, val recording: String)

    /** The request as the app makes it before the product completes it: the recording, a title, and a band seat left from Brasscribe's choices. */
    private fun request(profile: Profile) = JobCreate("audio-1", profile.id, renderAudio = true, allowHeavy = true, title = "Riff", seat = "2nd-cornet", reads = "treble")

    private fun sent(options: TabOptions): Sent {
        val job = tabJob(request(Profile.TAB), options)
        val kind = options.instrument!!
        return Sent(BrasscribeJson.encodeToJsonElement(JobCreate.serializer(), job).jsonObject, kind.id!!, options.tuning!!, options.capo!!,
            options.layout!!.id!!, (options.recording ?: kind.defaultRecording).id!!)
    }

    /** Your instrument's choices with What is this?'s answers: the first job of a song. */
    private fun firstJobs(): List<Sent> = buildList {
        for (instrument in Instrument.entries) for (kind in instrument.kinds) for (tuning in kind.tunings) for (reads in Reads.entries)
            for (hand in FrettingHand.entries) for (answer in listOf(Recording.INSTRUMENT, Recording.SONG, null)) {
                add(sent(tabOptions(YourInstrument(kind, tuning, hand, reads), SongAnswer(answer))))
            }
    }

    /** Check the song's changes: the song written down again with another capo, the tuning it sounds like, or another octave. */
    private fun changedJobs(): List<Sent> = buildList {
        for (instrument in Instrument.entries) for (kind in instrument.kinds) for (tuning in kind.tunings) for (layout in TabLayout.entries.filter { it.id != null })
            for (recording in listOf(Recording.INSTRUMENT, Recording.SONG)) {
                // What a song's options read back as: the fingering style is the computer's, named.
                val made = TabOptions(kind, tuning, 0, no.brasscribe.play.engine.FingeringStyle.AS_PLAYED, recording, Octave.AUTO, layout)
                fun again(options: TabOptions) = add(sent(tabOptions(YourInstrument(), SongAnswer(options.recording, again = options))))
                for (fret in SongCheck.CAPO_FRETS) again(made.copy(capo = fret))
                for (other in kind.tunings) again(made.copy(tuning = other, capo = 3))
                for (octave in Octave.entries.filter { it.id != null }) again(made.copy(octave = octave))
            }
    }

    @Test
    fun everyChoiceOfYourInstrumentAndWhatIsThisReachesTheJob() {
        val jobs = firstJobs()
        assertEquals((11 + 2 + 1 + 5 + 2 + 1 + 2 + 1 + 1) * 3 * 3 * 3, jobs.size)
        // Every instrument and tuning the computer has is among them, in every layout.
        assertEquals(
            FrettedInstrument.entries.filter { it.id != null }.flatMap { k -> k.tunings.flatMap { t -> listOf("tab", "tab-and-notation", "notation").map { Triple(k.id, t, it) } } }.toSet(),
            jobs.map { Triple(it.instrument, it.tuning, it.layout) }.toSet(),
        )
        for (job in jobs) {
            fun text(name: String) = (job.body[name] as? JsonPrimitive)?.content
            assertEquals("tab", text("profile"))
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
    fun aJobOfEitherIdIsSentAsATabJobAndABandJobIsLeftAlone() {
        val options = tabOptions(YourInstrument(FrettedInstrument.UKULELE, "low-g"), SongAnswer(Recording.INSTRUMENT))
        for (profile in listOf(Profile.TAB, Profile.BASS_TAB)) {
            val job = tabJob(request(profile), options)
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
        val jobs = firstJobs() + changedJobs()
        val file = File.createTempFile("tab-jobs", ".jsonl")
        try {
            file.writeText(jobs.joinToString("\n") { job ->
                buildJsonObject {
                    put("body", job.body)
                    put("expect", buildJsonObject {
                        put("instrument", job.instrument); put("tuning", job.tuning); put("capo", job.capo)
                        put("layout", job.layout); put("recording", job.recording)
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
            assertTrue(output, output.trim().endsWith("${jobs.size} of ${jobs.size} jobs accepted and read as meant"))
        } finally {
            file.delete()
        }
    }
}
