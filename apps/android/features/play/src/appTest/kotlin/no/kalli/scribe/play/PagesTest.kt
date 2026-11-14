package no.kalli.scribe.play

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.Uri
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.engine.EngineException
import no.kalli.scribe.engine.InputRefusal
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Printed music as the phone takes it in: what a file is by how it starts and the type it came with, and the copy
 * that is sent (as it is, or read by the phone and written as an upright JPEG that is not too large). The pictures
 * are made here.
 */
@RunWith(AndroidJUnit4::class)
class PagesTest {
    private val context: Context get() = ApplicationProvider.getApplicationContext()
    private val from get() = File(context.cacheDir, "pages-test-from").apply { mkdirs() }
    private val dir get() = File(context.cacheDir, "pages-test")

    @After
    fun clean() {
        from.deleteRecursively()
        dir.deleteRecursively()
    }

    /** A picture with a dark bar across its top, so which way up it is can be seen. */
    private fun picture(width: Int, height: Int, format: Bitmap.CompressFormat, alpha: Boolean = false): ByteArray {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(if (alpha) Color.TRANSPARENT else Color.WHITE)
        for (x in 0 until width) for (y in 0 until maxOf(1, height / 4)) bitmap.setPixel(x, y, Color.BLACK)
        return ByteArrayOutputStream().also { bitmap.compress(format, 95, it) }.toByteArray()
    }

    /** [jpeg] with EXIF data that says it was taken on its side: its top is the picture's right-hand edge (orientation 6). */
    private fun onItsSide(jpeg: ByteArray): ByteArray {
        val tiff = byteArrayOf('M'.code.toByte(), 'M'.code.toByte(), 0, 42, 0, 0, 0, 8, 0, 1, 0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, 6, 0, 0, 0, 0, 0, 0)
        val exif = "Exif".toByteArray() + byteArrayOf(0, 0) + tiff
        val length = exif.size + 2
        return jpeg.copyOfRange(0, 2) + byteArrayOf(0xFF.toByte(), 0xE1.toByte(), (length shr 8).toByte(), length.toByte()) + exif + jpeg.copyOfRange(2, jpeg.size)
    }

    private fun file(name: String, bytes: ByteArray): Uri = Uri.fromFile(File(from, name).apply { writeBytes(bytes) })

    private fun take(name: String, bytes: ByteArray): Page = Pages.take(context, file(name, bytes), name, dir)

    private fun size(file: File): Pair<Int, Int> =
        BitmapFactory.Options().apply { inJustDecodeBounds = true }.also { BitmapFactory.decodeFile(file.path, it) }.let { it.outWidth to it.outHeight }

    private fun head(text: String, vararg bytes: Int): ByteArray = bytes.map { it.toByte() }.toByteArray() + text.toByteArray(Charsets.ISO_8859_1)

    @Test
    fun aFileIsToldByHowItStartsAndTheTypeItCameWith() {
        assertEquals(Pages.Kind.PDF, Pages.kindOf("%PDF-1.7\n%".toByteArray(), null))
        assertEquals(Pages.Kind.PNG, Pages.kindOf(picture(4, 4, Bitmap.CompressFormat.PNG).copyOf(Pages.HEAD_BYTES), "application/octet-stream"))
        assertEquals(Pages.Kind.JPEG, Pages.kindOf(picture(4, 4, Bitmap.CompressFormat.JPEG).copyOf(Pages.HEAD_BYTES), null))
        assertEquals(Pages.Kind.WEBP, Pages.kindOf(head("RIFF") + ByteArray(4) + head("WEBPVP8 "), null))
        // What the computer does not read, the phone may: an iPhone's HEIC, AVIF, GIF, TIFF.
        assertEquals(Pages.Kind.OTHER, Pages.kindOf(head("", 0x49, 0x49, 0x2A, 0x00, 8, 0, 0, 0), null))
        assertEquals(Pages.Kind.OTHER, Pages.kindOf(head("", 0x4D, 0x4D, 0x00, 0x2A, 0, 0, 0, 8), null))
        for (brand in listOf("heic", "heix", "mif1", "avif")) assertEquals(brand, Pages.Kind.OTHER, Pages.kindOf(head("ftyp$brand", 0, 0, 0, 0x18) + ByteArray(4), null))
        assertEquals(Pages.Kind.OTHER, Pages.kindOf("GIF89a".toByteArray() + ByteArray(8), null))
        // A picture by its type alone is left to the phone to read (a BMP, or whatever a newer phone takes).
        assertEquals(Pages.Kind.OTHER, Pages.kindOf("BM".toByteArray() + ByteArray(12), "image/bmp"))
        assertEquals(Pages.Kind.OTHER, Pages.kindOf(ByteArray(16), "image/x-new; charset=binary"))
        // A recording is no page: an M4A or MP4 starts with the same box as a HEIC, a WAV with the same four letters as a WebP.
        assertNull(Pages.kindOf(head("ftypM4A ", 0, 0, 0, 0x20) + ByteArray(4), "audio/mp4"))
        assertNull(Pages.kindOf(head("ftypisom", 0, 0, 0, 0x20) + ByteArray(4), null))
        assertNull(Pages.kindOf(head("RIFF") + ByteArray(4) + head("WAVEfmt "), "audio/wav"))
        assertNull(Pages.kindOf("<?xml version=\"1.0\"?>".toByteArray(), "application/xml"))
        assertNull(Pages.kindOf(ByteArray(0), null))
        // Its name says nothing: a picture named as a recording is a picture, and the other way round.
        assertTrue(Pages.isPage(null) { picture(4, 4, Bitmap.CompressFormat.PNG).inputStream() })
        assertFalse(Pages.isPage("audio/mpeg") { "ID3".toByteArray().inputStream() })
        // What came as a picture or a PDF is brought in as a page, and may then turn out to be neither.
        assertTrue(Pages.isPage("application/pdf") { "not a pdf".toByteArray().inputStream() })
        assertTrue(Pages.isPage("image/heic") { null })
    }

