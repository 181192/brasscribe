package no.brasscribe.play.export

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/** Every part as one PDF: the files are joined page after page, each page's drawing as it was. */
class PdfJoinTest {
    /**
     * A small PDF as the engine writes them (classic cross-reference table): [pages] pages under one page tree that
     * holds the page size, each page drawing [mark], and stream lengths in objects of their own when [lengthApart].
     */
    private fun pdf(mark: String, pages: Int, lengthApart: Boolean = false): ByteArray {
        val objects = ArrayList<String>()
        fun add(body: String): Int { objects += body; return objects.size }
        val catalog = add("")
        val tree = add("")
        val kids = (1..pages).map { p ->
            val content = "BT /F1 12 Tf 72 720 Td ($mark page $p) Tj ET\n% endobj inside a stream\n"
            val stream = if (lengthApart) {
                val length = add("")
                val s = add("<< /Length $length 0 R >>\nstream\n${content}endstream")
                objects[length - 1] = "${content.length}"
                s
            } else add("<< /Length ${content.length} >>\nstream\n${content}endstream")
            add("<< /Type /Page /Parent $tree 0 R /Contents $stream 0 R >>")
        }
        objects[catalog - 1] = "<< /Type /Catalog /Pages $tree 0 R >>"
        objects[tree - 1] = "<< /Type /Pages /Kids [${kids.joinToString(" ") { "$it 0 R" }}] /Count $pages /MediaBox [0 0 595 842] " +
            "/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"
        val out = StringBuilder("%PDF-1.4\n")
        val offsets = objects.mapIndexed { i, body -> out.length.also { out.append("${i + 1} 0 obj\n$body\nendobj\n") } }
        val xref = out.length
        out.append("xref\n0 ${objects.size + 1}\n0000000000 65535 f \n")
        offsets.forEach { out.append("%010d 00000 n \n".format(it)) }
        out.append("trailer\n<< /Size ${objects.size + 1} /Root $catalog 0 R >>\nstartxref\n$xref\n%%EOF\n")
        return out.toString().toByteArray(Charsets.ISO_8859_1)
    }

    private fun text(pdf: ByteArray) = String(pdf, Charsets.ISO_8859_1)

    @Test
    fun theFilesAreJoinedPageAfterPageAsTheyWere() {
        val a = pdf("Solo Cornet", 2)
        val b = pdf("Repiano Cornet", 1, lengthApart = true)
        val c = pdf("Flugelhorn", 3)
        val joined = PdfJoin.join(listOf(a, b, c))
        assertNotNull(joined)
        joined!!
        assertEquals(6, PdfJoin.pageCount(joined))
        val t = text(joined)
        // Every page's drawing is there, in order, byte for byte.
        val order = listOf("Solo Cornet page 1", "Solo Cornet page 2", "Repiano Cornet page 1", "Flugelhorn page 1", "Flugelhorn page 2", "Flugelhorn page 3")
        assertEquals(order, order.sortedBy { t.indexOf(it) })
        assertEquals(order.size, order.count { it in t })
        // Each file's page tree, with the size and fonts its pages take from it, hangs from the joined one.
        val root = Regex("""(\d+) 0 obj\n<< /Type /Pages /Kids""").find(t)!!.groupValues[1]
        assertEquals(3, Regex("""<< /Parent $root 0 R /Type /Pages""").findAll(t).count())
        assertEquals(3, Regex("""/MediaBox \[0 0 595 842]""").findAll(t).count())
        // The joined file reads again, and joins again.
        assertEquals(12, PdfJoin.pageCount(PdfJoin.join(listOf(joined, joined))!!))
    }

    @Test
    fun theCrossReferencesPointAtTheirObjects() {
        val joined = PdfJoin.join(listOf(pdf("A", 1), pdf("B", 2, lengthApart = true)))!!
        val t = text(joined)
        val xref = Regex("""startxref\s+(\d+)""").find(t)!!.groupValues[1].toInt()
        val entries = Regex("""(\d{10}) (\d{5}) ([nf]) ?\r?\n""").findAll(t.substring(xref)).toList()
        var used = 0
        entries.forEachIndexed { number, e ->
            if (e.groupValues[3] != "n") return@forEachIndexed
            used++
            assertEquals("object $number", "$number ${e.groupValues[2].toInt()} obj", t.substring(e.groupValues[1].toInt()).substringBefore('\n'))
        }
        assertEquals(t.substring(xref).substringBefore("trailer").lines().count { it.endsWith(" n ") }, used)
    }

    @Test
    fun oneFileJoinsToItsOwnPages() {
        val joined = PdfJoin.join(listOf(pdf("Euphonium", 2)))!!
        assertEquals(2, PdfJoin.pageCount(joined))
    }

    @Test
    fun whatItDoesNotReadIsNotJoined() {
        val ok = pdf("Solo Cornet", 1)
        assertNull(PdfJoin.join(emptyList()))
        assertNull(PdfJoin.join(listOf(ok, "not a PDF".toByteArray())))
        // A file with an update appended, encrypted, or with object streams (PDF 1.5).
        assertNull(PdfJoin.join(listOf(ok, text(ok).replace("/Size", "/Prev 9 /Size").toByteArray(Charsets.ISO_8859_1))))
        assertNull(PdfJoin.join(listOf(ok, text(ok).replace("/Size", "/Encrypt 9 0 R /Size").toByteArray(Charsets.ISO_8859_1))))
        assertNull(PdfJoin.join(listOf(ok, text(ok).replace("/Type /Catalog", "/Type /Catalog /X /ObjStm").toByteArray(Charsets.ISO_8859_1))))
        // Cut short: the cross-reference table is gone.
        assertNull(PdfJoin.join(listOf(ok, ok.copyOf(ok.size / 2))))
        // A stream longer than the file says.
        val length = Regex("""/Length (\d+)""").find(text(ok))!!
        val longer = text(ok).replaceRange(length.groups[1]!!.range, (length.groupValues[1].toInt() + 100_000).toString())
        assertNull(PdfJoin.join(listOf(ok, longer.toByteArray(Charsets.ISO_8859_1))))
    }
}
