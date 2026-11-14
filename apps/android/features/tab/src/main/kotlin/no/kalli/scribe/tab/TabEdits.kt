package no.kalli.scribe.tab

/** What the player has changed about one note of the tab. */
data class NoteEdit(
    /** The string and fret Fretscribe wrote, when the player moved the note to another place. */
    val was: Pair<Int, Int>? = null,
    /** The player looked at a doubtful note and kept it: it has no "?" any more. */
    val checked: Boolean = false,
    /** The note is left out of the tab. */
    val leftOut: Boolean = false,
    /** The note is a ghost note: struck muted, written as an x. */
    val ghost: Boolean = false,
) {
    val changed: Boolean get() = was != null || checked || leftOut || ghost
}

/**
 * The player's fixes to a tab, kept in the tab's own MusicXML beside the facts the core wrote there: a processing
 * instruction on each written piece of the note, after its `<?fretted-note N?>`. So a song keeps its fixes wherever its
 * file goes, every note keeps where it came from, and a fix is taken back by taking its instruction away.
 *
 * - `<?fretted-was S F?>`: the note was moved to another string; S and F are the string and fret Fretscribe wrote.
 * - `<?fretted-checked C?>` in place of `<?fretted-confidence C?>`: a doubtful note the player kept (or moved).
 * - `<?fretted-left-out?>`: the note is not played. It stays in the file, and is a rest on the page ([shown]).
 * - `<?fretted-ghost?>`: a ghost note, an x on the page ([shown]).
 *
 * The file is edited as text, a note at a time: nothing else in it is rewritten.
 */
object TabEdits {
    private const val WAS = "fretted-was"
    private const val CONFIDENCE = "fretted-confidence"
    private const val CHECKED = "fretted-checked"
    private const val LEFT_OUT = "fretted-left-out"
    private const val GHOST = "fretted-ghost"

