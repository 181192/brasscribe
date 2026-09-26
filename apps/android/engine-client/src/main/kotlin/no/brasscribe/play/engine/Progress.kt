package no.brasscribe.play.engine

/** What a transcription is doing right now, in terms the UI can put into plain words. */
data class Progress(
    val status: JobStatus = JobStatus.QUEUED,
    /** 0..1 share of stages done. */
    val fraction: Double = 0.0,
    /** Stage kind being worked on: beats, stems, layers, transcribe, arrange, export. */
    val currentKind: String? = null,
    val currentStage: String? = null,
    val stagesDone: Int = 0,
    val stagesTotal: Int = 0,
    /** Estimated seconds left, null until there is something to estimate from. */
    val etaSeconds: Int? = null,
    val device: String? = null,
    val error: String? = null,
    val lastEventId: Int = -1,
)

/**
 * Folds job events into [Progress]. The time estimate uses the observed pace once a stage has finished,
 * and typical stage durations per kind before that.
 */
class ProgressTracker(private val stagesTotal: Int, private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 }) {
    private var startedAt: Double? = null
    var progress = Progress(stagesTotal = stagesTotal)
        private set

    fun onEvent(e: JobEvent): Progress {
        val now = e.time ?: clock()
        if (startedAt == null) startedAt = now
        var p = progress.copy(lastEventId = e.id)
        when (e.type) {
            "job" -> {
                val status = runCatching { JobStatus.valueOf(e.status.orEmpty().uppercase()) }.getOrDefault(p.status)
                p = p.copy(status = status, error = e.error ?: p.error)
                if (status == JobStatus.SUCCEEDED) p = p.copy(fraction = 1.0, etaSeconds = 0, stagesDone = stagesTotal)
            }
            "stage" -> {
                p = p.copy(status = JobStatus.RUNNING, currentStage = e.stage, currentKind = e.kind ?: p.currentKind,
                    device = e.device ?: p.device)
                if (e.status == "failed") p = p.copy(error = e.error ?: e.message)
                if (e.fraction != null) p = p.copy(fraction = e.fraction, stagesDone = (e.fraction * stagesTotal + 0.5).toInt())
            }
        }
        progress = p.copy(etaSeconds = if (p.status.terminal) 0 else eta(p, now))
        return progress
    }

    private fun eta(p: Progress, now: Double): Int? {
        val start = startedAt ?: return null
        val elapsed = now - start
        if (p.fraction >= 0.05 && elapsed > 1.0) return ((elapsed / p.fraction) * (1 - p.fraction)).toInt()
        val remaining = stagesTotal - p.stagesDone
        return if (remaining <= 0) null else (remaining * TYPICAL_STAGE_S).toInt()
    }

    private companion object {
        const val TYPICAL_STAGE_S = 40.0
    }
}
