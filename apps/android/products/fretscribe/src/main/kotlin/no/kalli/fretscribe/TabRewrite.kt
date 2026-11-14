package no.kalli.fretscribe

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import no.kalli.scribe.core.frettedTabJson
import no.kalli.scribe.engine.FrettedInstrument
import no.kalli.scribe.engine.TabLayout
import no.kalli.scribe.tab.TabIndex

/**
 * A tab written again on the phone for another tuning or capo, by the same core that wrote it on the computer
 * (`target-fretted` through the core's bindings): the page's own notes go in, with their pitches, starts, lengths and
 * doubt, a string and a fret for each come out, and the page is written anew. Nothing is asked of the computer.
 *
 * - Another tuning, or a capo that **keeps the sound**: the same pitches, on the strings and frets that suit them now.
 * - A capo that **keeps the shapes**: every note stays on its string and fret, counted from the capo, so the song
 *   sounds as much higher (or lower) as the capo was moved.
 */
object TabRewrite {
    /** The core counts a quarter note in 24 ticks; the page's index in [TabIndex.TICKS]. */
    private const val CORE_TICKS = 24

    private val NAME = Regex("""^([A-G])([#b♯♭]?)(-?\d+)$""")
    private val STEPS = mapOf('C' to 0, 'D' to 2, 'E' to 4, 'F' to 5, 'G' to 7, 'A' to 9, 'B' to 11)

    /** The MIDI pitch of a note named as the page names one with no place ("D1", "F#2"); null for another word. */
    fun pitchOf(name: String): Int? {
        val m = NAME.find(name.trim()) ?: return null
        val alter = when (m.groupValues[2]) { "#", "♯" -> 1; "b", "♭" -> -1; else -> 0 }
        return 12 * (m.groupValues[3].toInt() + 1) + STEPS.getValue(m.groupValues[1][0]) + alter
    }

    /** The instrument and tuning the page is written for, by its strings without the capo; null when it is none the app knows. */
    fun written(musicXml: String, index: TabIndex): Pair<FrettedInstrument, String>? {
        val open = SongFacts.openStrings(musicXml).map { it - index.capo }
        return SongFacts.OPEN_STRINGS.entries.firstOrNull { it.value == open }?.key?.let(FrettedInstrument::ofPreset)
    }

    private class Written(val pitch: Int, val start: Int, val dur: Int, val confidence: Double, val string: Int?)

    private val SOURCE = Regex("""<\?fretted-source\s+([^?]*)\?>\s*""")

    /**
     * The notes a page written here was written from, kept in the page itself (`<?fretted-source p,s,d,c;…?>`: pitch,
     * start, length and confidence of each): a tuning or a capo that leaves a note without a place does not lose the
     * note, and the next one asks for it again as it was. Null on a page the computer wrote.
     */
    private fun source(musicXml: String): List<Written>? = SOURCE.find(musicXml)?.groupValues?.get(1)?.trim()?.split(';')?.mapNotNull { n ->
        val f = n.split(',')
        if (f.size != 4) null else Written(f[0].toIntOrNull() ?: return@mapNotNull null, f[1].toIntOrNull() ?: return@mapNotNull null,
            f[2].toIntOrNull() ?: return@mapNotNull null, f[3].toDoubleOrNull() ?: return@mapNotNull null, null)
    }?.takeIf { it.isNotEmpty() }

    private fun withSource(musicXml: String, notes: List<Written>): String {
        val kept = "<?fretted-source " + notes.joinToString(";") { "${it.pitch},${it.start},${it.dur},${it.confidence}" } + "?>\n"
        val bare = SOURCE.replace(musicXml, "")
        val end = bare.lastIndexOf("</score-partwise>")
        return if (end < 0) bare else bare.substring(0, end) + kept + bare.substring(end)
    }

    /** The page was written on this phone: what the computer said of the song's notes, tuning and capo is not about this page. */
    fun rewritten(musicXml: String): Boolean = musicXml.contains("<?fretted-source")

    /** The core that writes a tab is in this build of the app. */
    val available: Boolean by lazy {
        try { frettedTabJson("{"); true } catch (e: LinkageError) { false } catch (e: Exception) { e !is java.lang.reflect.InvocationTargetException || e.cause !is LinkageError }
    }

