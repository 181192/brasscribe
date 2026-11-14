package no.kalli.fretscribe

import alphaTab.Settings
import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.model.Score
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import no.kalli.scribe.engine.FixtureEngineApi
import no.kalli.scribe.engine.FixtureSource
import no.kalli.scribe.model.Lang
import no.kalli.scribe.play.export.JvmPdfPages
import no.kalli.scribe.score.AlphaTabMusicXml
import no.kalli.scribe.score.export.PdfJoin
import no.kalli.scribe.score.export.PhonePdf
import no.kalli.scribe.tab.TabIndex
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The files of Share or print for a tab ([TabExports]), on the fixtures (apps/fixtures/bass-line and bass-line-marks):
 * the Guitar Pro file reads back with every note on its string and fret, the MIDI has every note, the phone's PDF has
 * the tab and its marks on a page, the text files are the computer's, and each says when it can't be had.
 */
@RunWith(AndroidJUnit4::class)
class TabExportsTest {
    private val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    private val fixtures = File(System.getProperty("scribe.sounds")!!).parentFile!!.resolve("apps/fixtures")
    private fun fixture(name: String) = fixtures.resolve(name).readText()
    private val exports = TabExports(context)
    private val marks = fixture("bass-line-marks/tab.musicxml")

    @Before
    fun pages() { PhonePdf.newPages = { JvmPdfPages() } }

    @After
    fun clean() { File(context.cacheDir, "exports").deleteRecursively() }

    /** Every note alphaTab reads on the tab staff: its string (1 the lowest, as alphaTab counts) and fret, in order; tied-to notes left out. */
    private fun fretted(score: Score): List<Pair<Int, Int>> {
        val out = ArrayList<Pair<Int, Int>>()
        for (staff in score.tracks[0].staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) for (note in beat.notes) {
            if (!note.isTieDestination) out += note.string.toInt() to note.fret.toInt()
        }
        return out
    }

    /** Every file in the zip [bytes], read through [java.util.zip.ZipInputStream], which checks each one's checksum. */
    private fun unzipChecked(bytes: ByteArray): Map<String, ByteArray> {
        val files = HashMap<String, ByteArray>()
        java.util.zip.ZipInputStream(bytes.inputStream()).use { zip -> generateSequence { zip.nextEntry }.forEach { files[it.name] = zip.readBytes() } }
        return files
    }

    @Test
    fun theGuitarProFileReadsBackWithEveryNoteOnItsStringAndFret() {
        // A four-string bass with marked notes, a six-string guitar and a four-string ukulele.
        for ((song, strings) in listOf("bass-line-marks" to 4, "guitar-line" to 6, "ukulele-line" to 4)) {
            val xml = fixture("$song/tab.musicxml")
            val gp = exports.guitarPro(xml)
            // A Guitar Pro 7 file is a zip with the score inside.
            assertEquals(song, "PK", String(gp, 0, 2))
            // Every file in it is whole, by its own checksum (alphaTab writes checksums other programs refuse; the app sets them right).
            val files = unzipChecked(gp)
            assertEquals(song, "7.0", files["VERSION"]?.decodeToString())
            assertTrue("$song: ${files.keys}", files["Content/score.gpif"]?.decodeToString()?.startsWith("<?xml") == true)
            val back = ScoreLoader.loadScoreFromBytes(Uint8Array(gp.asUByteArray()), Settings())
            val page = AlphaTabMusicXml.parse(xml.toByteArray(), Settings())
            val written = fretted(page)
            assertEquals(song, TabIndex.parse(xml).pieces.count { it.first && it.staff == 0 }, written.size)
            assertEquals(song, written, fretted(back))
            assertEquals(song, page.masterBars.length.toInt(), back.masterBars.length.toInt())
            fun tuning(score: Score) = score.tracks[0].staves[0].stringTuning.tunings.let { t -> (0 until t.length.toInt()).map { t[it] } }
            assertEquals(song, tuning(page), tuning(back))
            assertEquals(song, strings, tuning(back).size)
        }
    }

