package no.brasscribe.play.export

import alphaTab.Environment
import alphaTab.LayoutMode
import alphaTab.PlayerMode
import alphaTab.RenderEngineFactory
import alphaTab.Settings
import alphaTab.collections.DoubleList
import alphaTab.model.Score
import alphaTab.rendering.RenderFinishedEventArgs
import alphaTab.rendering.ScoreRenderer
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Picture
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import no.brasscribe.play.score.AlphaTabMusicXml
import java.io.OutputStream

/**
 * PDFs laid out on the phone from alphaTab's engraving, for a score with no PDF from the computer (made on the phone,
 * or changed on it): the player's part, every part, and the conductor's score, on A4. The pages are drawn as lines,
 * curves and the music font's glyphs ([PictureCanvas]), never as pixels, so they print sharp. The layout is alphaTab's,
 * so it may differ from the computer's (MuseScore's).
 *
 * The notes are as the MusicXML writes them, as on the screen: each part at its written pitch, in the key it was
 * arranged in, and a doubtful note with its "?" over it. Ink on white, whatever the app's appearance.
 *
 * It runs off the main thread and never touches the score view's alphaTab.
 */
class PhonePdf(context: Context) {
    private val musicFont: Typeface = Typeface.createFromAsset(context.assets, "Bravura.otf")
    /** Under a page with a doubtful note: what its "?" means (design/system.md, the uncertainty legend). */
    private val legend: String = context.getString(no.brasscribe.play.R.string.export_marks_note)

    /** One engraved system (or the title block): its drawing, and its size in alphaTab's units. */
    class Chunk(val picture: Picture, val width: Float, val height: Float, val firstBar: Int, val lastBar: Int)

    /** A part or the full score, engraved: its chunks top to bottom, to be drawn at [scale] points per unit; [marked]: a note has a "?". */
    class Engraved(val name: String?, val chunks: List<Chunk>, val scale: Float, val marked: Boolean = false)

    private fun settings() = Settings().apply {
        core.engine = ENGINE
        core.enableLazyLoading = false
        display.layoutMode = LayoutMode.Page
        player.playerMode = PlayerMode.Disabled
        player.enableCursor = false
        // Ink on white: alphaTab's bar numbers are red by default.
        val ink = alphaTab.model.Color(0.0, 0.0, 0.0, 255.0)
        val lines = alphaTab.model.Color(64.0, 64.0, 64.0, 255.0)
        display.resources.apply {
            mainGlyphColor = ink; secondaryGlyphColor = ink; scoreInfoColor = ink
            staffLineColor = lines; barSeparatorColor = ink; barNumberColor = lines
        }
    }

    /** Reads [musicXml] once, for every part and the full score. */
    fun parse(musicXml: ByteArray): Score {
        register(musicFont)
        return AlphaTabMusicXml.parse(musicXml, settings())
    }

    /** Engraves [tracks] of [score] (one for a part, every one for the conductor) as wide as an A4 page between its margins at [scale]. */
    fun engrave(score: Score, tracks: List<Int>, name: String?, scale: Float): Engraved {
        register(musicFont)
        val renderer = ScoreRenderer(settings())
        renderer.width = (CONTENT_W / scale).toDouble()
        val laidOut = ArrayList<RenderFinishedEventArgs>()
        val drawn = HashMap<String, Chunk>()
        var failed: Throwable? = null
        renderer.partialLayoutFinished.on { laidOut += it }
        renderer.partialRenderFinished.on { e ->
            (e.renderResult as? Picture)?.let { drawn[e.id] = Chunk(it, e.width.toFloat(), e.height.toFloat(), e.firstMasterBarIndex.toInt(), e.lastMasterBarIndex.toInt()) }
        }
        renderer.error.on { failed = it }
        try {
            renderer.renderScore(score, DoubleList(*tracks.map { it.toDouble() }.toDoubleArray()), null)
            for (a in laidOut) if (a.id !in drawn) renderer.renderResult(a.id)
        } finally {
            renderer.destroy()
        }
        failed?.let { throw IllegalStateException("alphaTab could not lay out the pages", it) }
        return Engraved(name, dropCredit(laidOut.mapNotNull { drawn[it.id] }), scale, marked(score, tracks))
    }

    /** A PDF being written: parts are added one after another, each from a new page, and their drawings let go. */
    inner class Document(private val pages: PdfPages = newPages()) : java.io.Closeable {
        var pageCount = 0
            private set

        fun add(part: Engraved) {
            val laid = paginate(part)
            laid.forEachIndexed { i, page ->
                pages.page(PAGE_W, PAGE_H) { c -> drawPage(c, part, page, i, laid.size) }
                pageCount++
            }
        }

        fun writeTo(out: OutputStream) = pages.writeTo(out)
        override fun close() = pages.close()
    }

