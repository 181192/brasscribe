package no.brasscribe.play.export

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.TranscriptionResult
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.model.KotlinCoreBridge
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.MusicXmlParts
import no.brasscribe.play.screen.ScreenDevice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The PDFs the phone lays out itself (from alphaTab's engraving), on "Old Hundredth" (apps/fixtures/old-hundredth): ink
 * on white, staves of a size players read at A4, nothing past a page's edge, every part in one print job, and the
 * computer's PDF still used while nothing was changed. The PDF document itself is Android's, checked on a device
 * (PhonePdfDeviceTest); here its pages are drawn into pictures ([JvmPdfPages]).
 */
@RunWith(AndroidJUnit4::class)
class PhonePdfTest {
    private val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    private val xml = checkNotNull(ScreenDevice.fixture("old-hundredth/brass-band.musicxml")).decodeToString()
    private val names = MusicXmlParts.names(xml)

    @Before
    fun pages() { PhonePdf.newPages = { JvmPdfPages() } }

    /** The staff's height in mm on the page: the first five rows of a drawn system that a line crosses most of. */
    private fun staffMm(chunk: PhonePdf.Chunk, scale: Float): Double {
        val bmp = Bitmap.createBitmap(chunk.width.toInt(), chunk.height.toInt(), Bitmap.Config.ARGB_8888)
        Canvas(bmp).apply { drawColor(Color.WHITE); drawPicture(chunk.picture) }
        val rows = (0 until bmp.height).filter { y -> (0 until bmp.width).count { x -> Color.red(bmp.getPixel(x, y)) < 160 } > bmp.width / 2 }
        // Neighbouring rows are one line drawn over two pixels.
        val lines = rows.fold(mutableListOf<Int>()) { acc, y -> if (acc.isEmpty() || y - acc.last() > 1) acc += y else acc[acc.size - 1] = y; acc }
        assertTrue("staff lines found: $lines", lines.size >= 5)
        return (lines[4] - lines[0]) * scale * 25.4 / 72
    }

    @Test
    fun aPartIsInkOnWhiteWithAStaffPlayersReadAtA4() {
        val pdf = PhonePdf(context)
        val score = pdf.parse(xml.toByteArray())
        val solo = names.indexOf("Solo Cornet")
        val part = pdf.engrave(score, listOf(solo), "Solo Cornet", PhonePdf.PART_SCALE)
        // The title block, then the systems with every bar of the hymn.
        assertEquals(-1, part.chunks.first().lastBar)
        assertEquals(score.masterBars.length.toInt() - 1, part.chunks.last().lastBar)
        val mm = staffMm(part.chunks[1], PhonePdf.PART_SCALE)
        // A printed part's staff is about 7 mm (6 to 8 mm in engraving practice).
        assertTrue("staff $mm mm", mm in 6.0..8.5)

        val pages = JvmPdfPages(keep = true)
        pdf.Document(pages).use { it.add(part) }
        assertEquals(1, pages.pages)
        val page = pages.drawn.single()
        var ink = 0
        var coloured = 0
        for (y in 0 until page.height) for (x in 0 until page.width) {
            val p = page.getPixel(x, y)
            val (r, g, b) = Triple(Color.red(p), Color.green(p), Color.blue(p))
            if (r < 128 && g < 128 && b < 128) ink++
            if (maxOf(r, g, b) - minOf(r, g, b) > 60) coloured++
        }
        assertTrue("ink $ink", ink > 2_000)
        // A part with a "?" says under its pages what it means; one with none (the soprano's rests) does not.
        assertTrue(PhonePdf.marked(score, (0 until score.tracks.length.toInt()).toList()))
        assertFalse(PhonePdf.marked(score, listOf(names.indexOf("Soprano Cornet"))))
        // Ink on white: no red bar numbers, no tinted notes (the "?" is a word over the note, not a colour).
        assertEquals(0, coloured)
    }

    @Test
    fun aVeryUncertainNoteKeepsItsBoxedMark() {
        // The computer writes a very uncertain note's "?" in a rectangle; alphaTab alone would print it as a plain "?".
        val boxed = xml.replaceFirst("<words>?</words>", "<words enclosure=\"rectangle\">?</words>")
        val score = PhonePdf(context).parse(boxed.toByteArray())
        val texts = (0 until score.tracks.length.toInt()).flatMap { t ->
            score.tracks[t].staves.flatMap { st -> st.bars.flatMap { b -> b.voices.flatMap { v -> v.beats.mapNotNull { it.text?.trim() } } } }
        }
        assertEquals(1, texts.count { it == no.brasscribe.play.score.BOXED_QUESTION })
        assertEquals(3, texts.count { it == "?" })
    }

    @Test
    fun aSystemAPageTallIsDrawnUnderTheTitleNotOnAPageOfItsOwn() {
        fun chunk(h: Float, bars: Int) = PhonePdf.Chunk(android.graphics.Picture(), 800f, h, if (bars < 0) -1 else 0, bars)
        val title = chunk(100f, -1)
        // At 0.62 a unit the system is 1,240 pt, taller than the page (770 pt between its margins).
        val tall = chunk(2_000f, 3)
        val pages = PhonePdf.paginate(PhonePdf.Engraved("Solo Cornet", listOf(title, tall, chunk(100f, 7)), PhonePdf.PART_SCALE))
        assertEquals(listOf(title, tall), pages.first().map { it.first })
        assertTrue(pages.first().sumOf { (c, s) -> (c.height * s).toDouble() } <= PhonePdf.CONTENT_H + 0.01)
        // Under a tall title, a system that would be drawn below half the size it fits a page at goes to the next page.
        val tallTitle = chunk(1_000f, -1)
        val apart = PhonePdf.paginate(PhonePdf.Engraved(null, listOf(tallTitle, tall), PhonePdf.PART_SCALE))
        assertEquals(2, apart.size)
    }

    @Test
    fun theConductorsScoreFitsItsPagesAndNoPartRunsPastAnEdge() {
        val pdf = PhonePdf(context)
        val score = pdf.parse(repeated(xml, 4).toByteArray())
        val full = pdf.engrave(score, (0 until score.tracks.length.toInt()).toList(), null, PhonePdf.SCORE_SCALE)
        val parts = listOf(full) + (0 until 3).map { pdf.engrave(score, listOf(it), names[it], PhonePdf.PART_SCALE) }
        for (p in parts) for (page in PhonePdf.paginate(p)) {
            assertTrue(page.sumOf { (c, s) -> (c.height * s).toDouble() } <= PhonePdf.CONTENT_H + 0.01)
            for ((c, s) in page) assertTrue(c.width * s <= PhonePdf.CONTENT_W + 0.01)
        }
        val system = full.chunks.first { it.lastBar >= 0 }
        val drawnAt = PhonePdf.paginate(full).flatten().first { it.first === system }.second
        val mm = staffMm(system, drawnAt)
        println("conductor: ${score.tracks.length.toInt()} staves, ${PhonePdf.paginate(full).size} pages, staff $mm mm")
        // Small, as a full score's staves are, and still readable.
        assertTrue("staff $mm mm", mm >= 3.0)
    }

    @Test
    fun aScoreMadeOrChangedOnThePhoneHasThePhonesPdfAndAnUnchangedComputerScoreKeepsItsOwn() {
        val exporter = Exporter(context, KotlinCoreBridge)
        val phone = TranscriptionResult(null, xml, Profile.SOLO, onDevice = true)
        // Brasscribe lays out its own; Fretscribe's PDFs are the computer's alone.
        assertEquals(no.brasscribe.play.Product.PHONE_PDF, exporter.available(phone, ExportFormat.PDF, midiFromScore = true))
        assertFalse(exporter.pdfFromComputer(phone))
        assertEquals(no.brasscribe.play.Product.PHONE_PDF, exporter.perPart(phone, ExportFormat.PDF))
        val computer = TranscriptionResult(null, xml, Profile.BRASS_BAND, onDevice = false, jobId = "j",
            engineOutputs = setOf("brass-band.pdf", "parts/01-Soprano Cornet.pdf"))
        assertTrue(exporter.pdfFromComputer(computer))
        val changed = computer.copy(changedOnPhone = true)
        assertFalse(exporter.pdfFromComputer(changed))
        assertEquals(no.brasscribe.play.Product.PHONE_PDF, exporter.available(changed, ExportFormat.PDF, midiFromScore = true))
        // Audio and braille are the computer's alone: after a change they are still not offered.
        assertFalse(exporter.available(changed, ExportFormat.AUDIO, midiFromScore = true))
    }

    @Test
    fun everyPartIsAFileEachAndOnePrintJob() {
        val exporter = Exporter(context, KotlinCoreBridge)
        val r = TranscriptionResult(null, xml, Profile.BRASS_BAND, onDevice = true)
        val seen = ArrayList<Pair<Int, Int>>()
        val files = runBlocking {
            exporter.buildAll(r, listOf(ExportFormat.PDF), ExportScope.EVERY_PART, 1, names, null, null, emptyList(), Lang.EN) { d, of -> seen += d to of }
        }
        assertEquals(names.size, files.size)
        assertTrue(files.all { it.file.isFile && PdfJoin.pageCount(it.file.readBytes()) == 1 })
        // Numbered in score order: two parts of one name would not share a file.
        assertEquals(names.indices.map { "%02d-".format(it + 1) }, files.map { it.file.name.take(3) })
        assertEquals((0..names.size).map { it to names.size }, seen)
        val jobs = runBlocking { exporter.printJobs(files, "Old Hundredth") }
        assertEquals(1, jobs.size)
        assertEquals(names.size, PdfJoin.pageCount(jobs.single().second.readBytes()))
        // Print after Share lays nothing out again (and so says nothing about laying it out).
        assertTrue(exporter.phonePdfsReady(r, ExportScope.EVERY_PART, 1, names))
        assertFalse(exporter.phonePdfsReady(r, ExportScope.CONDUCTOR, 1, names))
        val again = runBlocking { exporter.buildAll(r, listOf(ExportFormat.PDF), ExportScope.EVERY_PART, 1, names, null, null, emptyList(), Lang.EN) }
        assertEquals(files.map { it.file }, again.map { it.file })
    }

    /**
     * Time and memory for a full brass band (25 parts) of 96 bars, every part and the conductor's score, as Every part
     * and the score lay them out. The hymn's 18 parts with seven of them again, its 12 bars eight times over. Native
     * memory (the pictures' drawing, the PDF document's) is not counted: the heap is what the JVM sees.
     */
    @Test
    fun timeAndMemoryForAFullBand() {
        val band = repeated(moreParts(xml, 25), 8)
        val bandNames = MusicXmlParts.names(band)
        assertEquals(25, bandNames.size)
        val exporter = Exporter(context, KotlinCoreBridge)
        val r = TranscriptionResult(null, band, Profile.BRASS_BAND, onDevice = true)
        val threads = java.lang.management.ManagementFactory.getThreadMXBean() as com.sun.management.ThreadMXBean
        val runtime = Runtime.getRuntime()
        System.gc()
        val before = runtime.totalMemory() - runtime.freeMemory()
        val peak = java.util.concurrent.atomic.AtomicLong(before)
        val sampling = java.util.concurrent.atomic.AtomicBoolean(true)
        val sampler = Thread { while (sampling.get()) { peak.accumulateAndGet(runtime.totalMemory() - runtime.freeMemory(), ::maxOf); Thread.sleep(5) } }.apply { start() }
        val allocated0 = threads.getThreadAllocatedBytes(Thread.currentThread().id)
        val times = ArrayList<Long>()
        var last = System.nanoTime()
        val start = last
        val files = runBlocking {
            exporter.buildAll(r, listOf(ExportFormat.PDF), ExportScope.EVERY_PART, 1, bandNames, null, null, emptyList(), Lang.EN) { d, _ ->
                if (d > 0) { val now = System.nanoTime(); times += now - last; last = now }
            }
        }
        val partsMs = (System.nanoTime() - start) / 1_000_000
        val scoreStart = System.nanoTime()
        val score = runBlocking { exporter.buildAll(r, listOf(ExportFormat.PDF), ExportScope.CONDUCTOR, 1, bandNames, null, null, emptyList(), Lang.EN) }
        val scoreMs = (System.nanoTime() - scoreStart) / 1_000_000
        val allocated = threads.getThreadAllocatedBytes(Thread.currentThread().id) - allocated0
        sampling.set(false)
        sampler.join()
        System.gc()
        val retained = runtime.totalMemory() - runtime.freeMemory() - before
        val bars = band.split("<measure ").size - 1
        println("phone PDFs, 25 parts x ${bars / 25} bars: every part ${partsMs} ms " +
            "(a part: min ${times.min() / 1_000_000} ms, median ${times.sorted()[times.size / 2] / 1_000_000} ms, max ${times.max() / 1_000_000} ms), " +
            "conductor's score ${scoreMs} ms; heap peak ${(peak.get() - before) / 1_048_576} MB over the start (garbage included), " +
            "${retained / 1_048_576} MB kept after; allocated ${allocated / 1_048_576} MB; ${files.size} files, joined ${PdfJoin.pageCount(runBlocking { exporter.printJobs(files, "x") }.single().second.readBytes())} pages, " +
            "score ${PdfJoin.pageCount(score.single().file.readBytes())} pages")
        assertEquals(25, files.size)
        // The conductor's 25 staves: a system is drawn smaller to fit the page. Still a staff a conductor can read.
        val pdf = PhonePdf(context)
        val full = pdf.parse(band.toByteArray()).let { s -> pdf.engrave(s, (0 until s.tracks.length.toInt()).toList(), null, PhonePdf.SCORE_SCALE) }
        val system = full.chunks.first { it.lastBar >= 0 }
        val drawnAt = PhonePdf.paginate(full).flatten().first { it.first === system }.second
        val mm = staffMm(system, drawnAt)
        println("conductor's score, 25 staves: drawn at ${"%.3f".format(drawnAt)} pt a unit (${"%.3f".format(PhonePdf.SCORE_SCALE)} wanted), staff ${"%.2f".format(mm)} mm")
        assertTrue("staff $mm mm", mm >= 2.5)
        // Generous: CI machines differ. It is the measurement above that tells.
        assertTrue("every part took $partsMs ms", partsMs < 180_000)
    }

    /** The hymn's bars [times] over in every part, renumbered: a longer piece. */
    private fun repeated(xml: String, times: Int): String {
        val part = Regex("""(<part\s+id="[^"]+"\s*>)(.*?)(</part>)""", RegexOption.DOT_MATCHES_ALL)
        val measure = Regex("""<measure\b[^>]*>.*?</measure>""", RegexOption.DOT_MATCHES_ALL)
        return part.replace(xml) { m ->
            val bars = measure.findAll(m.groupValues[2]).map { it.value }.toList()
            var n = 0
            val body = (0 until times).joinToString("\n") {
                bars.joinToString("\n") { b -> n++; b.replaceFirst(Regex("""number="[^"]*""""), "number=\"$n\"") }
            }
            m.groupValues[1] + body + m.groupValues[3]
        }
    }

    /** The score with its first parts again (renamed) until it has [count]: a band's size. */
    private fun moreParts(xml: String, count: Int): String {
        val declared = Regex("""<score-part id="([^"]+)".*?</score-part>""", RegexOption.DOT_MATCHES_ALL).findAll(xml).toList()
        val parts = Regex("""<part id="([^"]+)">.*?</part>""", RegexOption.DOT_MATCHES_ALL).findAll(xml).toList()
        val extra = count - declared.size
        val newDeclared = (0 until extra).joinToString("\n") { i ->
            declared[i].value.replace("id=\"${declared[i].groupValues[1]}\"", "id=\"X$i\"").replace(Regex("<part-name>([^<]*)</part-name>"), "<part-name>$1 ($i)</part-name>")
        }
        val newParts = (0 until extra).joinToString("\n") { i -> parts[i].value.replaceFirst("id=\"${parts[i].groupValues[1]}\"", "id=\"X$i\"") }
        return xml.replace("</part-list>", "$newDeclared\n</part-list>").replace("</score-partwise>", "$newParts\n</score-partwise>")
    }
}

