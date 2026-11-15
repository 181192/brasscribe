package no.kalli.scribe.play

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageDecoder
import android.net.Uri
import java.io.File
import java.io.InputStream
import java.util.UUID

/**
 * One page of printed music in hand: [file] is the app's own copy, as it is sent; [name] is what it is called; [pages]
 * is how many pages it holds (a PDF's every page counts against [no.kalli.scribe.engine.EngineApi.MAX_PAGES], as the
 * computer counts them).
 */
data class Page(val file: File, val name: String, val pages: Int = 1)

/** The pages in [this] list, every page of a PDF counted. */
fun List<Page>.pageCount(): Int = sumOf { it.pages }

/** A PDF brought in as pages that the phone cannot open: locked with a password, or damaged. */
class UnreadablePdfException(name: String) : Exception("$name is a PDF that cannot be opened")

/** A file brought in as a page is larger than the computer reads as one ([Pages.MAX_BYTES]). */
class PageTooLargeException(name: String) : Exception("$name is larger than a page can be")

/** A file brought in as a page is neither a picture the phone can read nor a PDF. */
class NotAPageException(name: String) : Exception("$name is not a picture or a PDF")

/**
 * Printed music as the phone takes it in: pictures and PDFs, each copied into the app's own folder as the computer
 * reads it. What a file is, is told by how it starts and the type it came with, never by its name: a screenshot
 * shared from another app can come with no name at all.
 */
object Pages {
    /** What a page is. [extension]: of a copy that is sent as it is. [asItIs]: the computer reads it, so it is sent unchanged when it is upright and not too large. */
    enum class Kind(val extension: String, val asItIs: Boolean) {
        PDF("pdf", true), PNG("png", true), JPEG("jpg", true), WEBP("webp", true),

        /** A picture the computer does not read (an iPhone's HEIC, AVIF, GIF, BMP, TIFF) and the phone may: made into a JPEG here, or no page. */
        OTHER("jpg", false),
    }

    /** The longest side of a picture that is sent: a larger one is made smaller, so the pages stay quick to send. */
    const val MAX_SIDE = 3000

    private const val JPEG_QUALITY = 90

    /** The largest file the computer reads as a page: a larger one is refused here, before it is copied or sent. */
    const val MAX_BYTES = no.kalli.scribe.engine.EngineApi.MAX_PAGE_BYTES

    /**
     * How many pages the PDF [file] has, or null when it cannot be opened: locked with a password, or damaged (as on
     * the other apps, it is left out here, not sent for the computer to refuse). The phone's own reader counts them; a
     * test without that reader counts them from the file's text ([countInText]).
     */
    fun pdfPages(file: File): Int? {
        val read = runCatching {
            android.os.ParcelFileDescriptor.open(file, android.os.ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
                android.graphics.pdf.PdfRenderer(descriptor).use { it.pageCount }
            }
        }
        // Locked (SecurityException) or damaged (IOException): the phone's reader could not open it.
        if (read.exceptionOrNull() is SecurityException || read.exceptionOrNull() is java.io.IOException) return null
        read.getOrNull()?.let { return it.takeIf { n -> n > 0 } }
        return countInText(file.readBytes())
    }

    /**
     * The pages a PDF's text says it has: the largest page count of a page tree ("/Type /Pages … /Count 12"), else the
     * pages it names one by one. Null for a PDF locked with a password ("/Encrypt"), and for one that is cut short (no
     * "%%EOF") or names no page at all: a damaged file.
     */
    fun countInText(pdf: ByteArray): Int? {
        val text = String(pdf, Charsets.ISO_8859_1)
        if (text.contains("/Encrypt") || !text.contains("%%EOF")) return null
        val tree = Regex("""/Type\s*/Pages\b[^>]*?/Count\s+(\d+)|/Count\s+(\d+)[^>]*?/Type\s*/Pages\b""").findAll(text)
            .mapNotNull { m -> (m.groupValues[1].ifEmpty { m.groupValues[2] }).toIntOrNull() }.maxOrNull()
        val named = Regex("""/Type\s*/Page\b(?!s)""").findAll(text).count()
        return (tree ?: named).takeIf { it > 0 }
    }

    /** How much of a file says what it is. */
    const val HEAD_BYTES = 16