    private val NOTE = Regex("""<note\b[^>]*>.*?</note>""", RegexOption.DOT_MATCHES_ALL)
    private val INDEX = Regex("""<\?fretted-note\s+(\d+)\s*\?>""")
    private val CHORD = Regex("""<chord\s*/>|<chord>\s*</chord>""")
    private val STRING = Regex("""(<string>\s*)(\d+)(\s*</string>)""")
    private val FRET = Regex("""(<fret>\s*)(\d+)(\s*</fret>)""")
    private val DOUBT_MARK = Regex(
        """<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>\s*\?\s*</words>(?:(?!</direction>).)*?</direction>\s*""",
        RegexOption.DOT_MATCHES_ALL,
    )
    private val NOTEHEAD = Regex("""\s*<notehead\b[^>]*>[^<]*</notehead>""")
    private val COLOURED_HEAD = Regex("""\s*<notehead\b[^>]*\bcolor="[^"]*"[^>]*>\s*normal\s*</notehead>""")
    private val COLOUR = Regex("""(<note\b[^>]*?)\s+color="[^"]*"""")

    private fun instruction(name: String) = Regex("""\s*<\?$name\b([^?]*)\?>""")
    private fun String.has(name: String) = instruction(name).containsMatchIn(this)
    private fun String.without(name: String) = instruction(name).replace(this, "")
    private fun String.noteIndex(): Int? = INDEX.find(this)?.groupValues?.get(1)?.toIntOrNull()

    /** Adds `<?name data?>` after the note's own instruction, once. */
    private fun String.with(name: String, data: String = ""): String {
        if (has(name)) return this
        val at = INDEX.find(this) ?: return this
        val indent = Regex("""\n[ \t]*$""").find(substring(0, at.range.first))?.value ?: ""
        val text = if (data.isEmpty()) "<?$name?>" else "<?$name $data?>"
        return substring(0, at.range.last + 1) + indent + text + substring(at.range.last + 1)
    }

    /** Every written piece of [note] in [musicXml], changed by [change]. */
    private fun each(musicXml: String, note: Int, change: (String) -> String): String =
        NOTE.replace(musicXml) { m -> if (m.value.noteIndex() == note) change(m.value) else m.value }

    private fun String.checked(): String = instruction(CONFIDENCE).replace(this) { it.value.replace(CONFIDENCE, CHECKED) }

    /**
     * [note] is played on [string] (1 the highest, as the file counts them) at [fret]: the same pitch at another place.
     * The place Fretscribe wrote is kept beside it; moved back there, the note is as Fretscribe wrote it. A doubtful
     * note that was moved has been looked at: it has no "?" any more.
     */
    fun place(musicXml: String, note: Int, string: Int, fret: Int): String = each(musicXml, note) { piece ->
        val s = STRING.find(piece)?.groupValues?.get(2)?.toIntOrNull()
        val f = FRET.find(piece)?.groupValues?.get(2)?.toIntOrNull()
        // (A piece on a notation staff has no place.)
        if (s == null || f == null) return@each piece.checked()
        val was = instruction(WAS).find(piece)?.groupValues?.get(1)?.trim()?.split(Regex("\\s+"))?.mapNotNull { it.toIntOrNull() }?.takeIf { it.size == 2 }
        val original = was ?: listOf(s, f)
        var out = STRING.replace(piece) { it.groupValues[1] + string + it.groupValues[3] }
        out = FRET.replace(out) { it.groupValues[1] + fret + it.groupValues[3] }
        out = out.without(WAS)
        if (original != listOf(string, fret)) out = out.with(WAS, "${original[0]} ${original[1]}")
        out.checked()
    }

    /** A doubtful [note] is kept as it is written: it has no "?" any more. */
    fun keep(musicXml: String, note: Int): String = each(musicXml, note) { it.checked() }

    /** [note] is left out of the tab (it stays in the file), or put back. */
    fun leaveOut(musicXml: String, note: Int, out: Boolean = true): String =
        each(musicXml, note) { if (out) it.with(LEFT_OUT) else it.without(LEFT_OUT) }

    /** [note] is a ghost note, or an ordinary one again. */
    fun ghost(musicXml: String, note: Int, on: Boolean): String =
        each(musicXml, note) { if (on) it.with(GHOST) else it.without(GHOST) }

    /** [note] is back as Fretscribe wrote it: at its place, with its "?", played, and no ghost. */
    fun revert(musicXml: String, note: Int): String = each(musicXml, note) { piece ->
        var out = piece
        instruction(WAS).find(piece)?.groupValues?.get(1)?.trim()?.split(Regex("\\s+"))?.mapNotNull { it.toIntOrNull() }?.takeIf { it.size == 2 }?.let { (s, f) ->
            out = STRING.replace(out) { it.groupValues[1] + s + it.groupValues[3] }
            out = FRET.replace(out) { it.groupValues[1] + f + it.groupValues[3] }
        }
        out = out.without(WAS).without(LEFT_OUT).without(GHOST)
        instruction(CHECKED).replace(out) { it.value.replace(CHECKED, CONFIDENCE) }
    }

    /** What the player changed about [note]; nothing for a note the file does not have. */
    fun of(musicXml: String, note: Int): NoteEdit {
        val pieces = NOTE.findAll(musicXml).map { it.value }.filter { it.noteIndex() == note }.toList()
        if (pieces.isEmpty()) return NoteEdit()
        val was = pieces.firstNotNullOfOrNull { p ->
            instruction(WAS).find(p)?.groupValues?.get(1)?.trim()?.split(Regex("\\s+"))?.mapNotNull { it.toIntOrNull() }?.takeIf { it.size == 2 }?.let { it[0] to it[1] }
        }
        return NoteEdit(was, pieces.any { it.has(CHECKED) }, pieces.any { it.has(LEFT_OUT) }, pieces.any { it.has(GHOST) })
    }

    /** The notes left out, by their place in the tab's notes, in the order they are written. */
    fun leftOut(musicXml: String): List<Int> =
        NOTE.findAll(musicXml).map { it.value }.filter { it.has(LEFT_OUT) }.mapNotNull { it.noteIndex() }.distinct().toList()

    /** How many notes the player has fixed in [musicXml] (moved, kept, left out or made a ghost note). */
    fun fixed(musicXml: String): Int =
        NOTE.findAll(musicXml).map { it.value }.filter { piece -> listOf(WAS, CHECKED, LEFT_OUT, GHOST).any { piece.has(it) } }
            .mapNotNull { it.noteIndex() }.distinct().count()

    /** The player has changed something in [musicXml]. */
    fun changed(musicXml: String): Boolean = listOf(WAS, CHECKED, LEFT_OUT, GHOST).any { musicXml.contains("<?$it") }

    private fun tag(piece: String, name: String): String? = Regex("""<$name\b[^>]*>.*?</$name>|<$name\b[^>]*/>""", RegexOption.DOT_MATCHES_ALL).find(piece)?.value

    /** The rest that stands where a left-out note was written: as long, in the same voice and on the same staff. Null for a grace note. */
    private fun rest(piece: String): String? {
        val duration = tag(piece, "duration") ?: return null
        val dots = Regex("""<dot\s*/>""").findAll(piece).joinToString("") { it.value }
        return "<note><rest/>" + duration + tag(piece, "voice").orEmpty() + tag(piece, "type").orEmpty() + dots +
            tag(piece, "time-modification").orEmpty() + tag(piece, "staff").orEmpty() + "</note>"
    }

    /**
     * [musicXml] as it is shown, played and shared: a note left out is a rest (or gone from its chord), a ghost note has
     * an x for a head, a doubtful note the player kept has lost its colour, and a "?" stands only over a beat that
     * still has a doubtful note. A file without fixes comes back as it is.
     */
    fun shown(musicXml: String): String {
        if (!changed(musicXml)) return musicXml
        val notes = NOTE.findAll(musicXml).toList()
        val out = StringBuilder()
        var at = 0
        var i = 0
        while (i < notes.size) {
            // A beat: a note and the notes written as its chord, with nothing but space between them.
            var last = i
            while (last + 1 < notes.size && CHORD.containsMatchIn(notes[last + 1].value) &&
                musicXml.substring(notes[last].range.last + 1, notes[last + 1].range.first).isBlank()) last++
            val beat = (i..last).map { notes[it].value }
            val stay = beat.filter { !it.has(LEFT_OUT) }
            var before = musicXml.substring(at, notes[i].range.first)
            if (stay.none { it.has(CONFIDENCE) }) {
                // The "?" over this beat is the last thing before it.
                DOUBT_MARK.findAll(before).lastOrNull()?.takeIf { before.substring(it.range.last + 1).isBlank() }?.let { before = before.removeRange(it.range) }
            }
            out.append(before)
            if (stay.isEmpty()) {
                rest(beat.first())?.let(out::append)
            } else {
                stay.forEachIndexed { n, piece ->
                    var p = piece
                    if (n == 0) p = CHORD.replace(p, "").replace(Regex("""(<note\b[^>]*>)\s*\n\s*\n"""), "$1\n")
                    if (p.has(CHECKED)) p = COLOURED_HEAD.replace(COLOUR.replace(p, "$1"), "")
                    if (p.has(GHOST) && STRING.containsMatchIn(p)) {
                        p = NOTEHEAD.replace(p, "")
                        val where = listOf("<staff>", "<beam", "<notations>", "<?fretted-note").map { p.indexOf(it) }.filter { it >= 0 }.minOrNull()
                        if (where != null) p = p.substring(0, where) + "<notehead>x</notehead>" + p.substring(where)
                    }
                    if (n > 0) out.append("\n")
                    out.append(p)
                }
            }
            at = notes[last].range.last + 1
            i = last + 1
        }
        out.append(musicXml.substring(at))
        return out.toString()
    }
}