    /**
     * What alphaTab writes itself does not pass the checksum check: what [TabExports.wholeZip] is there for. When this
     * fails, alphaTab writes whole files and the rewrite can go.
     */
    @Test
    fun alphaTabsOwnGuitarProFileFailsTheChecksums() {
        val raw = exports.alphaTabsGuitarPro(marks)
        val refused = runCatching { unzipChecked(raw) }.exceptionOrNull()
        assertTrue("alphaTab's own file passed the checksum check", refused is java.util.zip.ZipException)
        assertTrue(refused!!.message, refused.message!!.contains("CRC", ignoreCase = true))
    }

    /** A zip of two small files, stored and deflated, as [java.util.zip.ZipOutputStream] writes them. */
    private fun twoFiles(): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        java.util.zip.ZipOutputStream(out).use { zip ->
            val text = "Bar 1: E string, open.".toByteArray()
            zip.putNextEntry(java.util.zip.ZipEntry("VERSION").apply {
                method = java.util.zip.ZipEntry.STORED; size = 3; compressedSize = 3; crc = java.util.zip.CRC32().apply { update("7.0".toByteArray()) }.value
            })
            zip.write("7.0".toByteArray())
            zip.closeEntry()
            zip.putNextEntry(java.util.zip.ZipEntry("Content/score.gpif"))
            zip.write(text)
            zip.closeEntry()
        }
        return out.toByteArray()
    }

    /** The offset of the second file's entry in the zip's directory. */
    private fun secondDirectoryEntry(zip: ByteArray): Int {
        val b = java.nio.ByteBuffer.wrap(zip).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        val end = (zip.size - 22 downTo 0).first { b.getInt(it) == 0x06054b50 }
        val first = b.getInt(end + 16)
        return first + 46 + (b.getShort(first + 28).toInt() and 0xFFFF) + (b.getShort(first + 30).toInt() and 0xFFFF) + (b.getShort(first + 32).toInt() and 0xFFFF)
    }

    @Test
    fun aZipThatSaysMoreThanItHasIsRefused() {
        val good = twoFiles()
        assertEquals(setOf("VERSION", "Content/score.gpif"), unzipChecked(TabExports.wholeZip(good)).keys)
        fun patched(at: Int, value: Int, short: Boolean = false) = good.copyOf().also {
            val b = java.nio.ByteBuffer.wrap(it).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            if (short) b.putShort(at, value.toShort()) else b.putInt(at, value)
        }
        val second = secondDirectoryEntry(good)
        val end = (good.size - 22 downTo 0).first { java.nio.ByteBuffer.wrap(good).order(java.nio.ByteOrder.LITTLE_ENDIAN).getInt(it) == 0x06054b50 }
        val cases = mapOf(
            // A file that says it is 4 GB, or larger than the cap, once unpacked.
            "a size of 4 GB" to patched(second + 24, -1),
            "a size over the cap" to patched(second + 24, (TabExports.ZIP_MAX_BYTES + 1).toInt()),
            // A file whose packed bytes run past the end of the zip.
            "packed past the end" to patched(second + 20, good.size),
            // A file whose header is past the end, and a directory past the end.
            "a header past the end" to patched(second + 42, good.size + 100),
            "a directory past the end" to patched(end + 16, good.size),
            // More files than the cap.
            "too many files" to patched(end + 10, TabExports.ZIP_MAX_ENTRIES + 1, short = true),
            // A name longer than the directory.
            "a name past the directory" to patched(second + 28, 0xFFFF, short = true),
            "nothing of a zip" to "not a zip at all, only words".toByteArray(),
        )
        for ((case, zip) in cases) {
            val thrown = runCatching { TabExports.wholeZip(zip) }.exceptionOrNull()
            assertTrue("$case: $thrown", thrown is java.util.zip.ZipException)
        }
    }

    @Test
    fun theMidiFileHasEveryNote() {
        val midi = exports.midi(marks)
        assertEquals("MThd", String(midi, 0, 4))
        // A note on is 0x9n with a velocity above 0; the file has one for every note the page starts.
        val notes = TabIndex.parse(marks).pieces.count { it.first && it.staff == 0 }
        var on = 0
        for (i in 0 until midi.size - 2) if ((midi[i].toInt() and 0xF0) == 0x90 && midi[i + 1] in 20..90 && midi[i + 2] > 0) on++
        assertTrue("$on note-ons for $notes notes", on >= notes)
    }

    @Test
    fun thePhonesPdfHasTheTabWithItsNameAndItsMarksOnAPage() {
        val pages = JvmPdfPages(keep = true)
        PhonePdf.newPages = { pages }
        val out = java.io.ByteArrayOutputStream()
        exports.phonePdf(marks, "Bass line", "? marks a note Fretscribe is not sure of.", out)
        assertEquals(1, pages.pages)
        assertEquals(1, PdfJoin.pageCount(out.toByteArray()))
        val page = pages.drawn.single()
        var ink = 0
        for (y in 0 until page.height) for (x in 0 until page.width) {
            val p = page.getPixel(x, y)
            if (android.graphics.Color.red(p) < 128 && android.graphics.Color.green(p) < 128 && android.graphics.Color.blue(p) < 128) ink++
        }
        assertTrue("ink $ink", ink > 1_500)
        // The legend under the page says what the marks mean: the page has marked notes.
        var foot = 0
        for (y in page.height - 40 until page.height - 10) for (x in 0 until page.width) if (android.graphics.Color.red(page.getPixel(x, y)) < 160) foot++
        assertTrue("the legend is under the page ($foot)", foot > 50)
    }

    @Test
    fun whatTheComputerWritesSaysWhenItCannotBeHad() {
        val all = setOf("tab.musicxml", "tab.txt", "tab-instructions.en.txt")
        for (format in listOf(TabShareFormat.PDF, TabShareFormat.GUITAR_PRO, TabShareFormat.MUSICXML, TabShareFormat.MIDI)) {
            assertNull("$format is the phone's own", exports.missing(format, null, emptySet(), connected = false, Lang.EN))
        }
        for (format in listOf(TabShareFormat.TEXT, TabShareFormat.INSTRUCTIONS)) {
            assertEquals(TabShareMissing.NOT_FROM_COMPUTER, exports.missing(format, null, all, connected = true, Lang.EN))
            assertEquals(TabShareMissing.NEEDS_COMPUTER, exports.missing(format, "job", all, connected = false, Lang.EN))
            assertNull(exports.missing(format, "job", all, connected = true, Lang.EN))
            // A computer that does not say what it wrote is asked all the same.
            assertNull(exports.missing(format, "job", emptySet(), connected = true, Lang.EN))
        }
        assertEquals(TabShareMissing.NOT_MADE, exports.missing(TabShareFormat.TEXT, "job", setOf("tab.musicxml"), connected = true, Lang.EN))
        // The instructions are asked for in the app's language.
        assertEquals(TabShareMissing.NOT_MADE, exports.missing(TabShareFormat.INSTRUCTIONS, "job", all, connected = true, Lang.NB))
        // The PDF is the computer's when it wrote one and is there; else the phone's.
        assertTrue(exports.pdfFromComputer("job", setOf("tab.pdf"), connected = true))
        assertFalse(exports.pdfFromComputer("job", setOf("tab.pdf"), connected = false))
        assertFalse(exports.pdfFromComputer("job", all, connected = true))
        assertFalse(exports.pdfFromComputer(null, setOf("tab.pdf"), connected = true))
        // With notes fixed on the phone, what the computer wrote does not have the fixes: the phone's files do.
        assertFalse(exports.pdfFromComputer("job", setOf("tab.pdf"), connected = true, fixed = true))
        for (format in listOf(TabShareFormat.TEXT, TabShareFormat.INSTRUCTIONS)) {
            assertEquals(TabShareMissing.FIXED, exports.missing(format, "job", all, connected = true, Lang.EN, fixed = true))
        }
        assertNull(exports.missing(TabShareFormat.MUSICXML, "job", all, connected = true, Lang.EN, fixed = true))
    }

    @Test
    fun theFilesAreNamedAfterTheSongAndTheTextOnesAreTheComputers() = runBlocking {
        val engine = FixtureEngineApi(FixtureSource { name -> fixtures.resolve("bass-line/$name").takeIf { it.isFile }?.readBytes() })
        val xml = fixture("bass-line/tab.musicxml")
        val outputs = setOf("tab.txt", "tab-instructions.en.txt", "tab-instructions.nb.txt")
        suspend fun build(format: TabShareFormat, lang: Lang = Lang.EN, suffix: String = "playing instructions") =
            exports.build(format, "Bass: line?", xml, "job", outputs, engine, connected = true, lang, "legend", suffix)
        val text = build(TabShareFormat.TEXT)
        assertEquals("Bass line.txt", text.name)
        assertEquals(fixture("bass-line/tab.txt"), text.readText())
        val en = build(TabShareFormat.INSTRUCTIONS)
        assertEquals("Bass line playing instructions.txt", en.name)
        assertEquals(fixture("bass-line/tab-instructions.en.txt"), en.readText())
        assertEquals(fixture("bass-line/tab-instructions.nb.txt"), build(TabShareFormat.INSTRUCTIONS, Lang.NB, "spilleinstruksjoner").readText())
        assertEquals(xml, build(TabShareFormat.MUSICXML).readText())
        assertEquals("Bass line.gp", build(TabShareFormat.GUITAR_PRO).name)
        assertEquals("Bass line.mid", build(TabShareFormat.MIDI).name)
        // The computer wrote no PDF for this song: the phone lays one out.
        val pdf = build(TabShareFormat.PDF)
        assertEquals("Bass line.pdf", pdf.name)
        assertTrue((PdfJoin.pageCount(pdf.readBytes()) ?: 0) >= 1)
        // A song with no name still has a file.
        assertEquals("tab.musicxml", exports.build(TabShareFormat.MUSICXML, "??", xml, null, emptySet(), null, connected = false, Lang.EN, "legend", "x").name)
    }

    @Test
    fun thePdfIsLaidOutOnThePhoneWhenTheComputersCannotBeHad() = runBlocking {
        val xml = fixture("bass-line/tab.musicxml")
        // The computer says it wrote a PDF, but has none to give (it fails as an unreachable computer would).
        val engine = FixtureEngineApi(FixtureSource { name -> fixtures.resolve("bass-line/$name").takeIf { it.isFile }?.readBytes() })
        assertTrue(runCatching { engine.pdf("job") }.isFailure)
        val outputs = setOf(TabExports.TAB_PDF)
        for (connected in listOf(true, false)) {
            val pdf = exports.build(TabShareFormat.PDF, "Bass line", xml, "job", outputs, engine, connected, Lang.EN, "legend", "x")
            assertEquals("connected $connected", "%PDF", pdf.readBytes().decodeToString(0, 4))
            assertTrue("connected $connected", (PdfJoin.pageCount(pdf.readBytes()) ?: 0) >= 1)
        }
        // What only the computer writes is not asked of a computer that does not answer.
        for (format in listOf(TabShareFormat.TEXT, TabShareFormat.INSTRUCTIONS)) {
            val thrown = runCatching { exports.build(format, "Bass line", xml, "job", setOf("tab.txt"), engine, connected = false, Lang.EN, "legend", "x") }.exceptionOrNull()
            assertTrue("$format: $thrown", thrown is IllegalStateException)
        }
    }
}
