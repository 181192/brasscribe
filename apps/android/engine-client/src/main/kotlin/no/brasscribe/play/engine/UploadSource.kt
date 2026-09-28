package no.brasscribe.play.engine

import java.io.File
import java.io.InputStream

/**
 * A file to send to the engine, read as a stream so memory stays flat whatever its size.
 * [open] may be called more than once (a retried request opens the stream again); each call
 * returns a fresh stream positioned at the start, which the caller closes.
 */
class UploadSource(val filename: String, val size: Long, val open: () -> InputStream) {
    init { require(size >= 0) { "size must not be negative" } }

    companion object {
        fun of(file: File, filename: String = file.name): UploadSource = UploadSource(filename, file.length()) { file.inputStream() }

        /** For small payloads and tests; the bytes are already in memory. */
        fun of(filename: String, bytes: ByteArray): UploadSource = UploadSource(filename, bytes.size.toLong()) { bytes.inputStream() }
    }
}

/** Upload progress: request bytes sent so far and the request's total (the file plus a little framing). */
typealias UploadProgress = (sent: Long, total: Long) -> Unit

suspend fun EngineApi.uploadAudio(filename: String, bytes: ByteArray): AudioRef = uploadAudio(UploadSource.of(filename, bytes))

suspend fun EngineApi.createJobFromUpload(filename: String, bytes: ByteArray, profile: Profile, title: String?, renderAudio: Boolean = true): Job =
    createJobFromUpload(UploadSource.of(filename, bytes), profile, title, renderAudio)
