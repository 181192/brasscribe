package no.brasscribe.play

import java.io.InputStream

/**
 * Whether a file is sheet music (MusicXML), for a product that opens none and says so. A file's name need not say
 * what it is: one shared from another app can come with the type alone, and a bare `.xml` is any XML. So the name is
 * asked first, then the type the file came with, then how the file starts.
 */
object SheetMusic {
    /** The types the app takes from the share sheet and "Open with" (AndroidManifest.xml). */
    val MIME_TYPES = setOf("application/vnd.recordare.musicxml+xml", "application/vnd.recordare.musicxml")

    /** How much of an XML file is read to find its root element: past the declaration, the doctype and a comment. */
    private const val XML_HEAD_BYTES = 64 * 1024

    private val ZIP = byteArrayOf('P'.code.toByte(), 'K'.code.toByte(), 3, 4)

    /** A UTF-8 byte order mark, which an XML file may start with. */
    private val BOM = byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte())

    /**
     * [name] is the file's name, [mime] the type it came with (null when nothing says), [open] opens it to read.
     * A file that cannot be read is not called sheet music: opening it as a recording says what is wrong with it.
     */
    fun isSheetMusic(name: String, mime: String?, open: () -> InputStream?): Boolean {
        val extension = name.substringAfterLast('.', "").lowercase()
        if (extension == "musicxml" || extension == "mxl") return true
        val type = mime?.substringBefore(';')?.trim()?.lowercase()
        if (type in MIME_TYPES) return true
        // A recording by its type is not read here. Anything else is told by how it starts, which costs a few bytes.
        if (type != null && (type.startsWith("audio/") || type.startsWith("video/"))) return false
        return runCatching { open()?.buffered()?.use(::startsAsSheetMusic) }.getOrNull() ?: false
    }

    private fun startsAsSheetMusic(input: InputStream): Boolean {
        input.mark(ZIP.size)
        val magic = head(input, ZIP.size)
        input.reset()
        // A zip: compressed MusicXML when the score PlayViewModel.unzipScore finds in it is one (not every zip, nor an EPUB).
        if (magic.contentEquals(ZIP)) return isScore(PlayViewModel.unzipScore(input))
        // Anything that does not start as XML (a recording) is known after these few bytes.
        val first = magic.firstOrNull()?.toInt()?.toChar() ?: return false
        if (first != '<' && !first.isWhitespace() && magic.firstOrNull() != BOM[0]) return false
        val bytes = head(input, XML_HEAD_BYTES)
        val text = if (bytes.take(BOM.size) == BOM.toList()) bytes.copyOfRange(BOM.size, bytes.size) else bytes
        val xml = String(text, Charsets.UTF_8).trimStart()
        return xml.startsWith("<") && isScore(xml)
    }

    /** As PlayViewModel.openScore tells a MusicXML score from other XML. */
    private fun isScore(xml: String): Boolean = xml.contains("score-partwise") || xml.contains("score-timewise")

    /** The first [count] bytes of [input], or all of it when it is shorter. */
    private fun head(input: InputStream, count: Int): ByteArray {
        val bytes = ByteArray(count)
        var filled = 0
        while (filled < count) {
            val n = input.read(bytes, filled, count - filled)
            if (n < 0) break
            filled += n
        }
        return bytes.copyOf(filled)
    }
}
