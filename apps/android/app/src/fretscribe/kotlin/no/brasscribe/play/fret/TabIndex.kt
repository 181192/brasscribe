package no.brasscribe.play.fret

import org.w3c.dom.Element
import org.w3c.dom.ProcessingInstruction
import javax.xml.parsers.DocumentBuilderFactory

/**
 * One written piece of a note in tab.musicxml. A note is one piece, or several tied ones when it crosses a
 * beat or a bar line, and it is written on each staff of a pair.
 */
data class TabPiece(
    /** The note's place in the tab's `notes` (the `<?fretted-note N?>` instruction). */
    val note: Int,
    /** 0 is the first staff of the part. */
    val staff: Int,
    /** The measure, counted from 0 in the order they are written (a pickup is the first). */
    val bar: Int,
    /** The measure's printed number: 0 for a pickup. */
    val barNumber: String,
    /** From the start of the measure, in [TabIndex.TICKS] to a quarter note. */
    val onset: Int,
    /** Sounding MIDI pitch. */
    val pitch: Int,
    val step: String,
    val alter: Int,
    /** 1 is the top line; null on a notation staff. */
    val string: Int?,
    val fret: Int?,
    /** Where the note starts: the piece no tie comes into. */
    val first: Boolean,
    /** The `<?fretted-confidence?>` of a doubtful note, on its first piece. */
    val confidence: Double?,
    /** The beat it starts in, 1 the first, by the time signature in force there; in a pickup, the beat of the full bar it leads into. */
    val beat: Int = 1,
    /** In a pickup: a first measure shorter than its time signature. */
    val pickup: Boolean = false,
)

/** One written measure: its printed number, how long it is and how its beats are counted. */
data class TabMeasure(
    /** The printed number: 0 for a pickup. */
    val number: String,
    /** In [TabIndex.TICKS] to a quarter note: a full bar of its time signature, or what a pickup holds. */
    val length: Int,
    /** Beats in a full bar of the time signature in force. */
    val beats: Int,
    /** One beat, in [TabIndex.TICKS]. */
    val beatTicks: Int,
    /** A first measure shorter than its time signature. */
    val pickup: Boolean = false,
) {
    /** The beat that starts at or before [tick] of this measure, 1 the first; in a pickup, the beat of the full bar it leads into. */
    fun beatAt(tick: Int): Int = ((tick.coerceAtLeast(0) + if (pickup) beats * beatTicks - length else 0) / beatTicks + 1).coerceIn(1, beats)
}

/** The boxed "! D1" above a column: the names of the notes that have no place there. */
data class TabNoPlace(val staff: Int, val bar: Int, val barNumber: String, val onset: Int, val names: List<String>, val beat: Int = 1, val pickup: Boolean = false)

/**
 * tab.musicxml as the tab view needs it: which drawn note is which note of the tab's data. The core says
 * so in a processing instruction on every note piece (core/target-fretted/README.md, The note index);
 * alphaTab drops those when it reads the file, so they are read here, with each piece's measure, start
 * and string, and a drawn note is found again by those.
 */
