package no.brasscribe.play.export

/**
 * Joins PDFs into one, page after page, each page as it was drawn (nothing is rasterised): every player's part
 * printed as one job. It reads what the engine writes (MuseScore, through Qt): a PDF with a classic cross-reference
 * table, without object streams, encryption or later updates appended. For anything else it gives null, and the
 * caller keeps the files apart.
 *
 * Each file's objects are copied as they are, with their numbers moved past those of the files before it, and each
 * file's own page tree goes under one new page tree, so what a page takes from its file's tree (its size, its
 * resources) stays.
 */
object PdfJoin {
    fun join(pdfs: List<ByteArray>): ByteArray? {
        if (pdfs.isEmpty()) return null
        val docs = pdfs.map { parse(it) ?: return null }
        val out = java.io.ByteArrayOutputStream()
        fun write(s: String) = out.write(s.toByteArray(Charsets.ISO_8859_1))
        write("%PDF-1.4\n%âãÏÓ\n")
        val offsets = HashMap<Int, Int>()
        val treeNumber = docs.sumOf { it.size } + 1
        val catalogNumber = treeNumber + 1
        val roots = ArrayList<Int>()
        var base = 0
        for (doc in docs) {
            fun moved(text: String) = REF.replace(text) { m -> "${m.groupValues[1].toInt() + base} ${m.groupValues[2]} R" }
            for ((number, obj) in doc.objects.toSortedMap()) {
                // The file's catalog is replaced by the joined file's.
                if (number == doc.catalog) continue
                var head = moved(obj.head)
                // The file's page tree hangs from the joined one.
                if (number == doc.pageTree) head = head.replaceFirst("<<", "<< /Parent $treeNumber 0 R")
                offsets[number + base] = out.size()
                write("${number + base} ${obj.generation} obj\n")
                write(head.trim())
                obj.stream?.let { data -> write("\nstream\n"); out.write(data); write("\nendstream") }
                write("\nendobj\n")
            }
            roots += doc.pageTree + base
            base += doc.size
        }
        offsets[treeNumber] = out.size()
        write("$treeNumber 0 obj\n<< /Type /Pages /Kids [${roots.joinToString(" ") { "$it 0 R" }}] /Count ${docs.sumOf { it.pageCount }} >>\nendobj\n")
        offsets[catalogNumber] = out.size()
        write("$catalogNumber 0 obj\n<< /Type /Catalog /Pages $treeNumber 0 R >>\nendobj\n")
        val size = catalogNumber + 1
        val xref = out.size()
        // Each entry is 20 bytes; numbers not used are free.
        write("xref\n0 $size\n0000000000 65535 f \n")
        for (n in 1 until size) write(offsets[n]?.let { "%010d 00000 n \n".format(it) } ?: "0000000000 65535 f \n")
        write("trailer\n<< /Size $size /Root $catalogNumber 0 R >>\nstartxref\n$xref\n%%EOF\n")
        return out.toByteArray()
    }

    /** The number of pages of [pdf], as its page tree says; null when it is not a PDF [join] reads. */
    fun pageCount(pdf: ByteArray): Int? = parse(pdf)?.pageCount

    /** One object: everything but its stream, and the stream's bytes as they are. */
    private class Obj(val generation: Int, val head: String, val stream: ByteArray?)

    /** A file read: its objects by number, its catalog, the root of its page tree, its pages, and the numbers it uses. */
    private class Doc(val objects: Map<Int, Obj>, val catalog: Int, val pageTree: Int, val pageCount: Int, val size: Int)

    private val REF = Regex("""(\d+)\s+(\d+)\s+R\b""")
    private val HEADER = Regex("""(\d+)\s+(\d+)\s+obj\b""")

    private fun parse(bytes: ByteArray): Doc? = runCatching { read(bytes) }.getOrNull()

