package no.brasscribe.play.export

import android.graphics.Bitmap
import android.graphics.Canvas
import java.io.OutputStream

/**
 * The JVM's stand-in for Android's PDF document, which Robolectric does not have (its native half is not there, so a
 * document is "closed" from the start). Each page is drawn, and the file written is a PDF with as many pages, empty:
 * what a page draws is checked in [drawn] (with [keep]; otherwise it is drawn into a recording and let go), and what
 * the real document writes is checked on a device (PhonePdfDeviceTest).
 */
class JvmPdfPages(private val keep: Boolean = false) : PdfPages {
    /** The pages drawn, each a picture of the page at 1 pixel per point; only with [keep]. */
    val drawn = ArrayList<Bitmap>()
    var pages = 0
        private set

    override fun page(width: Int, height: Int, draw: (Canvas) -> Unit) {
        pages++
        if (!keep) {
            // Drawn as a PDF page is, as drawing commands, and let go.
            val p = android.graphics.Picture()
            draw(p.beginRecording(width, height))
            p.endRecording()
            return
        }
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        draw(Canvas(bmp))
        drawn += bmp
    }

    override fun writeTo(out: OutputStream) = out.write(emptyPdf(pages))
    override fun close() = Unit

    companion object {
        /** A PDF of [pages] empty A4 pages (a classic cross-reference table, as [PdfJoin] reads). */
        fun emptyPdf(pages: Int): ByteArray {
            val objects = ArrayList<String>()
            val kids = (1..pages).map { objects += "<< /Type /Page /Parent 2 0 R >>"; objects.size + 2 }
            val all = listOf("<< /Type /Catalog /Pages 2 0 R >>",
                "<< /Type /Pages /Kids [${kids.joinToString(" ") { "$it 0 R" }}] /Count $pages /MediaBox [0 0 595 842] >>") + objects
            val out = StringBuilder("%PDF-1.4\n")
            val offsets = all.mapIndexed { i, body -> out.length.also { out.append("${i + 1} 0 obj\n$body\nendobj\n") } }
            val xref = out.length
            out.append("xref\n0 ${all.size + 1}\n0000000000 65535 f \n")
            offsets.forEach { out.append("%010d 00000 n \n".format(it)) }
            out.append("trailer\n<< /Size ${all.size + 1} /Root 1 0 R >>\nstartxref\n$xref\n%%EOF\n")
            return out.toString().toByteArray(Charsets.ISO_8859_1)
        }
    }
}
