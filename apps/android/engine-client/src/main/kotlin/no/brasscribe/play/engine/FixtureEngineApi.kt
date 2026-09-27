package no.brasscribe.play.engine

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.CompositionJson
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/** Where fixture files come from: a directory on the JVM, app assets on Android. */
fun interface FixtureSource {
    fun read(name: String): ByteArray?
}

class DirectoryFixtureSource(private val dir: File) : FixtureSource {
    override fun read(name: String): ByteArray? = File(dir, name).takeIf { it.isFile }?.readBytes()
}

/**
 * Plays the part of the engine using the golden Mikkel output (data/golden/mikkel-arranged-band):
 * every job walks the stages of its profile with timed progress events and then serves the golden
 * Composition, MusicXML, PDF and MP3. Used when no companion engine is paired, and in tests.
 */
class FixtureEngineApi(
    private val source: FixtureSource,
    /** Seconds each simulated stage takes. */
    private val stageSeconds: Double = 0.6,
) : EngineApi {
    private val uploads = ConcurrentHashMap<String, AudioRef>()
    private val jobs = ConcurrentHashMap<String, Job>()
    private val cancelled = ConcurrentHashMap.newKeySet<String>()
    private val counter = AtomicInteger()

    override suspend fun health() = Health(version = "fixture", device = "cpu", authRequired = false, serverId = "fixture", serverName = "Brasscribe on fixture")
    override suspend fun pair(code: String, deviceName: String?) = PairResponse("fixture-token", deviceId = "fixture", serverId = "fixture", serverName = "Brasscribe on fixture")

    override suspend fun profiles(): List<ProfileInfo> = Profile.entries.map {
        ProfileInfo(it.id, it.id, "Golden Mikkel output", it == Profile.ORCHESTRA_WITH_SOLOIST, stagesOf(it))
    }

    override suspend fun uploadAudio(filename: String, bytes: ByteArray): AudioRef {
        val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        return AudioRef(sha.take(16), sha, filename, bytes.size.toLong()).also { uploads[it.audioId] = it }
    }

    override suspend fun createJob(request: JobCreate): Job {
        val profile = Profile.of(request.profile) ?: throw EngineException(422, "unknown profile ${request.profile}")
        val id = "fixture-${counter.incrementAndGet()}"
        val job = Job(id, profile.id, JobStatus.QUEUED, now(), stagesOf(profile).map { StageState(it, StageStatus.PENDING, kindOf(it)) },
            audioId = request.audioId, title = request.title)
        jobs[id] = job
        return job
    }

    override suspend fun createJobFromUpload(filename: String, bytes: ByteArray, profile: Profile, title: String?, renderAudio: Boolean): Job =
        createJob(JobCreate(uploadAudio(filename, bytes).audioId, profile.id, renderAudio, title = title))

    override suspend fun job(jobId: String): Job = jobs[jobId] ?: throw EngineException(404, "no job $jobId")
    override suspend fun jobs(): List<Job> = jobs.values.sortedBy { it.created }

    override suspend fun cancel(jobId: String): Job {
        cancelled += jobId
        val j = job(jobId).copy(status = JobStatus.CANCELLED, finished = now())
        jobs[jobId] = j
        return j
    }

    override fun events(jobId: String, after: Int): Flow<JobEvent> = flow {
        val job = job(jobId)
        val stages = stagesOf(Profile.of(job.profile) ?: Profile.ORCHESTRA_WITH_SOLOIST)
        var id = 0
        suspend fun send(e: JobEvent) {
            if (e.id > after) emit(e)
        }
        send(JobEvent(id++, "job", run = jobId, time = now(), status = "queued"))
        jobs[jobId] = job.copy(status = JobStatus.RUNNING, started = now())
        send(JobEvent(id++, "job", run = jobId, time = now(), status = "running"))
        for ((i, stage) in stages.withIndex()) {
            if (jobId in cancelled) {
                jobs[jobId] = job(jobId).copy(status = JobStatus.CANCELLED, finished = now())
                send(JobEvent(id++, "job", run = jobId, time = now(), status = "cancelled")); return@flow
            }
            send(JobEvent(id++, "stage", run = jobId, time = now(), stage = stage, kind = kindOf(stage), status = "started"))
            delay((stageSeconds * 1000).toLong())
            if (jobId in cancelled) {
                jobs[jobId] = job(jobId).copy(status = JobStatus.CANCELLED, finished = now())
                send(JobEvent(id++, "job", run = jobId, time = now(), status = "cancelled")); return@flow
            }
            val fraction = (i + 1).toDouble() / stages.size
            send(JobEvent(id++, "stage", run = jobId, time = now(), stage = stage, kind = kindOf(stage), status = "cached",
                seconds = stageSeconds, fraction = fraction, device = "cpu"))
            jobs[jobId] = job(jobId).copy(progress = fraction)
        }
        jobs[jobId] = job(jobId).copy(status = JobStatus.SUCCEEDED, finished = now(), progress = 1.0, outputs = outputs)
        send(JobEvent(id, "job", run = jobId, time = now(), status = "succeeded"))
    }

    override suspend fun composition(jobId: String): Composition = CompositionJson.decode(String(file("composition.json")))
    override suspend fun musicXml(jobId: String): String = String(file("brass-band.musicxml"))
    override suspend fun midi(jobId: String): ByteArray = file("brass-band.mid")
    override suspend fun pdf(jobId: String): ByteArray = file("brass-band.pdf")
    override suspend fun renderedAudio(jobId: String): ByteArray = file("brass-band.mp3")

    override suspend fun artifacts(jobId: String): List<Artifact> = outputs.mapNotNull { name ->
        source.read(name)?.let { Artifact(name, it.size.toLong(), mediaOf(name), "/v1/jobs/$jobId/artifacts/$name") }
    }

    /** The score's files plus the golden per-part files that are packaged (parts/NN-Name.pdf|brf|musicxml). */
    private val outputs: List<String> by lazy {
        OUTPUTS + PART_NAMES.flatMapIndexed { i, n ->
            listOf("pdf", "brf", "musicxml").map { "parts/%02d-%s.%s".format(i + 1, n, it) }
        }.filter { source.read(it) != null }
    }

    override suspend fun artifact(jobId: String, name: String): ByteArray = file(name)
    override suspend fun braille(jobId: String, part: String?): ByteArray =
        file(if (part == null) "brass-band.brf" else part.toIntOrNull()?.let { n -> PART_NAMES.getOrNull(n - 1)?.let { "parts/%02d-%s.brf".format(n, it) } }
            ?: throw EngineException(404, "no part $part"))

    override suspend fun talkingScore(jobId: String, format: String, lang: String, part: String?, pitchMode: String?, verbosity: String): String =
        throw EngineException(404, "the fixture has no talking score; the app builds it with the core")

    override suspend fun manifest(jobId: String): String = """{"run":"$jobId","fixture":"data/golden/mikkel-arranged-band"}"""

    override suspend fun evidence(jobId: String): Evidence = Evidence.EMPTY

    override suspend fun renameRun(jobId: String, title: String): Job =
        job(jobId).copy(title = title).also { jobs[jobId] = it }

    override suspend fun deleteRun(jobId: String) {
        jobs.remove(jobId) ?: throw EngineException(404, "no run $jobId")
    }

    private fun file(name: String): ByteArray = source.read(name) ?: throw EngineException(404, "fixture file $name is missing")
    private fun now() = System.currentTimeMillis() / 1000.0

    companion object {
        val OUTPUTS = listOf("composition.json", "brass-band.musicxml", "brass-band.pdf", "brass-band.mp3", "brass-band.brf")
        /** The golden score's parts in order, as their file names spell them. */
        val PART_NAMES = listOf(
            "Soprano-Cornet", "Solo-Cornet", "Repiano-Cornet", "2nd-Cornet", "3rd-Cornet", "Flugelhorn", "Solo-Horn", "1st-Horn", "2nd-Horn",
            "1st-Baritone", "2nd-Baritone", "1st-Trombone", "2nd-Trombone", "Bass-Trombone", "Euphonium", "Eb-Bass", "Bb-Bass", "Percussion",
        )

        fun mediaOf(name: String): String = MEDIA[name] ?: when (name.substringAfterLast('.')) {
            "pdf" -> "application/pdf"; "brf" -> "text/plain"; "musicxml" -> "application/vnd.recordare.musicxml+xml"
            else -> "application/octet-stream"
        }

        private val MEDIA = mapOf(
            "composition.json" to "application/json", "brass-band.musicxml" to "application/vnd.recordare.musicxml+xml",
            "brass-band.pdf" to "application/pdf", "brass-band.mp3" to "audio/mpeg", "brass-band.brf" to "text/plain",
        )

        /** Stage names per profile, as the engine's profiles define them. */
        fun stagesOf(profile: Profile): List<String> = when (profile) {
            Profile.SOLO -> listOf("beats", "transcribe.mix.swift-f0", "transcribe.mix.muscriptor", "transcribe.mix.basic-pitch", "arrange", "export")
            Profile.BRASS_BAND -> listOf("beats", "transcribe.mix.muscriptor", "transcribe.mix.basic-pitch", "arrange", "export")
            Profile.POP_ROCK -> listOf("beats", "stems") + listOf("vocals", "other", "guitar", "piano").map { "transcribe.$it.muscriptor" } +
                listOf("transcribe.vocals.basic-pitch", "transcribe.bass.basic-pitch", "arrange", "export")
            Profile.ORCHESTRA_WITH_SOLOIST -> listOf("beats", "stems", "layers", "transcribe.solo.swift-f0", "transcribe.solo.muscriptor",
                "transcribe.bass.muscriptor", "transcribe.drums.muscriptor", "transcribe.orchestra.muscriptor", "contour.solo.swift-f0", "arrange", "export")
        }

        fun kindOf(stage: String): String = when {
            stage.startsWith("contour.") -> "transcribe"
            else -> stage.substringBefore('.')
        }
    }
}
