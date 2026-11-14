package no.kalli.scribe.play

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.util.LruCache
import java.io.File

/** What a page's row shows of it: a small [picture], or none when it cannot be read; a PDF's [pages], when it says. */
class PageThumbnail(val picture: Bitmap?, val pages: Int? = null)

/**
 * Small pictures of the pages in hand, for their rows. A picture is never read whole: its size is asked first and it
 * is sampled down while it is read ([sampleSize]), so a row costs a few tens of kilobytes whatever the page. A PDF
 * shows its first page, drawn small by the phone's own reader, and how many pages it has. One that cannot be read
 * (or a phone without that reader) has no picture, and the row shows an icon. Each is made once per page and kept
 * while the screen is: a page's file never changes.
 */
class PageThumbnails(private val side: Int = SIDE) {
    private val made = LruCache<String, PageThumbnail>(no.kalli.scribe.engine.EngineApi.MAX_PAGES * 2)

    /** The thumbnail of [page], made on the calling thread the first time: call it off the main thread. */
    fun of(page: Page): PageThumbnail = made.get(page.file.path) ?: make(page.file).also { made.put(page.file.path, it) }

    private fun make(file: File): PageThumbnail = runCatching {
        if (file.extension.equals(Pages.Kind.PDF.extension, ignoreCase = true)) pdf(file) else PageThumbnail(picture(file))
    }.getOrElse { PageThumbnail(null) }

    private fun picture(file: File): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        return BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sampleSize(bounds.outWidth, bounds.outHeight, side) })
    }

    private fun pdf(file: File): PageThumbnail =
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            PdfRenderer(descriptor).use { reader ->
                val count = reader.pageCount
                val picture = runCatching {
                    reader.openPage(0).use { first ->
                        val scale = side.toFloat() / maxOf(first.width, first.height, 1)
                        val small = Bitmap.createBitmap(maxOf(1, (first.width * scale).toInt()), maxOf(1, (first.height * scale).toInt()), Bitmap.Config.ARGB_8888)
                        // A PDF's page has no paper of its own.
                        small.eraseColor(Color.WHITE)
                        first.render(small, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        small
                    }
                }.getOrNull()
                PageThumbnail(picture, count)
            }
        }

    companion object {
        /** The longest side a thumbnail is read for, in pixels: about a row's picture on the densest screens. */
        const val SIDE = 192

        /**
         * How much a picture of [width] by [height] is sampled down while it is read, so its longest side comes out
         * at [side] or a little over: the largest power of two that leaves it no smaller (what the phone's reader takes).
         */
        fun sampleSize(width: Int, height: Int, side: Int): Int {
            var sample = 1
            while (maxOf(width, height) / (sample * 2) >= side) sample *= 2
            return sample
        }
    }
}