    /** The brands of a HEIF file (HEIC and AVIF): the same box starts an MP4 or M4A recording, with another brand. */
    private val HEIF_BRANDS = setOf("heic", "heix", "hevc", "hevx", "heim", "heis", "mif1", "msf1", "avif", "avis")

    /**
     * What [head] (a file's first [HEAD_BYTES]) and [mime] (the type it came with, null when nothing says) make
     * the file; null when it is no page. A file that starts as a picture or a PDF is one whatever its type says;
     * one that came as a picture and starts as nothing known is left to the phone to read.
     */
    fun kindOf(head: ByteArray, mime: String?): Kind? {
        fun starts(vararg bytes: Int) = head.size >= bytes.size && bytes.indices.all { head[it] == bytes[it].toByte() }
        val text = String(head, Charsets.ISO_8859_1)
        val type = mime?.substringBefore(';')?.trim()?.lowercase()
        return when {
            text.startsWith("%PDF-") -> Kind.PDF
            starts(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A) -> Kind.PNG
            starts(0xFF, 0xD8, 0xFF) -> Kind.JPEG
            text.startsWith("RIFF") && text.drop(8).startsWith("WEBP") -> Kind.WEBP
            starts(0x49, 0x49, 0x2A, 0x00) || starts(0x4D, 0x4D, 0x00, 0x2A) -> Kind.OTHER
            text.startsWith("GIF87a") || text.startsWith("GIF89a") -> Kind.OTHER
            text.drop(4).startsWith("ftyp") && text.drop(8).take(4) in HEIF_BRANDS -> Kind.OTHER
            type?.startsWith("image/") == true -> Kind.OTHER
            else -> null
        }
    }

    /** Whether a file is brought in as a page: it starts as one, or it came as a picture or a PDF (and may then turn out to be neither). */
    fun isPage(mime: String?, open: () -> InputStream?): Boolean {
        val type = mime?.substringBefore(';')?.trim()?.lowercase()
        if (type == "application/pdf" || type?.startsWith("image/") == true) return true
        return runCatching { open()?.use { kindOf(head(it), type) } }.getOrNull() != null
    }

    /**
     * The page at [uri], copied into [dir] as it is sent. A PDF, and a PNG, JPEG or WebP picture that is
     * upright and no larger than [MAX_SIDE], is kept byte for byte. Any other picture is read by the phone and
     * written as a JPEG: turned upright (a photo says in its EXIF data which way up it was taken; the computer's
     * reader follows that too, so this only makes sure of it), and made smaller when it is larger than [MAX_SIDE].
     * A file over [MAX_BYTES] is refused before any of it is copied, by the size its provider gives; one whose size
     * is not known is given up as soon as the copy has passed that.
     */
    fun take(context: Context, uri: Uri, name: String, dir: File): Page {
        dir.mkdirs()
        val id = UUID.randomUUID().toString()
        val original = File(dir, "$id.part")
        try {
            val mime = runCatching { context.contentResolver.getType(uri) }.getOrNull()
            if ((sizeOf(context, uri) ?: 0L) > MAX_BYTES) throw PageTooLargeException(name)
            (context.contentResolver.openInputStream(uri) ?: throw NotAPageException(name)).use { input ->
                original.outputStream().use { if (!copyUpTo(input, it, MAX_BYTES)) throw PageTooLargeException(name) }
            }
            return page(original, name, kindOf(original.inputStream().use(::head), mime) ?: throw NotAPageException(name), File(dir, id))
        } finally {
            original.delete()
        }
    }

