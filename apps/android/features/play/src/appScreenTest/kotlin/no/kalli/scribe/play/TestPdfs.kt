package no.kalli.scribe.play

import java.io.File

/**
 * A PDF reader for the tests, in [Pages.readPdf]'s place while a test runs: the JVM tests have no working PdfRenderer,
 * and the same flow tests on a device read the same files. It reads the invented PDFs of the tests (a page tree's
 * "/Count", or pages named one by one) and nothing else: a file with "/Encrypt" is locked, one cut short (no "%%EOF")
 * or with no page is damaged. In src/appScreenTest, which the JVM and the device runs both compile.
 */
object TestPdfs {
    private val count = Regex("/Count (\\d+)")
    private val page = Regex("/Type ?/Page[ >]")

    val reader: (File) -> PdfRead = { file ->
        val text = file.readBytes().toString(Charsets.ISO_8859_1)
        val pages = count.findAll(text).maxOfOrNull { it.groupValues[1].toInt() } ?: page.findAll(text).count()
        when {
            "/Encrypt" in text -> PdfRead.Locked
            "%%EOF" !in text || pages == 0 -> PdfRead.Damaged
            else -> PdfRead.Pages(pages)
        }
    }

}