    @Test
    fun aPictureTheComputerReadsIsSentAsItIs() {
        for ((name, format) in listOf("p.png" to Bitmap.CompressFormat.PNG, "p.jpeg" to Bitmap.CompressFormat.JPEG, "p.webp" to Bitmap.CompressFormat.WEBP_LOSSLESS)) {
            val bytes = picture(60, 80, format)
            val page = take(name, bytes)
            assertArrayEquals(name, bytes, page.file.readBytes())
            assertEquals(name, page.name)
            assertEquals(dir, page.file.parentFile)
        }
        val pdf = "%PDF-1.7\n1 0 obj\n<<>>\nendobj\n".toByteArray()
        assertArrayEquals(pdf, take("Hymn.pdf", pdf).file.readBytes())
        // A screenshot that came without a name's ending gets the one of what it is.
        assertEquals("Screenshot.png", take("Screenshot", picture(8, 8, Bitmap.CompressFormat.PNG)).name)
        // Nothing but the pages is left in their folder.
        assertEquals(5, dir.listFiles()!!.size)
    }

    @Test
    fun aPictureTheComputerDoesNotReadIsMadeAJpeg() {
        // The smallest GIF there is: one see-through pixel, which becomes paper.
        val gif = "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b".chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val page = take("page.gif", gif)
        assertEquals("page.jpg", page.name)
        assertEquals(Pages.Kind.JPEG, Pages.kindOf(page.file.readBytes().copyOf(Pages.HEAD_BYTES), null))
        assertEquals(1 to 1, size(page.file))
        val pixel = BitmapFactory.decodeFile(page.file.path).getPixel(0, 0)
        assertTrue("paper, not black: ${Integer.toHexString(pixel)}", Color.red(pixel) > 240 && Color.green(pixel) > 240 && Color.blue(pixel) > 240)
    }

    @Test
    fun aVeryLargePictureIsMadeSmaller() {
        val page = take("Photo.png", picture(Pages.MAX_SIDE * 2, 500, Bitmap.CompressFormat.PNG))
        assertEquals("Photo.jpg", page.name)
        assertEquals(Pages.MAX_SIDE to 250, size(page.file))
        // One just inside the limit is not touched.
        val fits = picture(Pages.MAX_SIDE, 40, Bitmap.CompressFormat.PNG)
        assertArrayEquals(fits, take("Fits.png", fits).file.readBytes())
    }

    @Test
    fun aPhotoTakenOnItsSideIsTurnedUpright() {
        // 80 wide and 40 high as it is stored, with its dark bar along the stored top: upright, the bar is down its right-hand side.
        val page = take("IMG.jpg", onItsSide(picture(80, 40, Bitmap.CompressFormat.JPEG)))
        assertEquals(40 to 80, size(page.file))
        val upright = BitmapFactory.decodeFile(page.file.path)
        fun dark(x: Int, y: Int) = Color.red(upright.getPixel(x, y)) < 80
        assertTrue("the bar is on the right", dark(38, 10) && dark(38, 70))
        assertFalse("and not on the left or along the top", dark(2, 40) || dark(15, 2))
        // An upright photo that says so is left as it is.
        val straight = picture(80, 40, Bitmap.CompressFormat.JPEG)
        assertArrayEquals(straight, take("Straight.jpg", straight).file.readBytes())
    }

