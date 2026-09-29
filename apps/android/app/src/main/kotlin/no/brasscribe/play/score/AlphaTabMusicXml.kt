package no.brasscribe.play.score

import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.model.Score
import org.w3c.dom.Element
import javax.xml.parsers.DocumentBuilderFactory

/**
 * What alphaTab 1.8.4's MusicXML importer gets wrong for a brass-band score, and the fixes, applied at every alphaTab
 * parse ([parse]); only alphaTab sees the changed bytes, saved and exported files keep the original. The same fixes
 * as Windows' AlphaTabMusicXml.
 *
 * - Ties: an unnumbered stop is paired with an open start by comparing the stop's written pitch with the starts'
 *   sounding pitch. In a transposing part the tie fails (the note sounds again) or joins a stale start on another
 *   note, which then holds for seconds. A note whose start comes before its stop ties to itself and the MIDI
 *   generator recurses until the stack overflows. [prepare] numbers every tie (as the arranger writes them since
 *   the ties were numbered) and puts a note's stop before its start.
 * - Trills: alphaTab plays the auxiliary two semitones above the written note, whatever the key, the
 *   accidental-mark or the transposition. [applyTrills] sets each trill's auxiliary from the MusicXML: the next
 *   letter up, its accidental from the accidental-mark, else from the key.
 */
object AlphaTabMusicXml {
    /** A trill: part and measure (0-based), onset in the measure (alphaTab ticks), its sounding key, semitones to its auxiliary. */
    data class Trill(val part: Int, val measure: Int, val onsetTicks: Int, val key: Int, val auxSemitones: Int)

    class Prepared(val musicXml: ByteArray, val trills: List<Trill>)

    /** alphaTab's parse of [musicXml] with the tie and trill fixes. */
    fun parse(musicXml: ByteArray, settings: alphaTab.Settings): Score {
        val p = prepare(musicXml)
        val score = ScoreLoader.loadScoreFromBytes(Uint8Array(p.musicXml.asUByteArray()), settings)
        applyTrills(score, p.trills)
        return score
    }

    private val PART = Regex("<part\\b.*?</part>", RegexOption.DOT_MATCHES_ALL)
    private val NOTE = Regex("<note\\b.*?</note>", RegexOption.DOT_MATCHES_ALL)
    private val TIED = Regex("<tied\\b[^>]*?/>|<tied\\b[^>]*>\\s*</tied>", RegexOption.DOT_MATCHES_ALL)
    private val TYPE = Regex("\\btype=\"(start|stop)\"")
    private val NUMBER = Regex("\\bnumber=\"([^\"]*)\"")

    fun prepare(musicXml: ByteArray): Prepared {
        var text = musicXml.toString(Charsets.UTF_8)
        val ties = text.contains("<tied")
        val trills = text.contains("<trill-mark")
        if (!ties && !trills) return Prepared(musicXml, emptyList())
        if (ties) text = PART.replace(text) { numberTies(it.value) }
        val bytes = if (ties) text.toByteArray(Charsets.UTF_8) else musicXml
        return Prepared(bytes, if (trills) findTrills(bytes) else emptyList())
    }

    /**
     * One part: a note's stop goes before its start, and every tie without a number gets one. A start takes the
     * lowest number no open tie holds, its stop the number of the open tie on the same pitch.
     */
    internal fun numberTies(part: String): String {
        val open = ArrayList<Pair<String, String>>()
        return NOTE.replace(part) { m ->
            val note = m.value
            val tied = TIED.findAll(note).toList()
            if (tied.isEmpty()) return@replace note
            val key = pitchKey(note)
            val ordered = tied.sortedBy { if (TYPE.find(it.value)?.groupValues?.get(1) == "start") 1 else 0 }
            val replaced = ordered.map { t ->
                val el = t.value
                val type = TYPE.find(el)?.groupValues?.get(1) ?: return@map el
                val number = NUMBER.find(el)?.groupValues?.get(1)
                val n: String
                if (type == "start") {
                    n = number ?: (1..1000).first { i -> open.none { it.second == i.toString() } }.toString()
                    open.removeAll { it.second == n }
                    open.add(key to n)
                } else {
                    val at = if (number != null) open.indexOfFirst { it.second == number } else open.indexOfLast { it.first == key }
                    n = number ?: if (at >= 0) open[at].second else "1"
                    if (at >= 0) open.removeAt(at)
                }
                if (number != null) el else el.replaceFirst("<tied ", "<tied number=\"$n\" ")
            }
            val sb = StringBuilder()
            var pos = 0
            tied.forEachIndexed { i, t ->
                sb.append(note, pos, t.range.first).append(replaced[i])
                pos = t.range.last + 1
            }
            sb.append(note, pos, note.length).toString()
        }
    }

    private fun field(s: String, tag: String) = Regex("<$tag>(.*?)</$tag>", RegexOption.DOT_MATCHES_ALL).find(s)?.groupValues?.get(1)?.trim() ?: ""

