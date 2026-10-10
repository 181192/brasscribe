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
