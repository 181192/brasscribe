package no.brasscribe.play

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.export.AndroidPdfPages
import no.brasscribe.play.export.PhonePdf
import no.brasscribe.play.screen.ScreenDevice
import no.brasscribe.play.test.DeviceOnly
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The PDF the phone lays out, written by Android's PDF document (which the JVM does not have): a real PDF of A4
 * pages, vector (the page's drawing is in the file, not a picture of it: small, and the music font is embedded), that
 * the system's own PDF renderer draws with ink on it. Every part is one document of every part's pages.
 */
@DeviceOnly
@RunWith(AndroidJUnit4::class)
class PhonePdfDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun aPartAndEveryPartAreRealPdfsWithInkOnA4() {
        val xml = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml"))
        val pdf = PhonePdf(context)
        val score = pdf.parse(xml)
        val start = android.os.SystemClock.elapsedRealtime()
        val parts = (0 until score.tracks.length.toInt()).map { pdf.engrave(score, listOf(it), "part $it", PhonePdf.PART_SCALE) }
        val one = File(context.cacheDir, "phone-pdf-part.pdf")
        pdf.Document(AndroidPdfPages()).use { d -> d.add(parts[1]); one.outputStream().use { d.writeTo(it) } }
        val all = File(context.cacheDir, "phone-pdf-all.pdf")
        val pages = pdf.Document(AndroidPdfPages()).use { d -> parts.forEach(d::add); all.outputStream().use { d.writeTo(it) }; d.pageCount }
        android.util.Log.i("PhonePdfDeviceTest", "${parts.size} parts engraved and written in ${android.os.SystemClock.elapsedRealtime() - start} ms, ${all.length()} bytes, $pages pages")

        val bytes = one.readBytes()
        assertEquals("%PDF-", String(bytes, 0, 5, Charsets.ISO_8859_1))
        // Vector: an A4 page of music in a few tens of kilobytes (a picture of it at print resolution is megabytes).
        assertTrue("${bytes.size} bytes", bytes.size < 400_000)
        // The music's glyphs are in the file, as an embedded font or as glyph drawings (Type 3), never left to the reader.
        val text = String(bytes, Charsets.ISO_8859_1)
        val fonts = Regex("""/(FontFile[23]?|Subtype\s*/\w+)""").findAll(text).map { it.value }.toSet()
        android.util.Log.i("PhonePdfDeviceTest", "a part: ${bytes.size} bytes, fonts $fonts")
        assertTrue("fonts in the file: $fonts (${bytes.size} bytes)", fonts.any { it.startsWith("/FontFile") } || fonts.any { it.contains("Type3") })

        PdfRenderer(ParcelFileDescriptor.open(one, ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
            assertEquals(1, r.pageCount)
            r.openPage(0).use { page ->
                assertEquals(PhonePdf.PAGE_W, page.width)
                assertEquals(PhonePdf.PAGE_H, page.height)
                val bmp = Bitmap.createBitmap(page.width, page.height, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.WHITE) }
                page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
                val px = IntArray(bmp.width * bmp.height).also { bmp.getPixels(it, 0, bmp.width, 0, 0, bmp.width, bmp.height) }
                assertTrue("ink on the page", px.count { Color.red(it) < 128 } > 2_000)
            }
        }
        PdfRenderer(ParcelFileDescriptor.open(all, ParcelFileDescriptor.MODE_READ_ONLY)).use { r -> assertEquals(pages, r.pageCount) }
        assertTrue(pages >= parts.size)
    }
}
