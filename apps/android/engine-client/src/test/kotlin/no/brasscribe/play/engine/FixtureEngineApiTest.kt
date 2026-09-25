package no.brasscribe.play.engine

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class FixtureEngineApiTest {
    private val golden = File(System.getProperty("brasscribe.golden") ?: "missing")

    @Test
    fun runsTheLayeredProfileAgainstTheGoldenMikkelOutput() = runTest {
        assumeTrue("golden output not present", File(golden, "composition.json").exists())
        val api = FixtureEngineApi(DirectoryFixtureSource(golden), stageSeconds = 0.0)
        val job = api.createJobFromUpload("mikkel.wav", ByteArray(64) { it.toByte() }, Profile.ORCHESTRA_WITH_SOLOIST, "Mikkel")
        val events = api.events(job.id).toList()
        val tracker = ProgressTracker(FixtureEngineApi.stagesOf(Profile.ORCHESTRA_WITH_SOLOIST).size)
        events.forEach { tracker.onEvent(it) }
        assertEquals(JobStatus.SUCCEEDED, tracker.progress.status)
        assertEquals(JobStatus.SUCCEEDED, api.job(job.id).status)

        val c = api.composition(job.id)
        assertEquals(listOf("solo", "bass", "strings", "brass", "drums"), c.voices.map { it.id })
        assertEquals(5216, c.voices.sumOf { it.notes.size })
        val xml = api.musicXml(job.id)
        assertEquals(18, Regex("<score-part ").findAll(xml).count())
        assertTrue(api.pdf(job.id).take(4).toByteArray().contentEquals("%PDF".toByteArray()))
        assertEquals(4, api.artifacts(job.id).size)
    }

    @Test
    fun cancelStopsTheEventStream() = runTest {
        val api = FixtureEngineApi({ null }, stageSeconds = 0.0)
        val job = api.createJob(JobCreate("a", Profile.SOLO.id))
        api.cancel(job.id)
        val events = api.events(job.id).toList()
        assertEquals("cancelled", events.last().status)
        assertEquals(JobStatus.CANCELLED, api.job(job.id).status)
    }
}