    private val header = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 9f; color = android.graphics.Color.rgb(64, 64, 64) }

    private fun drawPage(c: Canvas, part: Engraved, page: List<Pair<Chunk, Float>>, index: Int, of: Int) {
        c.drawColor(android.graphics.Color.WHITE)
        // The part's name over its pages, and the page of the part after the first: the parts of a band's print are told apart.
        val name = part.name
        if (name != null) c.drawText(name, MARGIN.toFloat(), MARGIN - 12f, header.apply { textAlign = Paint.Align.LEFT })
        if (of > 1) c.drawText("${index + 1}/$of", PAGE_W - MARGIN.toFloat(), MARGIN - 12f, header.apply { textAlign = Paint.Align.RIGHT })
        if (part.marked) c.drawText(legend, MARGIN.toFloat(), PAGE_H - MARGIN + 20f, header.apply { textAlign = Paint.Align.LEFT })
        var y = MARGIN.toFloat()
        for ((chunk, s) in page) {
            c.save()
            c.translate(MARGIN.toFloat(), y)
            c.scale(s, s)
            c.drawPicture(chunk.picture)
            c.restore()
            y += chunk.height * s
        }
    }

    companion object {
        /** A4 in PDF points, and its margins (12.7 mm). */
        const val PAGE_W = 595
        const val PAGE_H = 842
        const val MARGIN = 36
        const val CONTENT_W = PAGE_W - 2f * MARGIN
        const val CONTENT_H = PAGE_H - 2f * MARGIN

        /** A part: its staff about 7 mm high, as players read on the stand. */
        const val PART_SCALE = 0.62f
        /** The conductor's score: smaller, so a band's staves fit a page; a system taller than the page is drawn smaller still. */
        const val SCORE_SCALE = 0.40f

        /** alphaTab's name for the canvas the PDFs are drawn with. */
        const val ENGINE = "brasscribe-pdf"

        /** Where the pages are written: Android's PDF document. The JVM tests, which have none, give their own. */
        @Volatile
        @androidx.annotation.VisibleForTesting
        internal var newPages: () -> PdfPages = { AndroidPdfPages() }

        private var registered = false

        @Synchronized
        private fun register(musicFont: Typeface) {
            if (registered) return
            Environment.renderEngines.set(ENGINE, RenderEngineFactory(false) { PictureCanvas(musicFont) })
            registered = true
        }

        /** Whether a note of [tracks] has a "?" (or a boxed one) over it. */
        internal fun marked(score: Score, tracks: List<Int>): Boolean = tracks.any { t ->
            score.tracks[t].staves.any { st -> st.bars.any { bar -> bar.voices.any { v -> v.beats.any { b ->
                b.text?.trim().let { it == "?" || it == no.brasscribe.play.score.BOXED_QUESTION }
            } } } }
        }

        /** alphaTab may sign the engraving with a chunk of its own under the music: the PDF is the music (alphaTab is credited in About). */
        internal fun dropCredit(chunks: List<Chunk>): List<Chunk> =
            if (chunks.size > 1 && chunks.last().lastBar < 0) chunks.dropLast(1) else chunks

        /**
         * The pages of [part]: whole chunks (the title, then systems) top to bottom, a new page when the next does not fit.
         * A chunk wider or taller than the page is drawn smaller, to fit; each comes with the scale it is drawn at.
         */
        internal fun paginate(part: Engraved): List<List<Pair<Chunk, Float>>> {
            val pages = ArrayList<List<Pair<Chunk, Float>>>()
            var page = ArrayList<Pair<Chunk, Float>>()
            var used = 0f
            for (chunk in part.chunks) {
                val fit = minOf(part.scale, CONTENT_W / chunk.width.coerceAtLeast(1f), CONTENT_H / chunk.height.coerceAtLeast(1f))
                val h = chunk.height * fit
                if (page.isNotEmpty() && used + h > CONTENT_H) { pages += page; page = ArrayList(); used = 0f }
                page += chunk to fit
                used += h
            }
            if (page.isNotEmpty()) pages += page
            return pages
        }
    }
}

/** The pages of a PDF being written. */
interface PdfPages : java.io.Closeable {
    fun page(width: Int, height: Int, draw: (Canvas) -> Unit)
    fun writeTo(out: OutputStream)
}

/** Android's PDF document (Skia's PDF writer): the drawing stays vector, and the fonts are embedded as used. */
class AndroidPdfPages : PdfPages {
    private val doc = PdfDocument()
    private var number = 1

    override fun page(width: Int, height: Int, draw: (Canvas) -> Unit) {
        val p = doc.startPage(PdfDocument.PageInfo.Builder(width, height, number++).create())
        try { draw(p.canvas) } finally { doc.finishPage(p) }
    }

    override fun writeTo(out: OutputStream) = doc.writeTo(out)
    override fun close() = doc.close()
}
