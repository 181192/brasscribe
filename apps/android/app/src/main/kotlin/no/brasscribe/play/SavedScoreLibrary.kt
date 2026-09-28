package no.brasscribe.play

import java.io.File
import java.util.Properties
import java.util.UUID

data class SavedScore(
    val id: String,
    val title: String,
    val profile: String,
    val musicXml: String,
    val compositionJson: String?,
    val updated: Long,
    /** The computer's run this score came from, if any. */
    val jobId: String? = null,
    val evidenceJson: String? = null,
    /** Review events the musician kept, as "voice:index". */
    val checked: Set<String> = emptySet(),
    /** "Make this my part": the part picked for this score (its English name), or null for the seat's. */
    val part: String? = null,
    /** The one-line "this lineup has no part of your seat" notice was closed for this score. */
    val noticeSeen: Boolean = false,
    /** A note was changed on the phone: the computer's renders (audio, PDF, braille) are older than the score. */
    val changedOnPhone: Boolean = false,
)

/** App-owned score copies: MusicXML is the editable score, with its transcription beside it. */
class SavedScoreLibrary(private val root: File) {
    fun list(): List<SavedScore> = root.listFiles()?.mapNotNull(::read)
        ?.sortedByDescending { it.updated }.orEmpty()

    fun save(
        id: String?, title: String, profile: String, musicXml: String, compositionJson: String?,
        jobId: String? = null, evidenceJson: String? = null, checked: Set<String> = emptySet(), part: String? = null, noticeSeen: Boolean = false,
        changedOnPhone: Boolean = false,
    ): SavedScore {
        val key = id ?: UUID.randomUUID().toString()
        val folder = File(root, key).apply { mkdirs() }
        writeAtomic(File(folder, "score.musicxml"), musicXml)
        val composition = File(folder, "composition.json")
        if (compositionJson == null) composition.delete() else writeAtomic(composition, compositionJson)
        val evidence = File(folder, "evidence.json")
        if (evidenceJson == null) evidence.delete() else writeAtomic(evidence, evidenceJson)
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
        }
        val temporary = File(folder, "score.properties.tmp")
        temporary.outputStream().use { metadata.store(it, null) }
        check(temporary.renameTo(File(folder, "score.properties"))) { "couldn't save score details" }
        return SavedScore(key, title, profile, musicXml, compositionJson, updated, jobId, evidenceJson, checked, part, noticeSeen, changedOnPhone)
    }

    fun rename(id: String, title: String): SavedScore? {
        val current = list().firstOrNull { it.id == id } ?: return null
        return save(id, title, current.profile, current.musicXml, current.compositionJson, current.jobId, current.evidenceJson, current.checked, current.part, current.noticeSeen, current.changedOnPhone)
    }

    fun delete(id: String) {
        File(root, id).takeIf { it.parentFile == root }?.deleteRecursively()
    }

    private fun read(folder: File): SavedScore? = runCatching {
        val metadata = Properties().apply { File(folder, "score.properties").inputStream().use(::load) }
        SavedScore(
            id = folder.name,
            title = metadata.getProperty("title") ?: return null,
            profile = metadata.getProperty("profile") ?: "brass-band",
            musicXml = File(folder, "score.musicxml").readText(),
            compositionJson = File(folder, "composition.json").takeIf(File::isFile)?.readText(),
            updated = metadata.getProperty("updated")?.toLongOrNull() ?: 0L,
            jobId = metadata.getProperty("job"),
            evidenceJson = File(folder, "evidence.json").takeIf(File::isFile)?.readText(),
            checked = metadata.getProperty("checked")?.split(',')?.filter(String::isNotBlank)?.toSet().orEmpty(),
            part = metadata.getProperty("part"),
            noticeSeen = metadata.getProperty("notice_seen") == "true",
            changedOnPhone = metadata.getProperty("changed_on_phone") == "true",
        )
    }.getOrNull()

    private fun writeAtomic(file: File, text: String) {
        val temporary = File(file.parentFile, "${file.name}.tmp")
        temporary.writeText(text)
        check(temporary.renameTo(file)) { "couldn't save ${file.name}" }
    }
}