    private fun read(bytes: ByteArray): Doc? {
        // One character per byte: offsets in the text are offsets in the file.
        val text = String(bytes, Charsets.ISO_8859_1)
        if (!text.startsWith("%PDF-")) return null
        // Object streams and cross-reference streams (PDF 1.5) are not read here.
        if ("/ObjStm" in text || "/XRefStm" in text) return null
        val start = Regex("""startxref\s+(\d+)\s+%%EOF\s*$""").find(text, maxOf(0, text.length - 1024))?.groupValues?.get(1)?.toInt() ?: return null
        if (!text.startsWith("xref", start)) return null
        val trailerAt = text.indexOf("trailer", start).takeIf { it > 0 } ?: return null
        val trailer = text.substring(trailerAt, dictEnd(text, text.indexOf("<<", trailerAt)) ?: return null)
        // An update appended later, or encryption: not read here.
        if ("/Prev" in trailer || "/Encrypt" in trailer) return null
        val size = Regex("""/Size\s+(\d+)""").find(trailer)?.groupValues?.get(1)?.toInt() ?: return null
        val catalog = Regex("""/Root\s+(\d+)\s+\d+\s+R""").find(trailer)?.groupValues?.get(1)?.toInt() ?: return null
        // The table: sections of "first count", then "offset generation n|f" for each.
        val inUse = HashMap<Int, Int>()
        val words = text.substring(start + 4, trailerAt).trim().split(Regex("""\s+"""))
        var i = 0
        while (i + 1 < words.size) {
            var number = words[i].toInt()
            val count = words[i + 1].toInt()
            i += 2
            repeat(count) {
                if (words[i + 2] == "n" && number > 0) inUse[number] = words[i].toInt()
                i += 3
                number++
            }
        }
        val bodies = HashMap<Int, Pair<Int, Int>>()
        for ((number, offset) in inUse) {
            val head = HEADER.find(text, offset)?.takeIf { it.range.first == offset && it.groupValues[1].toInt() == number } ?: return null
            bodies[number] = head.groupValues[2].toInt() to head.range.last + 1
        }
        /** A plain number object's value: a stream's length is often one. */
        fun number(n: Int): Int? {
            val from = bodies[n]?.second ?: return null
            return text.substring(from, text.indexOf("endobj", from).takeIf { it >= 0 } ?: return null).trim().toIntOrNull()
        }
        val objects = HashMap<Int, Obj>()
        for ((number, body) in bodies) {
            val (generation, from) = body
            val at = skipSpace(text, from)
            // A stream's bytes may hold anything, "endobj" too: the stream is found after its dictionary, by its length.
            val dict = if (text.startsWith("<<", at)) dictEnd(text, at) ?: return null else null
            val streamAt = dict?.let { skipSpace(text, it) }?.takeIf { text.startsWith("stream", it) }
            if (streamAt == null) {
                val end = text.indexOf("endobj", dict ?: at).takeIf { it >= 0 } ?: return null
                objects[number] = Obj(generation, text.substring(from, end), null)
                continue
            }
            val head = text.substring(from, dict)
            val lengthOf = Regex("""/Length\s+(\d+)(?:\s+\d+\s+R)?""").find(head) ?: return null
            val length = if (lengthOf.value.endsWith("R")) number(lengthOf.groupValues[1].toInt()) ?: return null else lengthOf.groupValues[1].toInt()
            // "stream", then CR LF or LF.
            var dataStart = streamAt + "stream".length
            if (text.startsWith("\r\n", dataStart)) dataStart += 2 else if (text.startsWith("\n", dataStart)) dataStart += 1 else return null
            if (length < 0 || dataStart + length > bytes.size) return null
            if (!text.startsWith("endstream", skipSpace(text, dataStart + length))) return null
            objects[number] = Obj(generation, head, bytes.copyOfRange(dataStart, dataStart + length))
        }
        val pageTree = Regex("""/Pages\s+(\d+)\s+\d+\s+R""").find(objects[catalog]?.head ?: return null)?.groupValues?.get(1)?.toInt() ?: return null
        val tree = objects[pageTree]?.head ?: return null
        if ("/Parent" in tree || !tree.trimStart().startsWith("<<")) return null
        val count = Regex("""/Count\s+(\d+)""").find(tree)?.groupValues?.get(1)?.toInt() ?: return null
        return Doc(objects, catalog, pageTree, count, maxOf(size, (objects.keys.maxOrNull() ?: 0) + 1))
    }

    private fun skipSpace(text: String, from: Int): Int {
        var i = from
        while (i < text.length && text[i] in " \t\r\n\u000C\u0000") i++
        return i
    }

    /** The index just past the dictionary that opens at [open] ("<<"), past nested dictionaries and strings; null if it never closes. */
    private fun dictEnd(text: String, open: Int): Int? {
        if (open < 0 || !text.startsWith("<<", open)) return null
        var depth = 0
        var i = open
        while (i < text.length) {
            when {
                text.startsWith("<<", i) -> { depth++; i += 2 }
                text.startsWith(">>", i) -> { depth--; i += 2; if (depth == 0) return i }
                text[i] == '(' -> {
                    // A literal string: balanced parentheses, and a backslash escapes the next byte.
                    var nest = 0
                    while (i < text.length) {
                        when (text[i]) {
                            '\\' -> i++
                            '(' -> nest++
                            ')' -> if (--nest == 0) break
                        }
                        i++
                    }
                    i++
                }
                text[i] == '<' -> i = (text.indexOf('>', i).takeIf { it >= 0 } ?: return null) + 1
                text[i] == '%' -> while (i < text.length && text[i] != '\n' && text[i] != '\r') i++
                else -> i++
            }
        }
        return null
    }
}
