package no.brasscribe.play

import java.io.File
import java.util.Properties
import java.util.UUID

/** A recording kept in Your scores before it has a score: it opens What is this? again with the recording. */
data class KeptRecording(
    val id: String,
    val title: String,
    val kind: SourceKind,
    val seconds: Double,
    /** Milliseconds since the epoch: when it was kept. */
    val updated: Long,
    val file: File,
)

/**
 * The recordings kept in Your scores, one folder each under [root] (the app's `noBackupFilesDir`, so they stay out
 * of the phone's backup: they are large, and may be someone else's music). A folder holds the recording and
 * `kept.properties`. The scores in Your scores are elsewhere and are never touched.
 *
 * No step loses a recording, whatever fails and wherever the process ends. The details are written before the
 * recording is moved in; a move that fails leaves the recording where it was, and a folder that never got its
 * recording is cleared. A recording found without details is listed again, never deleted ([prune]).
 */
class KeptRecordingStore(private val root: File, private val files: Files = Files()) {
    /** The file operations a keep is made of, one at a time (the tests make one of them fail, or end there). */
    open class Files {
        open fun write(file: File, details: Properties) = file.outputStream().use { details.store(it, null) }
        open fun rename(from: File, to: File): Boolean = from.renameTo(to)
        open fun copy(from: File, to: File) { from.copyTo(to, overwrite = true) }
        open fun delete(file: File): Boolean = file.deleteRecursively()
    }

    fun list(): List<KeptRecording> = root.listFiles()?.mapNotNull(::read)?.sortedByDescending { it.updated }.orEmpty()

    /**
     * Keeps [file] as a recording called [title]. A file of the store's own is kept where it is (its details are
     * written again); any other file is moved in, so the caller's copy is gone and the returned [KeptRecording.file]
     * takes its place. When it throws, [file] is where it was and nothing is listed for it.
     */
    fun keep(file: File, title: String, kind: SourceKind, seconds: Double, now: Long = System.currentTimeMillis()): KeptRecording {
        folderOf(file)?.let { own ->
            writeDetails(own, details(file.name, title, kind, seconds, now))
            return KeptRecording(own.name, title, kind, seconds, now, file)
        }
        val folder = File(root, UUID.randomUUID().toString())
        check(folder.mkdirs()) { "couldn't keep the recording" }
        val target = File(folder, "$RECORDING.${file.extension.lowercase().ifBlank { "wav" }}")
        try {
            writeDetails(folder, details(target.name, title, kind, seconds, now))
            moveIn(file, target)
        } catch (e: Exception) {
            // The recording was not moved (a move either happens or leaves it): the empty folder goes.
            files.delete(folder)
            throw e
        }
        return KeptRecording(folder.name, title, kind, seconds, now, target)
    }

    /** The kept recording [file] is, or null. */
    fun entryOf(file: File): KeptRecording? = folderOf(file)?.let(::read)?.takeIf { it.file.canonicalFile == file.canonicalFile }

    /** Whether [file] is in the store: kept, or no longer listed and waiting for [prune]. */
    fun owns(file: File): Boolean = folderOf(file) != null

    /** Leaves Your scores (its score was made): the recording itself stays while it is in use, until [prune]. */
    fun forget(id: String) {
        val folder = folder(id) ?: return
        val details = readDetails(folder) ?: return
        writeDetails(folder, details.apply { setProperty(FORGOTTEN, "true") })
    }

    /** Deleted from Your scores: the details and the recording. */
    fun delete(id: String) {
        folder(id)?.let(files::delete)
    }

    /**
     * Clears what is no longer kept, except the folder of [inUse] (the recording in hand): a recording whose score
     * was made, and a folder that never got its recording. A recording without details is listed again instead.
     */
    fun prune(inUse: File?) {
        val busy = inUse?.let(::folderOf)
        for (folder in root.listFiles().orEmpty()) {
            if (!folder.isDirectory || folder == busy) continue
            val details = readDetails(folder)
            val recording = details?.getProperty("file")?.let { File(folder, it) }?.takeIf(File::isFile)
                ?: folder.listFiles()?.firstOrNull { it.isFile && it.name.startsWith("$RECORDING.") && !it.name.endsWith(".tmp") }
            when {
                recording == null -> files.delete(folder)
                details?.getProperty(FORGOTTEN) == "true" -> files.delete(folder)
                details == null || details.getProperty("file") != recording.name -> runCatching {
                    writeDetails(folder, details(recording.name, details?.getProperty("title").orEmpty(), SourceKind.FILE,
                        details?.getProperty("seconds")?.toDoubleOrNull() ?: 0.0, recording.lastModified()))
                }
            }
        }
    }

    /** What the kept recordings take on the phone, in bytes. */
    fun bytes(): Long = list().sumOf { it.file.length() }

    private fun details(file: String, title: String, kind: SourceKind, seconds: Double, updated: Long) = Properties().apply {
        setProperty("title", title)
        setProperty("kind", kind.name)
        setProperty("seconds", seconds.toString())
        setProperty("updated", updated.toString())
        setProperty("file", file)
    }

    private fun writeDetails(folder: File, details: Properties) {
        val temporary = File(folder, "$DETAILS.tmp")
        files.write(temporary, details)
        check(files.rename(temporary, File(folder, DETAILS))) { "couldn't keep the recording" }
    }

    private fun readDetails(folder: File): Properties? =
        runCatching { Properties().apply { File(folder, DETAILS).inputStream().use(::load) } }.getOrNull()

    /** Moves [from] to [to]: a rename, or a copy that is complete before [from] goes. On failure [from] is untouched. */
    private fun moveIn(from: File, to: File) {
        if (files.rename(from, to)) return
        val temporary = File(to.parentFile, "${to.name}.tmp")
        files.copy(from, temporary)
        check(files.rename(temporary, to)) { "couldn't keep the recording" }
        files.delete(from)
    }

    private fun folder(id: String): File? = File(root, id).takeIf { it.parentFile == root && it.isDirectory }

    private fun folderOf(file: File): File? {
        // Compared as canonical paths (an app's folders are reached through a link), named as the store names them.
        val parent = file.canonicalFile.parentFile ?: return null
        return File(root, parent.name).takeIf { parent.parentFile == root.canonicalFile }
    }

    private fun read(folder: File): KeptRecording? {
        val details = readDetails(folder) ?: return null
        if (details.getProperty(FORGOTTEN) == "true") return null
        val file = File(folder, details.getProperty("file") ?: return null).takeIf(File::isFile) ?: return null
        return KeptRecording(
            id = folder.name,
            title = details.getProperty("title") ?: return null,
            kind = SourceKind.entries.firstOrNull { it.name == details.getProperty("kind") } ?: SourceKind.FILE,
            seconds = details.getProperty("seconds")?.toDoubleOrNull() ?: 0.0,
            updated = details.getProperty("updated")?.toLongOrNull() ?: 0L,
            file = file,
        )
    }

    private companion object {
        const val RECORDING = "recording"
        const val DETAILS = "kept.properties"
        const val FORGOTTEN = "forgotten"
    }
}
