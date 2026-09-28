package no.brasscribe.play.engine

import kotlinx.coroutines.flow.Flow
import no.brasscribe.play.model.Composition

/** Thrown for any non-success response; [status] is the HTTP status (0 when there was no response). */
class EngineException(val status: Int, message: String) : Exception(message)

/**
 * The engine companion API as Play uses it. [KtorEngineApi] talks to a real engine on the LAN;
 * [FixtureEngineApi] replays a finished engine output folder for tests.
 */
interface EngineApi {
    suspend fun health(): Health
    suspend fun pair(code: String, deviceName: String?, platform: String? = PLATFORM): PairResponse

    /** Checks the stored credential: 401 means pair again; 404 means a trusted client with no device entry. */
    suspend fun thisDevice(): DeviceSelf
    suspend fun rotateToken(): RotateResponse
    suspend fun unpairThisDevice()

    /** Asks to pair without a code; the computer shows "Allow <device>?" with the match code. */
    suspend fun requestPairing(deviceName: String?, platform: String? = PLATFORM): PairRequestInfo
    suspend fun pollPairingRequest(requestId: String): PairRequestResult
    suspend fun profiles(): List<ProfileInfo>

    /** Streams [source] to the engine; [onProgress] reports bytes sent. */
    suspend fun uploadAudio(source: UploadSource, onProgress: UploadProgress = { _, _ -> }): AudioRef
    suspend fun createJob(request: JobCreate): Job
    suspend fun createJobFromUpload(source: UploadSource, profile: Profile, title: String?, renderAudio: Boolean = true,
                                    onProgress: UploadProgress = { _, _ -> }): Job
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

    /** Per uncertain note: its confidence and what each transcriber heard. */
    suspend fun evidence(jobId: String): Evidence

    /** Rename a finished score on the computer. */
    suspend fun renameRun(jobId: String, title: String): Job

    /** Remove a finished score from the computer. */
    suspend fun deleteRun(jobId: String)

    /** Braille music (BRF, North American Braille ASCII, 40 cells x 25 lines, CRLF); [part] = 1-based index or name, null = score. */
    suspend fun braille(jobId: String, part: String? = null): ByteArray

    /** Talking score: [format] html, text or json; [lang] en or nb; [part] = 1-based index or name, null = all parts. */
    suspend fun talkingScore(jobId: String, format: String = "html", lang: String = "en", part: String? = null,
                             pitchMode: String? = null, verbosity: String = "standard"): String

    companion object {
        /** operationIds of engine/openapi.json this client implements; checked by EngineContractTest. */
        val OPERATIONS = setOf(
            "getHealth", "pairDevice", "listProfiles", "uploadAudio", "createJob", "createJobFromUpload", "getJob",
            "listJobs", "cancelJob", "streamJobEvents", "getComposition", "getMusicXml", "getMidi", "getPdf",
            "getRenderedAudio", "listJobArtifacts", "getJobArtifact", "getJobManifest", "getBraille", "getTalkingScore",
            "getJobEvidence", "updateRun", "deleteRun", "getThisDevice", "rotateDeviceToken", "unpairThisDevice",
            "requestPairing", "pollPairingRequest",
        )

        const val PLATFORM = "android"

        /** operationIds deliberately left out: Studio's benchmarks, inspection and dataset tools, and the computer's own. */
        val NOT_USED = setOf(
            "getPartSources",
            "listSuites", "runSuite", "listSuiteHistory", "compareJob", "getJobInput", "getReferenceFile", "getRoundtrip",
            "runRoundtrip", "getStageFile", "getValidation", "listAdapters", "listConformanceReports", "listDatasets",
            "listJobStages", "listParityReports", "listReferences", "listSources", "rerunJob", "getConformanceRun",
            "runConformance",
            // Only the computer itself may call these (Brasscribe Bandroom).
            "listDevices", "revokeDevice", "getPairing", "openPairing", "closePairing", "listPairingRequests",
            "decidePairingRequest", "getStatus",
        )
    }
}
