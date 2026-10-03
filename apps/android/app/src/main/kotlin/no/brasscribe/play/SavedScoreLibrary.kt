package no.brasscribe.play

import java.io.File
import java.util.Properties
import java.util.UUID

/** A score in "Your scores": its details only. The score itself is read when it is opened ([SavedScoreLibrary.content]). */
data class SavedScore(
    val id: String,
    val title: String,
    val profile: String,
    val updated: Long,
    /** The computer's run this score came from, if any. */
    val jobId: String? = null,
    /** Review events the musician kept, as "voice:index". */
    val checked: Set<String> = emptySet(),
    /** "Make this my part": the part picked for this score (its English name), or null for the seat's. */
    val part: String? = null,
    /** The one-line "this lineup has no part of your seat" notice was closed for this score. */
    val noticeSeen: Boolean = false,
    /** A note was changed on the phone: the computer's renders (audio, PDF, braille) are older than the score. */
    val changedOnPhone: Boolean = false,
    /**
     * Notes changed in Review, by their Composition note ("voice@start"): the pitch Brasscribe wrote. Kept so
     * "Changed to … (was …)" is still on the card after reopening or arranging the score again.
     */
    val reviewChanges: Map<String, Int> = emptyMap(),
    /** A quick draft made on the phone (a band recording without the computer): the computer can make the full score. */
    val draft: Boolean = false,
    /** The recording kept beside a draft (its file name in the score's folder), for "Make the full score". */
    val recording: String? = null,
)

/** What a saved score holds beside its details: the MusicXML and, for a transcription, what it came from. */
data class SavedScoreContent(val musicXml: String, val compositionJson: String?, val evidenceJson: String?)

/**
 * App-owned score copies: MusicXML is the editable score, with its transcription beside it. [list] reads
 * only the details (the library is listed after every save); [content] reads one score when it is opened.
 */
class SavedScoreLibrary(private val root: File) {
    fun list(): List<SavedScore> = root.listFiles()?.mapNotNull(::read)
        ?.sortedByDescending { it.updated }.orEmpty()

    fun get(id: String): SavedScore? = folder(id)?.let(::read)

    /** Whether the score [id] is still kept, readable or not: what is kept beside it stays while it is. */
    fun has(id: String): Boolean = folder(id) != null

    /** The score and its transcription, or null when it is gone or unreadable. */
    fun content(id: String): SavedScoreContent? = folder(id)?.let { folder ->
        runCatching {
            SavedScoreContent(
                musicXml = File(folder, "score.musicxml").readText(),
                compositionJson = File(folder, "composition.json").takeIf(File::isFile)?.readText(),
                evidenceJson = File(folder, "evidence.json").takeIf(File::isFile)?.readText(),
            )
        }.getOrNull()
    }

    fun save(
        id: String?, title: String, profile: String, musicXml: String, compositionJson: String?,
        jobId: String? = null, evidenceJson: String? = null, checked: Set<String> = emptySet(), part: String? = null, noticeSeen: Boolean = false,
        changedOnPhone: Boolean = false, reviewChanges: Map<String, Int> = emptyMap(),
        draft: Boolean = false, recording: File? = null,
    ): SavedScore {
        val key = id ?: UUID.randomUUID().toString()
        val folder = File(root, key).apply { mkdirs() }
        writeAtomic(File(folder, "score.musicxml"), musicXml)
        val composition = File(folder, "composition.json")
        if (compositionJson == null) composition.delete() else writeAtomic(composition, compositionJson)
        val evidence = File(folder, "evidence.json")
        if (evidenceJson == null) evidence.delete() else writeAtomic(evidence, evidenceJson)
        // A draft keeps its recording, copied once: a later save (a rename, a checked note) has none to give.
        if (recording != null && recording.isFile && recordingIn(folder) == null) {
            val ext = recording.extension.lowercase().ifBlank { "wav" }
            recording.copyTo(File(folder, "$RECORDING.$ext.tmp"), overwrite = true).renameTo(File(folder, "$RECORDING.$ext"))
        }
        val updated = System.currentTimeMillis()
        val metadata = Properties().apply {
            setProperty("title", title)
            setProperty("profile", profile)
            setProperty("updated", updated.toString())
            jobId?.let { setProperty("job", it) }
            if (checked.isNotEmpty()) setProperty("checked", checked.sorted().joinToString(","))
            part?.let { setProperty("part", it) }
            if (noticeSeen) setProperty("notice_seen", "true")
            if (changedOnPhone) setProperty("changed_on_phone", "true")
            if (draft) setProperty("draft", "true")
            if (reviewChanges.isNotEmpty()) setProperty("review_changes", reviewChanges.toSortedMap().entries.joinToString(",") { "${it.key}=${it.value}" })
        }
        val temporary = File(folder, "score.properties.tmp")
        temporary.outputStream().use { metadata.store(it, null) }
        check(temporary.renameTo(File(folder, "score.properties"))) { "couldn't save score details" }
        return SavedScore(key, title, profile, updated, jobId, checked, part, noticeSeen, changedOnPhone, reviewChanges, draft, recordingIn(folder)?.name)
    }

    fun rename(id: String, title: String): SavedScore? {
        val current = get(id) ?: return null
        val content = content(id) ?: return null
        return save(id, title, current.profile, content.musicXml, content.compositionJson, current.jobId, content.evidenceJson, current.checked, current.part, current.noticeSeen, current.changedOnPhone, current.reviewChanges, current.draft)
    }

    /** The recording kept beside a draft, or null. */
    fun recordingFile(id: String): File? = folder(id)?.let(::recordingIn)

    fun delete(id: String) {
        File(root, id).takeIf { it.parentFile == root }?.deleteRecursively()
    }

    private fun recordingIn(folder: File): File? =
        folder.listFiles()?.firstOrNull { it.isFile && it.name.startsWith("$RECORDING.") && !it.name.endsWith(".tmp") }

    private fun folder(id: String): File? = File(root, id).takeIf { it.parentFile == root && it.isDirectory }

    private fun read(folder: File): SavedScore? = runCatching {
        val metadata = Properties().apply { File(folder, "score.properties").inputStream().use(::load) }
        SavedScore(
            id = folder.name,
            title = metadata.getProperty("title") ?: return null,
            profile = metadata.getProperty("profile") ?: "brass-band",
            updated = metadata.getProperty("updated")?.toLongOrNull() ?: 0L,
            jobId = metadata.getProperty("job"),
            checked = metadata.getProperty("checked")?.split(',')?.filter(String::isNotBlank)?.toSet().orEmpty(),
            part = metadata.getProperty("part"),
            noticeSeen = metadata.getProperty("notice_seen") == "true",
            changedOnPhone = metadata.getProperty("changed_on_phone") == "true",
            reviewChanges = metadata.getProperty("review_changes")?.split(',')?.mapNotNull { e ->
                val at = e.lastIndexOf('=')
                if (at <= 0) null else e.substring(at + 1).toIntOrNull()?.let { e.substring(0, at) to it }
            }?.toMap().orEmpty(),
            draft = metadata.getProperty("draft") == "true",
            recording = recordingIn(folder)?.name,
        )
    }.getOrNull()

    private companion object {
        const val RECORDING = "recording"
    }

    private fun writeAtomic(file: File, text: String) {
        val temporary = File(file.parentFile, "${file.name}.tmp")
        temporary.writeText(text)
        check(temporary.renameTo(file)) { "couldn't save ${file.name}" }
    }
}
