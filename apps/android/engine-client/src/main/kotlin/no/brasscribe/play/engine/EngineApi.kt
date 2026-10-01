package no.brasscribe.play.engine

import kotlinx.coroutines.flow.Flow
import no.brasscribe.play.model.Composition

/**
 * Thrown for any non-success response; [status] is the HTTP status (0 when there was no response).
 * [code]: the engine's code for a refused option (a 422's `code`: quartet_needs_group, seat_no_tune, ...), when it gave one.
 */
class EngineException(val status: Int, message: String, val code: String? = null) : Exception(message) {
    /** Why the engine refused the job, when it said so with a code this client knows. */
    val refusal: Refusal? get() = Refusal.of(code)
}

/** The engine's codes for a job it refuses to start (a 422's `code`); the app has its own words for each. */
enum class Refusal(val code: String) {
    /** A solo take asked for the quartet. */
    QUARTET_NEEDS_GROUP("quartet_needs_group"),
    /** A solo take for the percussion seat. */
    PERCUSSION_SOLO("percussion_solo"),
    /** The seat's part cannot carry the tune in this lineup. */
    SEAT_NO_TUNE("seat_no_tune"),
    /** A clef the seat is not offered in. */
    READS_NOT_OFFERED("reads_not_offered"),
    /** Anything else wrong with the options. */
    INVALID_OPTIONS("invalid_options"),
    /** A tab was asked of a computer whose Brasscribe cannot write tab: the Rust core's command line is not installed with it. */
    CORE_MISSING("core_missing");

    companion object {
        fun of(code: String?): Refusal? = entries.firstOrNull { it.code == code }
    }
}

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
    /** [tab]: the options of a [Profile.BASS_TAB] job; the engine refuses them for any other profile. */
    suspend fun createJobFromUpload(source: UploadSource, profile: Profile, title: String?, renderAudio: Boolean = true,
                                    onProgress: UploadProgress = { _, _ -> }, tab: TabOptions? = null): Job
    suspend fun job(jobId: String): Job
    suspend fun jobs(): List<Job>
    suspend fun cancel(jobId: String): Job

    /** Progress events; resumes after event [after]. Completes when the job reaches a terminal state. */
    fun events(jobId: String, after: Int = -1): Flow<JobEvent>

    suspend fun composition(jobId: String): Composition

    /** The job's score: the band score, or tab.musicxml of a bass-tab job. */
    suspend fun musicXml(jobId: String): String

    /** As [musicXml]; of a bass-tab job, tab.mid, which is there only when the computer has MuseScore (404 otherwise). */
    suspend fun midi(jobId: String): ByteArray

    /** As [musicXml]; of a bass-tab job, tab.pdf, which is there only when the computer has MuseScore (404 otherwise). */
    suspend fun pdf(jobId: String): ByteArray

    /** The tab of a finished bass-tab job: a string and a fret for every note. 404 for another profile, or before it is done. */
    suspend fun tab(jobId: String): Tab
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
            "getJobEvidence", "getTab", "updateRun", "deleteRun", "getThisDevice", "rotateDeviceToken", "unpairThisDevice",
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