    @Test
    fun whatIsNoPageIsRefusedAndLeavesNothingBehind() {
        for ((name, bytes) in listOf("notes.txt" to "do re mi".toByteArray(), "take.wav" to head("RIFF") + ByteArray(4) + head("WAVEfmt "), "empty.png" to ByteArray(0))) {
            assertTrue(name, runCatching { take(name, bytes) }.exceptionOrNull() is NotAPageException)
        }
        // It starts as a picture and is none: the phone cannot read it, and it is not sent as a JPEG that is no picture.
        assertTrue(runCatching { take("broken.gif", "GIF89a".toByteArray() + ByteArray(20) { 9 }) }.exceptionOrNull() is NotAPageException)
        assertEquals(emptyList<File>(), dir.listFiles().orEmpty().toList())
    }

    @Test
    fun aFileLargerThanTheComputerReadsIsRefusedBeforeItIsCopied() {
        // By the size it is said to have: nothing of it is read.
        val big = File(from, "Whole book.pdf")
        java.io.RandomAccessFile(big, "rw").use { it.write("%PDF-1.7\n".toByteArray()); it.setLength(Pages.MAX_BYTES + 1) }
        assertTrue(runCatching { Pages.take(context, Uri.fromFile(big), "Whole book.pdf", dir) }.exceptionOrNull() is PageTooLargeException)
        assertEquals(emptyList<File>(), dir.listFiles().orEmpty().toList())
        // One of exactly the size the computer reads is taken.
        java.io.RandomAccessFile(big, "rw").use { it.setLength(Pages.MAX_BYTES) }
        assertEquals(Pages.MAX_BYTES, Pages.take(context, Uri.fromFile(big), "Whole book.pdf", dir).file.length())
        big.delete()
        // With no size to ask for, the copy is given up as soon as it has passed the limit, not at the file's end.
        var read = 0L
        val endless = object : java.io.InputStream() {
            override fun read(): Int = 0.also { read++ }
            override fun read(b: ByteArray, off: Int, len: Int): Int = len.also { read += it }
        }
        val out = java.io.ByteArrayOutputStream()
        assertFalse(Pages.copyUpTo(endless, out, 100_000))
        assertTrue("stopped at the limit: read $read, wrote ${out.size()}", read <= 100_000 + (1 shl 16) && out.size() <= 100_000)
        val small = ByteArray(70_000) { it.toByte() }
        val whole = java.io.ByteArrayOutputStream()
        assertTrue(Pages.copyUpTo(small.inputStream(), whole, 100_000))
        assertArrayEquals(small, whole.toByteArray())
        assertEquals(R.string.error_page_too_large, ErrorWords.of(EngineException(413, "v1/jobs/pages: 413", InputRefusal.PAGE_TOO_LARGE)))
    }

    @Test
    fun aPhotoFromTheCameraBecomesThePage() {
        dir.mkdirs()
        val photo = File(dir, "photo-1.jpg").apply { writeBytes(picture(64, 48, Bitmap.CompressFormat.JPEG)) }
        val page = Pages.photo(photo, "Sheet music")
        assertEquals("Sheet music.jpg", page.name)
        assertEquals(64 to 48, size(page.file))
        assertFalse("the camera's file is the page now", photo.exists())
        assertEquals(listOf(page.file), dir.listFiles()!!.toList())
    }

