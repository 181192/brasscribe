package no.brasscribe.play

import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.export.ExportFile
import no.brasscribe.play.export.ExportFormat
import no.brasscribe.play.export.Exporter
import no.brasscribe.play.export.PdfJoin
import no.brasscribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Print with Every part sends one print job, every player's part one after another, not one print dialog per player
 * (some 25 for a full band). One file prints as it is; files that can't be joined still print, one job each.
 */
@RunWith(AndroidJUnit4::class)
class PrintEveryPartTest : ScreenTest() {
    /** A small PDF as the engine writes them: [pages] pages drawing [mark]. */
    private fun pdf(name: String, mark: String, pages: Int): ExportFile {
        val objects = ArrayList<String>()
        val kids = (1..pages).map { p ->
            val content = "BT /F1 12 Tf 72 720 Td ($mark page $p) Tj ET\n"
            objects += "<< /Length ${content.length} >>\nstream\n${content}endstream"
            objects += "<< /Type /Page /Parent 2 0 R /Contents ${objects.size + 2} 0 R >>"
            objects.size + 2
        }
        val all = listOf("<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [${kids.joinToString(" ") { "$it 0 R" }}] /Count $pages /MediaBox [0 0 595 842] >>") + objects
        val out = StringBuilder("%PDF-1.4\n")
        val offsets = all.mapIndexed { i, body -> out.length.also { out.append("${i + 1} 0 obj\n$body\nendobj\n") } }
        val xref = out.length
        out.append("xref\n0 ${all.size + 1}\n0000000000 65535 f \n")
        offsets.forEach { out.append("%010d 00000 n \n".format(it)) }
        out.append("trailer\n<< /Size ${all.size + 1} /Root 1 0 R >>\nstartxref\n$xref\n%%EOF\n")
        val f = File(rule.activity.cacheDir, "print-test/$name.pdf").apply { parentFile!!.mkdirs(); writeBytes(out.toString().toByteArray(Charsets.ISO_8859_1)) }
        return ExportFile(f, ExportFormat.PDF)
    }

    /** The jobs [files] make: each job's name and its file's pages. */
    private fun jobs(files: List<ExportFile>, full: Boolean = false): List<Pair<String, Int?>> {
        val exporter = Exporter(rule.activity, container.core)
        if (full) exporter.writeJoined = { _, _ -> throw java.io.IOException("ENOSPC (No space left on device)") }
        val jobs = kotlinx.coroutines.runBlocking { exporter.printJobs(files, "Abide - With Me") }
        return jobs.map { (name, file) -> name to PdfJoin.pageCount(file.readBytes()) }
    }

    @Test
    fun everyPartIsOnePrintJob() {
        val parts = listOf(pdf("Old Hundredth - Solo Cornet", "Solo Cornet", 2), pdf("Old Hundredth - Repiano Cornet", "Repiano", 1),
            pdf("Old Hundredth - Flugelhorn", "Flugelhorn", 3))
        // Named by the score's title, whole, also when it has " - " in it.
        assertEquals(listOf("Abide - With Me" to 6), jobs(parts))
    }

    @Test
    fun oneFileIsPrintedAsItIs() {
        assertEquals(listOf("Old Hundredth - Solo Cornet" to 2), jobs(listOf(pdf("Old Hundredth - Solo Cornet", "Solo Cornet", 2))))
    }

    @Test
    fun filesThatCantBeJoinedStillPrintOneJobEach() {
        val good = pdf("Old Hundredth - Solo Cornet", "Solo Cornet", 1)
        val broken = File(rule.activity.cacheDir, "print-test/Old Hundredth - Euphonium.pdf").apply { writeText("not a PDF") }
        val files = listOf(good, ExportFile(broken, ExportFormat.PDF))
        assertEquals(listOf("Old Hundredth - Solo Cornet" to 1, "Old Hundredth - Euphonium" to null), jobs(files))
    }

    @Test
    fun aPhoneTooFullForTheJoinedFilePrintsOneJobEach() {
        val parts = listOf(pdf("Old Hundredth - Solo Cornet", "Solo Cornet", 2), pdf("Old Hundredth - Flugelhorn", "Flugelhorn", 1))
        assertEquals(listOf("Old Hundredth - Solo Cornet" to 2, "Old Hundredth - Flugelhorn" to 1), jobs(parts, full = true))
    }
}
