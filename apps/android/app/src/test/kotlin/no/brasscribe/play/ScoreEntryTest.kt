package no.brasscribe.play

import no.brasscribe.play.engine.Job
import no.brasscribe.play.engine.JobStatus
import org.junit.Assert.assertEquals
import org.junit.Test

class ScoreEntryTest {
    private fun job(id: String, created: Double, audio: String, status: JobStatus = JobStatus.SUCCEEDED, outputs: List<String> = listOf("brass-band.musicxml")) =
        Job(id, "brass-band", status, created, emptyList(), audioId = audio, title = "Title $id", outputs = outputs)

    @Test
    fun latestScoresMergeThisPhoneAndTheComputerWithoutDuplicates() {
        val local = listOf(SavedScore("a", "Opened", "solo", 2_500_000, jobId = "j3"))
        val jobs = listOf(
            job("j1", 1000.0, "audio-1"), job("j2", 3000.0, "audio-1"), // re-run: only the latest shows
            job("j3", 2000.0, "audio-2"),                               // already on the phone
            job("j4", 4000.0, "audio-3", JobStatus.FAILED),
            job("j5", 1500.0, "audio-4", outputs = listOf("composition.json")),
        )
        val merged = ScoreEntry.merge(local, jobs)
        assertEquals(listOf("job:j2", "a"), merged.map { it.id })
        assertEquals(listOf(true, false), merged.map { it.onComputer })
        assertEquals("j3", merged[1].jobId)
    }
}
