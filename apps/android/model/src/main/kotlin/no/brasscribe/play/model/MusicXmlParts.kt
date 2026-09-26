package no.brasscribe.play.model

/**
 * The parts of a partwise MusicXML score: their names in score order, and one part as a score of its
 * own (for "My part" when no part file exists, and after a note was changed on the phone).
 */
object MusicXmlParts {
    private val scorePart = Regex("""<score-part\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</score-part>""", RegexOption.DOT_MATCHES_ALL)
    private val partName = Regex("""<part-name\b[^>]*>([^<]*)</part-name>""")
    private val groups = Regex("""<part-group\b[^>]*/>|<part-group\b.*?</part-group>""", RegexOption.DOT_MATCHES_ALL)

    fun names(xml: String): List<String> = scorePart.findAll(xml).map { m ->
        partName.find(m.groupValues[2])?.groupValues?.get(1)?.let(::unescape)?.replace(' ', ' ')?.trim().orEmpty()
    }.toList()

    /** The score with only part [index] (0-based) left; the brackets between parts go too. */
    fun single(xml: String, index: Int): String {
        val ids = scorePart.findAll(xml).map { it.groupValues[1] }.toList()
        require(index in ids.indices) { "no part $index" }
        val keep = ids[index]
        var out = scorePart.replace(xml) { m -> if (m.groupValues[1] == keep) m.value else "" }
        out = groups.replace(out, "")
        for (id in ids) if (id != keep) {
            out = Regex("""<part\s+id="${Regex.escape(id)}"\s*>.*?</part>""", RegexOption.DOT_MATCHES_ALL).replace(out, "")
        }
        return out
    }

    private fun unescape(s: String) = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&apos;", "'")
}
