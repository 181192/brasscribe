package no.brasscribe.play

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * What is sheet music: told by the file's name, by the type it came with, and where neither says, by how it starts.
 * An ordinary XML file or zip is not, and a MusicXML file with no name to go by still is.
 */
class SheetMusicTest {
    private val score = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
        <score-partwise version="4.0"><part-list/></score-partwise>""".toByteArray()
    private val otherXml = """<?xml version="1.0"?><settings><volume>3</volume></settings>""".toByteArray()
    private val wav = "RIFF".toByteArray() + ByteArray(40) + "<score-partwise>".toByteArray()

    private fun zip(vararg files: Pair<String, ByteArray>): ByteArray = ByteArrayOutputStream().also { out ->
        ZipOutputStream(out).use { z -> files.forEach { (name, bytes) -> z.putNextEntry(ZipEntry(name)); z.write(bytes); z.closeEntry() } }
    }.toByteArray()

    private val container = """<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>""".toByteArray()
    private val mxl = zip("META-INF/container.xml" to container, "score.xml" to score)

    private val unread: () -> InputStream? = { throw AssertionError("the file was read") }
    private fun sheetMusic(name: String, mime: String?, bytes: ByteArray) = SheetMusic.isSheetMusic(name, mime) { bytes.inputStream() }

    @Test
    fun byItsName() {
        assertTrue(SheetMusic.isSheetMusic("A tab.musicxml", null, unread))
        assertTrue(SheetMusic.isSheetMusic("A tab.MXL", "application/octet-stream", unread))
    }

    @Test
    fun byTheTypeItCameWith() {
        assertTrue(SheetMusic.isSheetMusic("download", "application/vnd.recordare.musicxml+xml", unread))
        assertTrue(SheetMusic.isSheetMusic("1234.bin", "application/vnd.recordare.musicxml", unread))
        assertTrue(SheetMusic.isSheetMusic("A tab.xml", "Application/vnd.recordare.musicxml+xml; charset=utf-8", unread))
    }

    @Test
    fun anXmlFileOnlyWhenItIsMusicXml() {
        assertTrue(sheetMusic("A tab.xml", "text/xml", score))
        assertTrue(sheetMusic("A tab.xml", null, byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()) + score))
        assertTrue(sheetMusic("A tab.xml", null, score.decodeToString().replace("partwise", "timewise").toByteArray()))
        assertFalse(sheetMusic("Settings.xml", "text/xml", otherXml))
        assertFalse(sheetMusic("Settings.xml", null, otherXml))
    }

    @Test
    fun withNoNameToGoBy() {
        assertTrue(sheetMusic("A tab", null, score))
        assertTrue(sheetMusic("document:1234", "application/octet-stream", score))
        assertTrue(sheetMusic("A tab", "application/zip", mxl))
        assertTrue(sheetMusic("A tab", null, mxl))
        assertFalse(sheetMusic("Notes", null, otherXml))
    }

    @Test
    fun otherZipsAreNot() {
        assertFalse(sheetMusic("Photos.zip", "application/zip", zip("a.txt" to "score-partwise".toByteArray())))
        // A document that is a zip with XML in it, and a container of something else.
        assertFalse(sheetMusic("Letter.docx", null, zip("[Content_Types].xml" to otherXml, "word/document.xml" to otherXml)))
        assertFalse(sheetMusic("Book", null, zip("META-INF/container.xml" to """<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>""".toByteArray(), "content.opf" to otherXml)))
        assertFalse(sheetMusic("Empty", null, zip()))
    }

    /** What [open] hands out, counting the bytes that are read from it. */
    private class Counted(private val bytes: ByteArray) {
        var read = 0L
        val open: () -> InputStream? = {
            object : java.io.FilterInputStream(bytes.inputStream()) {
                override fun read(): Int = super.read().also { if (it >= 0) read++ }
                override fun read(b: ByteArray, off: Int, len: Int): Int = super.read(b, off, len).also { if (it > 0) read += it }
            }
        }
    }

    /** Any zip may be handed over: only its start is looked at, however much it would unpack to. */
    @Test
    fun aZipWithOneHugeFileIsLeftAfterItsStart() {
        // 512 MB of nothing, which is half a megabyte as a zip.
        val huge = ByteArrayOutputStream().also { out ->
            ZipOutputStream(out).use { z ->
                z.putNextEntry(ZipEntry("film.bin"))
                val block = ByteArray(1 shl 20)
                repeat(512) { z.write(block) }
                z.closeEntry()
                z.putNextEntry(ZipEntry("score.xml")); z.write(score); z.closeEntry()
            }
        }.toByteArray()
        val file = Counted(huge)
        assertFalse(SheetMusic.isSheetMusic("Film", null, file.open))
        // 4 MB of it unpacked is a few kB of the zip; all of it would be every byte.
        assertTrue("read ${file.read} of ${huge.size} bytes", file.read < 64 * 1024 && file.read < huge.size / 4)
    }

    @Test
    fun aZipWithVeryManyFilesIsLeftAfterItsFirst() {
        val many = ByteArrayOutputStream().also { out ->
            ZipOutputStream(out).use { z -> repeat(20_000) { i -> z.putNextEntry(ZipEntry("part-$i.xml")); z.closeEntry() } }
        }.toByteArray()
        val file = Counted(many)
        assertFalse(SheetMusic.isSheetMusic("Parts", null, file.open))
        assertTrue("read ${file.read} of ${many.size} bytes", file.read < 64 * 1024 && file.read < many.size / 4)
    }

    /** A real compressed MusicXML file: its type, the container, then the score among other files, and a long one. */
    @Test
    fun compressedMusicXmlWithNoNameToGoBy() {
        val long = score.decodeToString().replace("<part-list/>", "<part-list/>" + "<part><measure/></part>".repeat(100_000)).toByteArray()
        val real = zip("mimetype" to "application/vnd.recordare.musicxml".toByteArray(), "META-INF/container.xml" to container,
            "cover.png" to ByteArray(200_000) { it.toByte() }, "score.xml" to long)
        assertTrue(sheetMusic("A tab", null, real))
        assertTrue(sheetMusic("document:77", "application/octet-stream", real))
        // With no container, the first .xml outside META-INF is the score.
        assertTrue(sheetMusic("A tab", null, zip("score.xml" to long)))
        assertFalse(sheetMusic("A tab", null, zip("META-INF/other.xml" to score, "notes.xml" to otherXml)))
    }

    @Test
    fun recordingsAreNot() {
        assertFalse(sheetMusic("Riff.wav", null, wav))
        assertFalse(sheetMusic("Riff", null, wav))
        // A recording by its type is not read at all.
        assertFalse(SheetMusic.isSheetMusic("Riff", "audio/x-wav", unread))
        assertFalse(SheetMusic.isSheetMusic("Clip.xml", "video/mp4", unread))
        assertFalse(sheetMusic("Nothing", null, ByteArray(0)))
    }

    @Test
    fun aFileThatCannotBeReadIsNot() {
        assertFalse(SheetMusic.isSheetMusic("A tab.xml", null) { throw IOException("gone") })
        assertFalse(SheetMusic.isSheetMusic("A tab.xml", null) { null })
        assertFalse(sheetMusic("A tab", null, "PK".toByteArray() + byteArrayOf(3, 4) + ByteArray(20)))
    }
}
