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
)

/** App-owned score copies: MusicXML is the editable score, with its transcription beside it. */
class SavedScoreLibrary(private val root: File) {
    fun list(): List<SavedScore> = root.listFiles()?.mapNotNull(::read)
        ?.sortedByDescending { it.updated }.orEmpty()

    fun save(id: String?, title: String, profile: String, musicXml: String, compositionJson: String?): SavedScore {
        val key = id ?: UUID.randomUUID().toString()
        val folder = File(root, key).apply { mkdirs() }
        writeAtomic(File(folder, "score.musicxml"), musicXml)
        val composition = File(folder, "composition.json")
        if (compositionJson == null) composition.delete() else writeAtomic(composition, compositionJson)
        val updated = System.currentTimeMillis()
        val metadata = Properties().apply {
            setProperty("title", title)
            setProperty("profile", profile)
            setProperty("updated", updated.toString())
        }
        val temporary = File(folder, "score.properties.tmp")
        temporary.outputStream().use { metadata.store(it, null) }
        check(temporary.renameTo(File(folder, "score.properties"))) { "couldn't save score details" }
        return SavedScore(key, title, profile, musicXml, compositionJson, updated)
    }

    fun rename(id: String, title: String): SavedScore? {
        val current = list().firstOrNull { it.id == id } ?: return null
        return save(id, title, current.profile, current.musicXml, current.compositionJson)
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
        )
    }.getOrNull()

    private fun writeAtomic(file: File, text: String) {
        val temporary = File(file.parentFile, "${file.name}.tmp")
        temporary.writeText(text)
        check(temporary.renameTo(file)) { "couldn't save ${file.name}" }
    }
}