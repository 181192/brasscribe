package no.brasscribe.play.engine

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/*
 * Wire types of the brasscribe engine companion API (engine/openapi.json, version 0.1.0).
 * EngineContractTest checks these against the vendored spec: every property the spec requires must be
 * declared here under the same name.
 */

@Serializable
data class Health(
    val version: String,
    val device: String,
    @SerialName("auth_required") val authRequired: Boolean,
    val status: String = "ok",
)

@Serializable
data class PairRequest(val code: String, @SerialName("device_name") val deviceName: String? = null)

@Serializable
data class PairResponse(val token: String)

@Serializable
data class ProfileInfo(
    val name: String,
    val pipeline: String,
    val description: String,
    val validated: Boolean,
    val stages: List<String>,
)

@Serializable
data class AudioRef(
    @SerialName("audio_id") val audioId: String,
    val sha256: String,
    val filename: String,
    val bytes: Long,
)

/** Exactly one of [audioId] (an upload), [sourceId] or [path] (a file inside the engine's data directory). */
@Serializable
data class JobCreate(
    @SerialName("audio_id") val audioId: String? = null,
    val profile: String = Profile.ORCHESTRA_WITH_SOLOIST.id,
    @SerialName("render_audio") val renderAudio: Boolean = true,
    @SerialName("allow_heavy") val allowHeavy: Boolean = true,
    val title: String? = null,
    @SerialName("source_id") val sourceId: String? = null,
    val path: String? = null,
    /** "full" (18 parts) or "minimal" (8 parts). */
    val lineup: String = "full",
    /** "faithful", "standard" or "easier". */
    val difficulty: String = "faithful",
    /** Target concert key: a tonic (Bb, F#, Am) or FIFTHS[:MODE]; exclusive with [transpose]. */
    val key: String? = null,
    /** Semitones, -11..11; exclusive with [key]. */
    val transpose: Int? = null,
)

@Serializable
enum class JobStatus {
    @SerialName("queued") QUEUED,
    @SerialName("running") RUNNING,
    @SerialName("succeeded") SUCCEEDED,
    @SerialName("failed") FAILED,
    @SerialName("cancelled") CANCELLED,
    @SerialName("unknown") UNKNOWN;

    val terminal: Boolean get() = this == SUCCEEDED || this == FAILED || this == CANCELLED
}

@Serializable
enum class StageStatus {
    @SerialName("pending") PENDING,
    @SerialName("started") STARTED,
    @SerialName("cached") CACHED,
    @SerialName("imported") IMPORTED,
    @SerialName("ran") RAN,
    @SerialName("failed") FAILED,
    @SerialName("skipped") SKIPPED;

    val done: Boolean get() = this == CACHED || this == IMPORTED || this == RAN || this == SKIPPED
}

@Serializable
data class StageState(
    val name: String,
    val status: StageStatus,
    val kind: String? = null,
    val device: String? = null,
    val seconds: Double? = null,
)

@Serializable
data class Job(
    val id: String,
    val profile: String,
    val status: JobStatus,
    val created: Double,
    val stages: List<StageState>,
    @SerialName("audio_id") val audioId: String? = null,
    val title: String? = null,
    val started: Double? = null,
    val finished: Double? = null,
    val error: String? = null,
    /** Share of stages finished, 0..1. */
    val progress: Double = 0.0,
    /** Names fetchable under /v1/jobs/{id}/artifacts/{name}. */
    val outputs: List<String> = emptyList(),
    /** The job this one re-runs, if any. */
    @SerialName("previous_run_id") val previousRunId: String? = null,
)

@Serializable
data class Artifact(
    val name: String,
    val bytes: Long,
    @SerialName("media_type") val mediaType: String,
    val url: String,
)

/** One Server-Sent Event of /v1/jobs/{id}/events (the `data:` payload). */
@Serializable
data class JobEvent(
    val id: Int,
    val type: String = "log",
    val run: String? = null,
    val time: Double? = null,
    val stage: String? = null,
    val status: String? = null,
    val kind: String? = null,
    val device: String? = null,
    val seconds: Double? = null,
    /** Share of the job's stages done (stage events). */
    val fraction: Double? = null,
    val message: String? = null,
    val error: String? = null,
)

/** The pipeline profiles the engine offers; the "What is this?" answer picks one. */
enum class Profile(val id: String) {
    SOLO("solo"),
    BRASS_BAND("brass-band"),
    ORCHESTRA_WITH_SOLOIST("orchestra-with-soloist"),
    POP_ROCK("pop-rock");

    companion object {
        fun of(id: String): Profile? = entries.firstOrNull { it.id == id }
    }
}
