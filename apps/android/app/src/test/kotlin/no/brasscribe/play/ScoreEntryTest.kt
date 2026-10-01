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

    @Test
    fun anotherAppsScoreIsNotOpenedAndLeavesNoMusicStandBehind() {
        val ours: (String) -> Boolean = { it != "other" }
        val theirs = ScoreEntry("job:x", "Theirs", 0, "other", jobId = "x")
        // Open on the music stand on the other app's row: nothing opens, and the next score opened is not put on the stand.
        assertEquals(ScoreEntry.Opening(here = false, standFor = null), theirs.opening(review = false, stand = true, makes = ours))
        assertEquals(ScoreEntry.Opening(here = false, standFor = null), theirs.opening(review = true, stand = false, makes = ours))
        // This app's own: the stand for that row, and never together with Check the notes.
        val mine = ScoreEntry("job:y", "Mine", 0, "brass-band", jobId = "y")
        assertEquals(ScoreEntry.Opening(here = true, standFor = "job:y"), mine.opening(review = false, stand = true, makes = ours))
        assertEquals(ScoreEntry.Opening(here = true, standFor = null), mine.opening(review = true, stand = true, makes = ours))
        assertEquals(ScoreEntry.Opening(here = true, standFor = null), mine.opening(review = false, stand = false, makes = ours))
        // A copy on this phone opens whatever made it.
        val copy = ScoreEntry("s1", "Copy", 0, "other", saved = SavedScore("s1", "Copy", "other", 0))
        assertEquals(ScoreEntry.Opening(here = true, standFor = "s1"), copy.opening(review = false, stand = true, makes = ours))
    }

    @Test
    fun theOtherAppsRunOfTheSameRecordingIsItsOwnRow() {
        // One recording, sent from both apps: a band score and a bass tab. Neither hides the other, whichever is newer.
        val band = job("band", 1000.0, "audio-1")
        val tab = job("tab", 2000.0, "audio-1", outputs = listOf("tab.musicxml")).copy(profile = "bass-tab")
        assertEquals(listOf("job:tab", "job:band"), ScoreEntry.merge(emptyList(), listOf(band, tab)).map { it.id })
        assertEquals(listOf("job:band", "job:tab"), ScoreEntry.merge(emptyList(), listOf(band.copy(created = 3000.0), tab)).map { it.id })
        // Exactly one of the two is this app's to open.
        assertEquals(1, listOf(band, tab).count { Product.makes(it.profile) })
    }
}
