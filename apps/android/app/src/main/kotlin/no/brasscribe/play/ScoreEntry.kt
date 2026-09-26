package no.brasscribe.play

import no.brasscribe.play.engine.Job
import no.brasscribe.play.engine.JobStatus

/** A row in "Your scores": a score on this phone, or a finished score on the paired computer. */
data class ScoreEntry(
    val id: String,
    val title: String,
    /** Milliseconds since the epoch. */
    val updated: Long,
    val profile: String,
    val saved: SavedScore? = null,
    val jobId: String? = saved?.jobId,
) {
    val onComputer: Boolean get() = saved == null

    companion object {
        /**
         * This phone's scores and the computer's finished runs, newest first. A run already opened
         * here is shown once, and re-runs of one recording collapse to the latest.
         */
        fun merge(local: List<SavedScore>, jobs: List<Job>): List<ScoreEntry> {
            val downloaded = local.mapNotNull { it.jobId }.toSet()
            val seenAudio = HashSet<String>()
            val remote = jobs.sortedByDescending { it.created }
                .filter { it.status == JobStatus.SUCCEEDED && it.outputs.any { o -> o.endsWith(".musicxml") } }
                .filter { j -> j.audioId?.let(seenAudio::add) ?: true }
                .filter { it.id !in downloaded }
                .map { j -> ScoreEntry("job:${j.id}", j.title ?: j.id, (j.created * 1000).toLong(), j.profile, jobId = j.id) }
            return (local.map { ScoreEntry(it.id, it.title, it.updated, it.profile, it) } + remote).sortedByDescending { it.updated }
        }
    }
}
