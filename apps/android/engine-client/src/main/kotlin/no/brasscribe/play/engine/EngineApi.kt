package no.brasscribe.play.engine

import kotlinx.coroutines.flow.Flow
import no.brasscribe.play.model.Composition

/** Thrown for any non-success response; [status] is the HTTP status (0 when there was no response). */
class EngineException(val status: Int, message: String) : Exception(message)

/**
 * The engine companion API as Play uses it. [KtorEngineApi] talks to a real engine on the LAN;
 * [FixtureEngineApi] replays the golden Mikkel output for development and tests.
 */
interface EngineApi {
    suspend fun health(): Health
    suspend fun pair(code: String, deviceName: String?): PairResponse
    suspend fun profiles(): List<ProfileInfo>

    suspend fun uploadAudio(filename: String, bytes: ByteArray): AudioRef
    suspend fun createJob(request: JobCreate): Job
    suspend fun createJobFromUpload(filename: String, bytes: ByteArray, profile: Profile, title: String?, renderAudio: Boolean = true): Job
    suspend fun job(jobId: String): Job
    suspend fun jobs(): List<Job>
    suspend fun cancel(jobId: String): Job

    /** Progress events; resumes after event [after]. Completes when the job reaches a terminal state. */
    fun events(jobId: String, after: Int = -1): Flow<JobEvent>

    suspend fun composition(jobId: String): Composition
    suspend fun musicXml(jobId: String): String
    suspend fun midi(jobId: String): ByteArray
    suspend fun pdf(jobId: String): ByteArray
    suspend fun renderedAudio(jobId: String): ByteArray
    suspend fun artifacts(jobId: String): List<Artifact>
    suspend fun artifact(jobId: String, name: String): ByteArray
    suspend fun manifest(jobId: String): String

    companion object {
        /** operationIds of engine/openapi.json this client implements; checked by EngineContractTest. */
        val OPERATIONS = setOf(
            "getHealth", "pairDevice", "listProfiles", "uploadAudio", "createJob", "createJobFromUpload", "getJob",
            "listJobs", "cancelJob", "streamJobEvents", "getComposition", "getMusicXml", "getMidi", "getPdf",
            "getRenderedAudio", "listJobArtifacts", "getJobArtifact", "getJobManifest",
        )

        /** operationIds deliberately left out: Studio's benchmarks, inspection and dataset tools. */
        val NOT_USED = setOf(
            "listSuites", "runSuite", "listSuiteHistory", "compareJob", "getJobInput", "getReferenceFile", "getRoundtrip",
            "runRoundtrip", "getStageFile", "getValidation", "listAdapters", "listConformanceReports", "listDatasets",
            "listJobStages", "listParityReports", "listReferences", "listSources", "rerunJob",
        )
    }
}
