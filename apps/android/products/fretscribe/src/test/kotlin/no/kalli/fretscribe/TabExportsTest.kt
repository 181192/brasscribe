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

    @Test
    fun theGuitarProFileReadsBackWithEveryNoteOnItsStringAndFret() {
        val gp = exports.guitarPro(marks)
        // A Guitar Pro 7 file is a zip with the score inside.
        assertEquals("PK", String(gp, 0, 2))
        // Every file in it is whole, by its own checksum (alphaTab writes checksums other programs refuse; the app sets them right).
        val files = HashMap<String, ByteArray>()
        java.util.zip.ZipInputStream(gp.inputStream()).use { zip -> generateSequence { zip.nextEntry }.forEach { files[it.name] = zip.readBytes() } }
        assertEquals("7.0", files["VERSION"]?.decodeToString())
        assertTrue("${files.keys}", files["Content/score.gpif"]?.decodeToString()?.startsWith("<?xml") == true)
        val back = ScoreLoader.loadScoreFromBytes(Uint8Array(gp.asUByteArray()), Settings())
        val page = AlphaTabMusicXml.parse(marks.toByteArray(), Settings())
        val written = fretted(page)
        assertEquals(TabIndex.parse(marks).pieces.count { it.first && it.staff == 0 }, written.size)
        assertEquals(written, fretted(back))
        assertEquals(page.masterBars.length.toInt(), back.masterBars.length.toInt())
        fun tuning(score: Score) = score.tracks[0].staves[0].stringTuning.tunings.let { t -> (0 until t.length.toInt()).map { t[it] } }
        assertEquals(tuning(page), tuning(back))
        assertEquals(4, tuning(back).size)
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
    }

    @Test
    fun theFilesAreNamedAfterTheSongAndTheTextOnesAreTheComputers() = runBlocking {
        val engine = FixtureEngineApi(FixtureSource { name -> fixtures.resolve("bass-line/$name").takeIf { it.isFile }?.readBytes() })
        val xml = fixture("bass-line/tab.musicxml")
        val outputs = setOf("tab.txt", "tab-instructions.en.txt", "tab-instructions.nb.txt")
        suspend fun build(format: TabShareFormat, lang: Lang = Lang.EN, suffix: String = "playing instructions") =
            exports.build(format, "Bass: line?", xml, "job", outputs, engine, lang, "legend", suffix)
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
        assertEquals("tab.musicxml", exports.build(TabShareFormat.MUSICXML, "??", xml, null, emptySet(), null, Lang.EN, "legend", "x").name)
    }
}