class TabIndex(
    val pieces: List<TabPiece>,
    val noPlace: List<TabNoPlace>,
    /** Measures written. */
    val bars: Int,
    val staves: Int,
    /** The staff with the TAB clef; null in the notation layout. */
    val tabStaff: Int?,
    /** The words over the first measure: "Drop D: D A D G B E, Capo 3". */
    val header: String?,
    /** Quarter notes a minute, as the first measure says; null when it does not. */
    val tempo: Int? = null,
    /** The measures in the order they are written; [bars] of them. */
    val measures: List<TabMeasure> = emptyList(),
) {
    private val byNote = pieces.groupBy { it.note }

    /** The pieces of [note] in the order they are written; empty for a note the document does not have. */
    fun of(note: Int): List<TabPiece> = byNote[note].orEmpty()

    /** The staff the marks stand on: the tab staff, or the notation staff when it is the only one. */
    val markStaff: Int get() = tabStaff ?: 0

    /** The capo's fret, as the header says it; 0 without one. */
    val capo: Int get() = header?.let { CAPO.find(it)?.groupValues?.get(1)?.toIntOrNull() } ?: 0

    /** The tuning's name, as the header says it ("Drop D"). */
    val tuningName: String? get() = header?.substringBefore(':', "")?.trim()?.takeIf { it.isNotEmpty() }

    companion object {
        /** alphaTab's ticks to a quarter note: onsets are kept in them, so they compare with a beat's start. */
        const val TICKS = 960

        private val CAPO = Regex("""\bCapo (\d+)""")
        private val STEPS = mapOf("C" to 0, "D" to 2, "E" to 4, "F" to 5, "G" to 7, "A" to 9, "B" to 11)
        private val MARK_DIRECTION = Regex(
            """<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>\s*(?:\?|![^<]*)</words>(?:(?!</direction>).)*?</direction>\s*""",
            RegexOption.DOT_MATCHES_ALL,
        )
        private val NOTE_COLOUR = Regex("""(<note(?:head)?\b[^>]*?)\s+color="#[0-9A-Fa-f]{6,8}"""")

        /**
         * [musicXml] without the "?" and "!" words and without the doubt colour: the view draws its marks from
         * the data, and would otherwise show them twice. For the renderer only; the file itself is kept as it is.
         */
        fun withoutMarks(musicXml: String): String = NOTE_COLOUR.replace(MARK_DIRECTION.replace(musicXml, ""), "$1")

        private val WORDS_DIRECTION = Regex(
            """<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>([^<]*)</words>(?:(?!</direction>).)*?</direction>\s*""",
            RegexOption.DOT_MATCHES_ALL,
        )

        /**
         * [musicXml] for the renderer: without its marks ([withoutMarks]) and without the words over the first
         * measure (the tuning, the strings and the capo). The screen's header says those, and on the page a mark
         * over the first notes would stand on them.
         */
        fun forRenderer(musicXml: String, header: String?): String {
            val bare = withoutMarks(musicXml)
            if (header == null) return bare
            var done = false
            return WORDS_DIRECTION.replace(bare) { m -> if (!done && m.groupValues[1].trim() == header) { done = true; "" } else m.value }
        }

        private fun Element.child(name: String): Element? {
            var n = firstChild
            while (n != null) {
                if (n is Element && n.tagName == name) return n
                n = n.nextSibling
            }
            return null
        }

        private fun Element.children(name: String): List<Element> {
            val out = ArrayList<Element>()
            var n = firstChild
            while (n != null) {
                if (n is Element && n.tagName == name) out += n
                n = n.nextSibling
            }
            return out
        }

        private fun Element.path(vararg names: String): Element? = names.fold(this as Element?) { e, n -> e?.child(n) }
        private fun Element.text(vararg names: String): String? = path(*names)?.textContent?.trim()
        private fun Element.int(vararg names: String): Int? = text(*names)?.toIntOrNull()

        private fun Element.instruction(target: String): String? {
            var n = firstChild
            while (n != null) {
                if (n is ProcessingInstruction && n.target == target) return n.data.trim()
                n = n.nextSibling
            }
            return null
        }

        /** How long [measure] is, in divisions: as far as its notes reach. */
        private fun lengthOf(measure: Element): Int {
            var pos = 0
            var end = 0
            var c = measure.firstChild
            while (c != null) {
                val el = c as? Element
                c = c.nextSibling
                when (el?.tagName) {
                    "backup" -> pos -= el.int("duration") ?: 0
                    "forward" -> pos += el.int("duration") ?: 0
                    "note" -> if (el.child("chord") == null && el.child("grace") == null) pos += el.int("duration") ?: 0
                }
                end = maxOf(end, pos)
            }
            return end
        }

        /** Reads the first part of [musicXml]. A document that is not MusicXML gives an empty index. */
        fun parse(musicXml: String): TabIndex {
            val factory = DocumentBuilderFactory.newInstance().apply {
                isValidating = false
                isNamespaceAware = false
                runCatching { setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false) }
                runCatching { setFeature("http://xml.org/sax/features/external-general-entities", false) }
                runCatching { setFeature("http://xml.org/sax/features/external-parameter-entities", false) }
            }
            val root = runCatching { factory.newDocumentBuilder().parse(musicXml.byteInputStream()).documentElement }.getOrNull()
            val part = root?.child("part") ?: return TabIndex(emptyList(), emptyList(), 0, 1, null, null)
            val pieces = ArrayList<TabPiece>()
            val noPlace = ArrayList<TabNoPlace>()
            var divisions = 1
            var staves = 1
            var tabStaff: Int? = null
            var header: String? = null
            var tempo: Int? = null
            var beats = 4
            var beatTicks = TICKS
            val measures = part.children("measure")
            val written = ArrayList<TabMeasure>()
            measures.forEachIndexed { bar, measure ->
                val number = measure.getAttribute("number").ifEmpty { (bar + 1).toString() }
                // The time signature and the divisions of this measure are in force from its start.
                measure.child("attributes")?.let { a ->
                    a.int("divisions")?.takeIf { it > 0 }?.let { divisions = it }
                    a.int("time", "beats")?.takeIf { it > 0 }?.let { beats = it }
                    a.int("time", "beat-type")?.takeIf { it > 0 }?.let { beatTicks = TICKS * 4 / it }
                }
                var pos = 0
                var last = 0
                fun ticks(p: Int) = p * TICKS / divisions
                // A pickup is shorter than a bar: its notes are counted in the beats of the bar they lead into.
                val length = ticks(lengthOf(measure))
                val full = beats * beatTicks
                val pickup = bar == 0 && length in 1 until full
                fun beatAt(onset: Int) = (onset + if (pickup) full - length else 0) / beatTicks + 1
                written += TabMeasure(number, if (pickup) length else full, beats, beatTicks, pickup)
                var c = measure.firstChild
                while (c != null) {
                    val el = c as? Element
                    c = c.nextSibling
                    if (el == null) continue
                    when (el.tagName) {
                        "attributes" -> {
                            el.int("divisions")?.takeIf { it > 0 }?.let { divisions = it }
                            el.int("staves")?.let { staves = maxOf(staves, it) }
                            el.int("time", "beats")?.takeIf { it > 0 }?.let { beats = it }
                            el.int("time", "beat-type")?.takeIf { it > 0 }?.let { beatTicks = TICKS * 4 / it }
                            for (clef in el.children("clef")) if (clef.text("sign") == "TAB") {
                                tabStaff = (clef.getAttribute("number").toIntOrNull() ?: 1) - 1
                            }
                        }
                        "backup" -> pos -= el.int("duration") ?: 0
                        "forward" -> pos += el.int("duration") ?: 0
                        "direction" -> {
                            val staff = (el.int("staff") ?: 1) - 1
                            for (type in el.children("direction-type")) for (words in type.children("words")) {
                                val text = words.textContent.trim()
                                when {
                                    text == "?" -> Unit
                                    text.startsWith("!") && words.getAttribute("enclosure") == "rectangle" ->
                                        noPlace += TabNoPlace(staff, bar, number, ticks(pos), text.removePrefix("!").trim().split(' ').filter { it.isNotEmpty() },
                                            beatAt(ticks(pos)), pickup)
                                    header == null && bar == 0 && text.isNotEmpty() -> header = text
                                }
                            }
                            if (tempo == null && bar == 0) tempo = el.child("sound")?.getAttribute("tempo")?.toDoubleOrNull()?.let { Math.round(it).toInt() }
                        }
                        "note" -> {
                            val chord = el.child("chord") != null
                            val grace = el.child("grace") != null
                            val onset = if (chord) last else pos
                            if (!chord && !grace) { last = pos; pos += el.int("duration") ?: 0 }
                            val index = el.instruction("fretted-note")?.toIntOrNull() ?: continue
                            val pitch = el.child("pitch") ?: continue
                            val step = pitch.text("step") ?: continue
                            val alter = Math.round(pitch.text("alter")?.toDoubleOrNull() ?: 0.0).toInt()
                            val octave = pitch.int("octave") ?: continue
                            val technical = el.path("notations", "technical")
                            pieces += TabPiece(
                                note = index, staff = (el.int("staff") ?: 1) - 1, bar = bar, barNumber = number, onset = ticks(onset),
                                pitch = 12 * (octave + 1) + (STEPS[step] ?: 0) + alter, step = step, alter = alter,
                                string = technical?.int("string"), fret = technical?.int("fret"),
                                first = el.children("tie").none { it.getAttribute("type") == "stop" },
                                confidence = el.instruction("fretted-confidence")?.toDoubleOrNull(),
                                beat = beatAt(ticks(onset)), pickup = pickup,
                            )
                        }
                    }
                }
            }
            return TabIndex(pieces, noPlace, measures.size, staves, tabStaff, header, tempo, written)
        }
    }
}