    /** The size of the file at [uri] as its provider says it (a file's own length for a file), or null when nothing says. */
    private fun sizeOf(context: Context, uri: Uri): Long? = runCatching {
        if (uri.scheme == "file") return@runCatching uri.path?.let(::File)?.length()
        context.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst() && !c.isNull(0)) c.getLong(0) else null
        }
    }.getOrNull()

    /** Copies [input] to [out] a buffer at a time, and stops once more than [limit] bytes have come: false then. */
    fun copyUpTo(input: InputStream, out: java.io.OutputStream, limit: Long): Boolean {
        val buffer = ByteArray(1 shl 16)
        var copied = 0L
        while (true) {
            val n = input.read(buffer)
            if (n < 0) return true
            copied += n
            if (copied > limit) return false
            out.write(buffer, 0, n)
        }
    }

    /** As [take], for a photo the camera wrote to [photo], which is in the pages' folder already: it becomes the page. */
    fun photo(photo: File, name: String): Page {
        try {
            val kind = kindOf(photo.inputStream().use(::head), "image/jpeg") ?: throw NotAPageException(name)
            return page(photo, name, kind, File(photo.parentFile, UUID.randomUUID().toString()))
        } finally {
            photo.delete()
        }
    }

    /** [original] as a page at [stem] with its kind's extension: moved there as it is, or read and written as a JPEG. */
    private fun page(original: File, name: String, kind: Kind, stem: File): Page {
        fun titled(extension: String) = "${name.substringBeforeLast('.').ifBlank { name }}.$extension"
        if (kind == Kind.PDF || (kind.asItIs && fitsAsItIs(original))) {
            // A PDF counts as its pages; one the phone cannot open is no page it can send.
            val count = if (kind == Kind.PDF) pdfPages(original) ?: throw UnreadablePdfException(name) else 1
            val to = File(stem.parentFile, "${stem.name}.${kind.extension}")
            check(original.renameTo(to)) { "the page could not be kept" }
            // The name it came with, when that says what it is; else with the kind it was found to be.
            return Page(to, if (name.substringAfterLast('.', "").lowercase() in EXTENSIONS.getValue(kind)) name else titled(kind.extension), count)
        }
        val to = File(stem.parentFile, "${stem.name}.${Kind.JPEG.extension}")
        try {
            val picture = ImageDecoder.decodeBitmap(ImageDecoder.createSource(original)) { decoder, info, _ ->
                // In memory, where it can be drawn on and compressed, and no larger than it is sent.
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                val longest = maxOf(info.size.width, info.size.height)
                if (longest > MAX_SIDE) {
                    val scale = MAX_SIDE.toFloat() / longest
                    decoder.setTargetSize(maxOf(1, Math.round(info.size.width * scale)), maxOf(1, Math.round(info.size.height * scale)))
                }
            }
            // A JPEG has no see-through: what was, is paper.
            val opaque = if (!picture.hasAlpha()) picture else Bitmap.createBitmap(picture.width, picture.height, Bitmap.Config.ARGB_8888).also {
                Canvas(it).apply { drawColor(Color.WHITE); drawBitmap(picture, 0f, 0f, null) }
                picture.recycle()
            }
            to.outputStream().use { check(opaque.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, it)) { "the page could not be written" } }
            opaque.recycle()
            return Page(to, titled(Kind.JPEG.extension))
        } catch (e: Exception) {
            to.delete()
            throw NotAPageException(name).also { it.initCause(e) }
        }
    }

    /** A picture the computer reads is sent as it is when it is upright and no side is longer than [MAX_SIDE]. */
    // The platform's EXIF reader: the faults lint warns of are in Android versions older than the apps run on.
    @android.annotation.SuppressLint("ExifInterface")
    private fun fitsAsItIs(file: File): Boolean {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        // A picture whose size the phone cannot read goes as it is: the computer may still read it.
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return true
        if (maxOf(bounds.outWidth, bounds.outHeight) > MAX_SIDE) return false
        val upright = android.media.ExifInterface.ORIENTATION_NORMAL
        val turned = runCatching { android.media.ExifInterface(file).getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION, upright) }.getOrDefault(upright)
        return turned == upright || turned == android.media.ExifInterface.ORIENTATION_UNDEFINED
    }

    private val EXTENSIONS = mapOf(
        Kind.PDF to setOf("pdf"), Kind.PNG to setOf("png"), Kind.JPEG to setOf("jpg", "jpeg"), Kind.WEBP to setOf("webp"),
        Kind.OTHER to emptySet(),
    )

    private fun head(input: InputStream): ByteArray {
        val bytes = ByteArray(HEAD_BYTES)
        var filled = 0
        while (filled < bytes.size) {
            val n = input.read(bytes, filled, bytes.size - filled)
            if (n < 0) break
            filled += n
        }
        return bytes.copyOf(filled)
    }
}