    @Test
    fun whyThePagesWereNotReadIsSaidInTheAppsWords() {
        assertEquals(Problem.NOT_A_PAGE, PlayViewModel.pagesProblem(EngineException(415, "v1/jobs/pages: 415", InputRefusal.NOT_A_PAGE)))
        // A job that failed: told by the fixed words at the end of its error, after the stage's name.
        fun failed(said: String) = EngineJobFailedException("read: $said")
        assertEquals(Problem.NO_NOTES_ON_PAGE, PlayViewModel.pagesProblem(failed("no notes were found on the page")))
        assertEquals(R.string.error_engine_failed, ErrorWords.of(failed("no notes were found on the page")))
        assertEquals(Problem.NO_NOTES_ON_PAGE, PlayViewModel.pagesProblem(EngineJobFailedException("notes: no staff of notes was found on the page: a tab staff is not read")))
        assertEquals(R.string.error_only_tab_on_page, ErrorWords.of(EngineJobFailedException("notes: no staff of notes was found on the page: a tab staff is not read")))
        assertEquals(Problem.PAGES_FAILED, PlayViewModel.pagesProblem(failed("there are more than 40 pages")))
        assertEquals(R.string.error_too_many_pages, ErrorWords.of(failed("there are more than 40 pages")))
        assertEquals(Problem.PAGES_FAILED, PlayViewModel.pagesProblem(failed("a page is too large to read")))
        assertEquals(R.string.error_page_too_large, ErrorWords.of(failed("a page is too large to read")))
        // The general failure, and anything a newer engine may say.
        for (said in listOf("the pages could not be read", "something else", "no notes were found on the page, perhaps")) {
            assertEquals(said, Problem.PAGES_FAILED, PlayViewModel.pagesProblem(failed(said)))
            assertEquals(said, R.string.error_engine_failed, ErrorWords.of(failed(said)))
        }
        // What the computer refuses before a job is made.
        assertEquals(R.string.error_page_too_large, ErrorWords.of(EngineException(413, "v1/jobs/pages: 413", InputRefusal.PAGE_TOO_LARGE)))
        assertEquals(R.string.error_reader_missing, ErrorWords.of(EngineException(503, "v1/jobs/pages: 503", InputRefusal.READER_MISSING)))
        assertEquals(Problem.PAGES_FAILED, PlayViewModel.pagesProblem(EngineException(503, "v1/jobs/pages: 503", InputRefusal.READER_MISSING)))
        assertEquals(Problem.PAGES_FAILED, PlayViewModel.pagesProblem(PagesNotReadException()))
        assertEquals(R.string.error_pages_not_read, ErrorWords.of(PagesNotReadException()))
        assertEquals(R.string.error_not_a_page, ErrorWords.of(EngineException(415, "v1/jobs/pages: 415", InputRefusal.NOT_A_PAGE)))
        assertEquals(R.string.error_too_large_for_computer, ErrorWords.of(EngineException(413, "v1/jobs/pages: 413")))
        assertEquals(R.string.where_companion_missing, ErrorWords.of(NoCompanionException()))
        // The words the engine fails such a job with are the ones looked for.
        val sheet = File(checkNotNull(System.getProperty("scribe.repo")) { "scribe.repo is not set by the build" }, "engine/src/scribe_engine/sheet.py")
        val engine = sheet.readText()
        for (said in listOf(ErrorWords.NO_NOTES_ON_PAGE, ErrorWords.ONLY_TAB_ON_PAGE, ErrorWords.PAGE_TOO_LARGE, ErrorWords.PAGES_NOT_READ)) {
            assertTrue("$sheet says \"$said\"", engine.contains("\"$said\""))
        }
        assertTrue(engine.contains("f\"there are more than {pages.MAX_PAGES} pages\""))
    }

    /**
     * Where the phone sends the player to install the reader, it uses Bandroom's own words for the section and its
     * button (Bandroom for Windows' strings, which a test there holds to the copy deck and the Mac's).
     */
    @Test
    fun whereTheReaderIsInstalledIsNamedInBandroomsOwnWords() {
        val repo = File(checkNotNull(System.getProperty("scribe.repo")) { "scribe.repo is not set by the build" })
        fun value(file: File, pattern: String) = checkNotNull(Regex(pattern, RegexOption.DOT_MATCHES_ALL).find(file.readText())) { "$pattern in $file" }.groupValues[1]
        for ((bandroom, phone) in listOf("en-US" to "values", "nb-NO" to "values-nb")) {
            val resw = File(repo, "apps/bandroom/windows/src/Brasscribe.Bandroom/Strings/$bandroom/Resources.resw")
            val section = value(resw, "<data name=\"Settings_Reader\"[^>]*>\\s*<value>([^<]+)</value>")
            val button = value(resw, "<data name=\"Settings_Reader_Install\"[^>]*>\\s*<value>([^<]+)</value>")
            val strings = File(repo, "apps/android/features/play/src/main/res/$phone/strings.xml")
            val missing = value(strings, "<string name=\"error_reader_missing\">([^<]+)</string>")
            val notRead = value(strings, "<string name=\"error_pages_not_read\">([^<]+)</string>")
            assertTrue("$missing names the section $section", missing.contains(section))
            assertTrue("$missing names the button $button", missing.contains(button))
            assertTrue("$notRead names the section $section", notRead.contains(section))
        }
    }
}
