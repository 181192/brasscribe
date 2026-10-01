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

    /**
     * What opening this row does. A score in the computer's list that the other app made ([makes] says no to
     * its profile) is not opened [Opening.here], and nothing is set up for it; [Opening.standFor] is the row
     * whose score goes straight onto the music stand.
     */
    fun opening(review: Boolean, stand: Boolean, makes: (String) -> Boolean): Opening =
        if (saved == null && !makes(profile)) Opening(here = false, standFor = null)
        else Opening(here = true, standFor = id.takeIf { stand && !review })

    data class Opening(val here: Boolean, val standFor: String?)

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
                // (The other app's runs of the same recording are another score: they never hide this app's.)
                .filter { j -> j.audioId?.let { seenAudio.add("${Product.makes(j.profile)}:$it") } ?: true }
                .filter { it.id !in downloaded }
                .map { j -> ScoreEntry("job:${j.id}", j.title ?: j.id, (j.created * 1000).toLong(), j.profile, jobId = j.id) }
            return (local.map { ScoreEntry(it.id, it.title, it.updated, it.profile, it) } + remote).sortedByDescending { it.updated }
        }
    }
}