    private fun pitchKey(note: String): String {
        val pitch = field(note, "pitch")
        if (pitch.isNotEmpty()) {
            // an <alter>0</alter> and no <alter> are the same pitch
            val alter = field(pitch, "alter").toDoubleOrNull() ?: 0.0
            return "${field(pitch, "step")}$alter/${field(pitch, "octave")}"
        }
        val unp = field(note, "unpitched")
        return "u${field(unp, "display-step")}/${field(unp, "display-octave")}"
    }

    private val STEPS = listOf("C", "D", "E", "F", "G", "A", "B")
    private val STEP_SEMIS = intArrayOf(0, 2, 4, 5, 7, 9, 11)

    /** Alter of a letter in a key signature of [fifths]. */
    private fun keyAlter(fifths: Int, step: Int): Int {
        val i = "FCGDAEB".indexOf(STEPS[step][0])
        return when {
            fifths > 0 -> if (i < fifths) 1 else 0
            fifths < 0 -> if (6 - i < -fifths) -1 else 0
            else -> 0
        }
    }

    private fun accidentalAlter(mark: String): Int? = when (mark) {
        "sharp" -> 1; "natural" -> 0; "flat" -> -1; "double-sharp", "sharp-sharp" -> 2; "flat-flat" -> -2
        else -> null
    }

    private fun Element.child(name: String): Element? {
        var n = firstChild
        while (n != null) {
            if (n is Element && n.tagName == name) return n
            n = n.nextSibling
        }
        return null
    }

    private fun Element.path(vararg names: String): Element? = names.fold(this as Element?) { e, n -> e?.child(n) }
    private fun Element.int(vararg names: String): Int? = path(*names)?.textContent?.trim()?.toIntOrNull()

    /** Every trill-marked note of the MusicXML, in part order. */
    fun findTrills(musicXml: ByteArray): List<Trill> {
        val f = DocumentBuilderFactory.newInstance().apply {
            isValidating = false
            isNamespaceAware = false
            runCatching { setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false) }
        }
        val doc = f.newDocumentBuilder().parse(musicXml.inputStream())
        val out = ArrayList<Trill>()
        val parts = doc.documentElement.getElementsByTagName("part")
        for (pi in 0 until parts.length) {
            val part = parts.item(pi) as Element
            var divisions = 1; var fifths = 0; var transpose = 0
            val measures = part.getElementsByTagName("measure")
            for (mi in 0 until measures.length) {
                var pos = 0; var last = 0
                var c = (measures.item(mi) as Element).firstChild
                while (c != null) {
                    val el = c as? Element
                    c = c.nextSibling
                    if (el == null) continue
                    when (el.tagName) {
                        "attributes" -> {
                            el.int("divisions")?.takeIf { it > 0 }?.let { divisions = it }
                            el.int("key", "fifths")?.let { fifths = it }
                            el.child("transpose")?.let { tr -> transpose = (tr.int("chromatic") ?: 0) + 12 * (tr.int("octave-change") ?: 0) }
                        }
                        "backup" -> pos -= el.int("duration") ?: 0
                        "forward" -> pos += el.int("duration") ?: 0
                        "note" -> {
                            val chord = el.child("chord") != null
                            val grace = el.child("grace") != null
                            val onset = if (chord) last else pos
                            if (!chord && !grace) { last = pos; pos += el.int("duration") ?: 0 }
                            val p = el.child("pitch")
                            if (grace || p == null || el.path("notations", "ornaments", "trill-mark") == null) continue
                            val step = STEPS.indexOf(p.child("step")?.textContent?.trim()).coerceAtLeast(0)
                            val alter = Math.round(p.child("alter")?.textContent?.trim()?.toDoubleOrNull() ?: 0.0).toInt()
                            val octave = p.int("octave") ?: 4
                            val written = 12 * (octave + 1) + STEP_SEMIS[step] + alter
                            val auxStep = (step + 1) % 7
                            val auxOctave = octave + if (step == 6) 1 else 0
                            val mark = el.path("notations", "ornaments", "accidental-mark")?.textContent?.trim()
                            val auxAlter = mark?.let { accidentalAlter(it) } ?: keyAlter(fifths, auxStep)
                            val aux = 12 * (auxOctave + 1) + STEP_SEMIS[auxStep] + auxAlter
                            out += Trill(pi, mi, onset * 960 / divisions, written + transpose, aux - written)
                        }
                    }
                }
            }
        }
        return out
    }

    /** Sets each trilled note's auxiliary in [score] (matched by track, bar, onset and sounding key); returns how many. */
    fun applyTrills(score: Score, trills: List<Trill>): Int {
        if (trills.isEmpty()) return 0
        val byPlace = trills.associateBy({ listOf(it.part, it.measure, it.onsetTicks, it.key) }, { it.auxSemitones })
        var set = 0
        for (track in score.tracks) for (staff in track.staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) {
            for (note in beat.notes) {
                if (!note.isTrill) continue
                val key = note.realValue.toInt()
                val semis = byPlace[listOf(track.index.toInt(), bar.index.toInt(), beat.playbackStart.toInt(), key)] ?: continue
                note.trillValue = (key + semis).toDouble()
                set++
            }
        }
        return set
    }
}