    /** The notes of the page: what it was written from when it says so, else what it writes, and by name the ones with no place. */
    private fun notes(musicXml: String, index: TabIndex): List<Written> {
        val starts = IntArray(index.measures.size + 1).also { s -> index.measures.forEachIndexed { i, m -> s[i + 1] = s[i] + m.length } }
        // The core counts from the first downbeat: a pickup's notes come before it.
        val lead = index.measures.firstOrNull()?.takeIf { it.pickup }?.length ?: 0
        fun ticks(page: Int) = Math.floorDiv(page * CORE_TICKS, TabIndex.TICKS)
        val written = ArrayList<Written>()
        index.pieces.filter { it.staff == index.markStaff && it.bar < index.measures.size }.groupBy { it.note }.values.forEach { pieces ->
            val first = pieces.firstOrNull { it.first } ?: pieces.first()
            val start = starts[first.bar] + first.onset
            val end = pieces.maxOf { starts[it.bar] + it.onset + it.length }
            written += Written(first.pitch, ticks(start - lead), ticks(end - start).coerceAtLeast(1), pieces.firstNotNullOfOrNull { it.confidence } ?: 1.0, first.string)
        }
        val from = source(musicXml)
        if (from != null) {
            // Each note of the source with the string the page has it on, when the page has it.
            val placed = written.groupBy { it.start to it.pitch }.mapValues { it.value.toMutableList() }
            return from.map { n -> Written(n.pitch, n.start, n.dur, n.confidence, placed[n.start to n.pitch]?.removeFirstOrNull()?.string) }
        }
        // A note with no place is only named on the computer's page ("! D1"): it is asked for again, a beat long.
        index.noPlace.filter { it.staff == index.markStaff && it.bar < index.measures.size }.forEach { n ->
            n.names.mapNotNull(::pitchOf).filter { it in 0..127 }.forEach { pitch ->
                written += Written(pitch, ticks(starts[n.bar] + n.onset - lead), ticks(index.measures[n.bar].beatTicks).coerceAtLeast(1), 1.0, null)
            }
        }
        return written.sortedWith(compareBy<Written> { it.start }.thenBy { it.pitch })
    }

    /**
     * The core's request that writes the page [musicXml] (read as [index]) again for [kind] in [tuning] with a capo at
     * [capo], in [layout], under [title]. With [keepShapes] every note is asked for on the string it is on, as much
     * higher as the capo moves from where it is on the page.
     */
    fun request(title: String, musicXml: String, index: TabIndex, kind: FrettedInstrument, tuning: String, capo: Int, layout: TabLayout?, keepShapes: Boolean = false): String =
        request(title, musicXml, index, kind, tuning, capo, layout, asked(musicXml, index, capo, keepShapes), keepShapes)

    private fun asked(musicXml: String, index: TabIndex, capo: Int, keepShapes: Boolean): List<Written> {
        val moved = if (keepShapes) capo - index.capo else 0
        return notes(musicXml, index).map { Written(it.pitch + moved, it.start, it.dur, it.confidence, it.string) }
    }

    private fun request(title: String, musicXml: String, index: TabIndex, kind: FrettedInstrument, tuning: String, capo: Int, layout: TabLayout?, notes: List<Written>, keepShapes: Boolean): String {
        val first = index.measures.firstOrNull()
        val fifths = Regex("""<key\b[^>]*>\s*<fifths>\s*(-?\d+)\s*</fifths>(?:\s*<mode>\s*(\w+)\s*</mode>)?""").find(musicXml)
        return buildJsonObject {
            put("title", title)
            putJsonObject("instrument") { put("preset", kind.preset(tuning)); put("capo", capo) }
            putJsonArray("notes") {
                notes.forEach { n -> addJsonObject { put("pitch", n.pitch); put("start", n.start); put("dur", n.dur); put("confidence", n.confidence) } }
            }
            if (keepShapes) putJsonObject("options") {
                putJsonArray("pins") { notes.forEachIndexed { i, n -> n.string?.let { s -> addJsonObject { put("note", i); put("string", s) } } } }
            }
            index.tempo?.let { put("tempo_bpm", it) }
            if (first != null) putJsonObject("meter") { put("beats", first.beats); put("beat_unit", 4 * TabIndex.TICKS / first.beatTicks) }
            if (fifths != null) putJsonObject("key") {
                put("fifths", fifths.groupValues[1].toInt())
                fifths.groupValues[2].takeIf { it.isNotEmpty() }?.let { put("mode", it) }
            }
            putJsonObject("tab") { put("layout", (layout ?: TabLayout.TAB).id ?: "tab") }
        }.toString()
    }

    /**
     * The page [musicXml] written again for [kind] in [tuning] with a capo at [capo] (see [request]), with the notes it
     * was written from kept in it. The core's library must be loaded; throws what the core refuses.
     */
    fun rewrite(title: String, musicXml: String, index: TabIndex, kind: FrettedInstrument, tuning: String, capo: Int, layout: TabLayout?, keepShapes: Boolean = false): String {
        val notes = asked(musicXml, index, capo, keepShapes)
        return withSource(write(request(title, musicXml, index, kind, tuning, capo, layout, notes, keepShapes)), notes)
    }

    /** The page the core writes for [request] (the core's library must be loaded); throws what the core refuses. */
    fun write(request: String): String = Json.parseToJsonElement(frettedTabJson(request)).jsonObject.getValue("musicxml").jsonPrimitive.content
}
