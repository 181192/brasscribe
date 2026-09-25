package no.brasscribe.play.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlin.math.floor

/*
 * Talking-score announcements: the text a screen reader speaks for one stop in the score.
 * Implements docs/accessibility/talking-score-spec.md and is checked against its conformance vectors.
 * The Rust core will provide the same function; until then this is the implementation behind CoreBridge.
 */

enum class Lang { EN, NB }

enum class PitchMode {
    @SerialName("written") WRITTEN,
    @SerialName("concert") CONCERT,
}

enum class Verbosity {
    @SerialName("brief") BRIEF,
    @SerialName("standard") STANDARD,
    @SerialName("full") FULL,
}

@Serializable
data class TsSettings(
    val verbosity: Verbosity = Verbosity.STANDARD,
    @SerialName("pitch_mode") val pitchMode: PitchMode = PitchMode.WRITTEN,
)

/** What the previous announcement left behind: decides which parts of the location are repeated. */
@Serializable
data class TsContext(
    val part: String? = null,
    val bar: Int? = null,
    @SerialName("pitch_mode") val pitchMode: PitchMode? = null,
)

@Serializable
data class TsPart(
    val name: String,
    @SerialName("name_nb") val nameNb: String? = null,
    val instrument: String? = null,
    @SerialName("instrument_nb") val instrumentNb: String? = null,
)

@Serializable
data class TsFreeRegion(
    @SerialName("start_bar") val startBar: Int,
    @SerialName("end_bar") val endBar: Int,
    @SerialName("start_s") val startS: Double,
    @SerialName("end_s") val endS: Double,
    val entering: Boolean = false,
)

@Serializable
data class TsBar(
    val number: Int,
    @SerialName("key_fifths") val keyFifths: Int? = null,
    @SerialName("tempo_bpm") val tempoBpm: Int? = null,
    @SerialName("a_tempo") val aTempo: Boolean = false,
    val rehearsal: String? = null,
    @SerialName("free_region") val freeRegion: TsFreeRegion? = null,
)

@Serializable
data class TsPos(val beat: Int, val num: Int = 0, val den: Int = 1)

@Serializable
data class TsHeldFrom(val bar: Int, val beat: Int, val num: Int = 0, val den: Int = 1)

@Serializable
data class TsTieNext(val bar: Int, val type: String, val dots: Int = 0)

@Serializable
data class TsTie(
    val start: Boolean = false,
    val stop: Boolean = false,
    val next: TsTieNext? = null,
    @SerialName("chain_beats") val chainBeats: Double? = null,
)

@Serializable
data class TsTuplet(val actual: Int, val normal: Int, val index: Int)

@Serializable
data class TsEvent(
    val kind: String,
    val pos: TsPos? = null,
    val type: String? = null,
    val dots: Int = 0,
    val tuplet: TsTuplet? = null,
    val tie: TsTie? = null,
    val written: SpelledPitch? = null,
    val concert: SpelledPitch? = null,
    val pitches: List<SpelledPitch> = emptyList(),
    val articulations: List<String> = emptyList(),
    val dynamic: String? = null,
    val confidence: Double? = null,
    val sources: List<String> = emptyList(),
    val checked: Boolean = false,
    @SerialName("time_s") val timeS: Double? = null,
    @SerialName("performed_s") val performedS: Double? = null,
    @SerialName("held_from") val heldFrom: TsHeldFrom? = null,
    val bars: Int = 1,
    val instruments: List<String> = emptyList(),
    @SerialName("instruments_nb") val instrumentsNb: List<String> = emptyList(),
)

/** One stop in the score, with everything the announcer needs around it. */
data class TsStop(
    val event: TsEvent,
    val bar: TsBar? = null,
    val part: TsPart? = null,
    /** Key of the bar when the bar does not say (the part's current key). */
    val keyFifths: Int = 0,
    val totalBars: Int? = null,
)

object Announcer {
    fun announce(stop: TsStop, context: TsContext, settings: TsSettings, lang: Lang): String {
        val w = Words(lang)
        val e = stop.event
        if (e.kind == "mode-change") return modeChange(stop, settings, w)

        val bar = stop.bar
        val partChanged = stop.part != null && stop.part.name != context.part
        val barChanged = bar != null && bar.number != context.bar
        val prefix = StringBuilder()
        bar?.freeRegion?.takeIf { it.entering }?.let { r ->
            prefix.append(w.adLibEntry(r.startBar, r.endBar, roundHalfUp(r.endS - r.startS).toInt())).append(" ")
        }
        if (bar != null && bar.aTempo && bar.tempoBpm != null) prefix.append(w.aTempo(bar.tempoBpm)).append(" ")
        if (partChanged) prefix.append(w.partName(stop.part!!)).append(". ")

        val keyFifths = bar?.keyFifths ?: stop.keyFifths
        val barPart = if (bar != null && (barChanged || partChanged)) {
            buildList {
                add(if (settings.verbosity == Verbosity.FULL && stop.totalBars != null) w.barOf(bar.number, stop.totalBars) else w.bar(bar.number))
                if (partChanged || bar.keyFifths != null && bar.keyFifths != stop.keyFifths) add(w.key(keyFifths))
                if (bar.tempoBpm != null && !bar.aTempo) add(w.tempo(bar.tempoBpm))
                bar.rehearsal?.let { add(w.rehearsal(it)) }
            }.joinToString(", ")
        } else null

        if (e.kind == "bar-rest") {
            val number = bar?.number ?: context.bar ?: 0
            return prefix.toString() + if (e.bars > 1) w.barsRest(number, number + e.bars - 1, e.bars) else "${w.bar(number)}: ${w.wholeBarRest()}"
        }

        val inFreeTime = bar?.freeRegion != null && e.timeS != null
        val position = when {
            inFreeTime -> w.timePosition(roundHalfUp(e.timeS!!).toInt())
            e.pos != null -> if (settings.verbosity == Verbosity.BRIEF) w.positionBrief(e.pos) else w.position(e.pos)
            else -> null
        }
        val location = listOfNotNull(barPart, position).joinToString(", ")
        val body = body(e, settings, keyFifths, w, bar)
        return prefix.toString() + (if (location.isEmpty()) body else "$location: $body")
    }

    private fun modeChange(stop: TsStop, settings: TsSettings, w: Words): String =
        if (settings.pitchMode == PitchMode.CONCERT) w.concertPitch()
        else w.writtenPitch(stop.part)

    private fun body(e: TsEvent, s: TsSettings, keyFifths: Int, w: Words, bar: TsBar?): String {
        val brief = s.verbosity == Verbosity.BRIEF
        val parts = mutableListOf<String>()
        when (e.kind) {
            "rest" -> return w.rest(e.type ?: "quarter", e.dots, brief)
            "held" -> {
                val p = pitchOf(e, s, keyFifths, w)
                val from = e.heldFrom
                return if (from == null) w.held(p, null, null) else {
                    val fromPos = w.positionShort(TsPos(from.beat, from.num, from.den))
                    w.held(p, if (from.bar != bar?.number) from.bar else null, fromPos)
                }
            }
            "unpitched" -> {
                val names = if (w.lang == Lang.NB && e.instrumentsNb.isNotEmpty()) e.instrumentsNb else e.instruments
                parts += w.joinAnd(names)
                parts += w.duration(e.type ?: "quarter", e.dots, brief)
            }
            "chord" -> {
                val names = e.pitches.sortedBy { it.midi }.map { w.pitch(it, keyFifths) }
                parts += w.chord(names)
                parts += w.duration(e.type ?: "quarter", e.dots, brief)
            }
            else -> {
                val p = pitchOf(e, s, keyFifths, w)
                if (brief) return "$p ${w.duration(e.type ?: "quarter", e.dots, true)}" + confidenceSuffix(e, s, w)
                parts += p
                parts += w.duration(e.type ?: "quarter", e.dots, false)
            }
        }
        e.tie?.takeIf { it.start }?.let { t ->
            if (t.chainBeats != null) parts += w.tiedChain(t.chainBeats)
            else t.next?.let { n -> parts += w.tiedTo(w.duration(n.type, n.dots, false), if (n.bar != bar?.number) n.bar else null) }
        }
        e.tuplet?.let { parts += w.tuplet(it) }
        e.articulations.forEach { parts += w.articulation(it) }
        e.dynamic?.let { parts += w.dynamic(it) }
        if (bar?.freeRegion != null && (e.performedS ?: 0.0) >= 1.0) parts += w.heldAbout(floor(e.performedS!! * 2 + 0.5) / 2)
        confidenceWords(e, s, w)?.let { parts += it }
        return parts.joinToString(", ")
    }

    private fun confidenceSuffix(e: TsEvent, s: TsSettings, w: Words): String =
        confidenceWords(e, s, w)?.let { ", $it" } ?: ""

    private fun confidenceWords(e: TsEvent, s: TsSettings, w: Words): String? {
        val c = e.confidence ?: return null
        if (e.checked) return null
        val level = when (Uncertainty.of(c)) {
            Uncertainty.CONFIDENT -> return null
            Uncertainty.UNCERTAIN -> w.uncertain()
            Uncertainty.VERY_UNCERTAIN -> w.veryUncertain()
        }
        if (s.verbosity != Verbosity.FULL) return level
        return "$level, ${w.confidencePercent(floor(c * 100 + 0.5).toInt())}, ${w.sources(e.sources)}"
    }

    private fun pitchOf(e: TsEvent, s: TsSettings, keyFifths: Int, w: Words): String {
        val written = e.written
        val concert = e.concert
        if (s.verbosity == Verbosity.FULL && written != null && concert != null) {
            return w.writtenAndSounds(w.pitch(written, keyFifths), w.pitch(concert, null))
        }
        val p = if (s.pitchMode == PitchMode.CONCERT) concert ?: written else written ?: concert
        return p?.let { w.pitch(it, if (s.pitchMode == PitchMode.CONCERT) null else keyFifths) } ?: ""
    }

    /** Short visible label of a pitch: "B♭4" in English, "B4" in bokmål (where B♮ is "H4"). */
    fun pitchLabel(p: SpelledPitch, lang: Lang): String {
        if (lang == Lang.NB) return Words(lang).pitch(p, null).replace(" ", "")
        val acc = when (p.alter) { 1 -> "♯"; -1 -> "♭"; 2 -> "𝄪"; -2 -> "𝄫"; else -> "" }
        return "${p.step}$acc${p.octave}"
    }

    /** Round half up, never banker's rounding. */
    fun roundHalfUp(x: Double): Double = floor(x + 0.5)
}

/** The word lists of both languages (talking-score spec §3–§4). */
internal class Words(val lang: Lang) {
    private val en = lang == Lang.EN

    fun pitch(p: SpelledPitch, keyFifths: Int?): String {
        if (!en) return "${nbName(p)} ${p.octave}"
        val acc = when (p.alter) {
            1 -> "-sharp"; -1 -> "-flat"; 2 -> "-double-sharp"; -2 -> "-double-flat"
            0 -> if (keyFifths != null && SpelledPitch.alteredSteps(keyFifths).containsKey(p.step)) "-natural" else ""
            else -> ""
        }
        return "${p.step}$acc ${p.octave}"
    }

    private fun nbName(p: SpelledPitch): String {
        val natural = if (p.step == "B") "H" else p.step
        return when (p.alter) {
            0 -> natural
            1 -> "${natural}iss"
            -1 -> when (p.step) {
                "E" -> "Ess"; "A" -> "Ass"; "B" -> "B"
                else -> "${p.step}ess"
            }
            2 -> "$natural dobbeltkryss"
            -2 -> "$natural dobbelt-b"
            else -> natural
        }
    }

    fun instrumentSpoken(text: String): String =
        text.replace("B♭", "B-flat").replace("E♭", "E-flat").replace("F♯", "F-sharp")

    fun duration(type: String, dots: Int, brief: Boolean): String {
        val base = if (en) {
            val t = EN_TYPES[type] ?: type
            if (brief) t.removeSuffix(" note") else t
        } else {
            val (full, short) = NB_TYPES[type] ?: (type to type)
            if (brief) short else full
        }
        return dotWord(dots)?.let { "$it $base" } ?: base
    }

    private fun dotWord(dots: Int): String? = when (dots) {
        0 -> null
        1 -> if (en) "dotted" else "punktert"
        2 -> if (en) "double-dotted" else "dobbeltpunktert"
        else -> if (en) "$dots-dotted" else "$dots-punktert"
    }

    fun rest(type: String, dots: Int, brief: Boolean): String {
        val base = if (en) "${(EN_TYPES[type] ?: type).removeSuffix(" note")} rest"
        else "${NB_REST_STEM[type] ?: type}pause"
        return dotWord(dots)?.let { "$it $base" } ?: base
    }

    fun bar(n: Int) = if (en) "bar $n" else "takt $n"
    fun barOf(n: Int, total: Int) = if (en) "bar $n of $total" else "takt $n av $total"
    fun wholeBarRest() = if (en) "rest, whole bar" else "pause hele takten"
    fun barsRest(a: Int, b: Int, n: Int) = if (en) "bars $a to $b: rest, $n bars" else "takt $a til $b: pause, $n takter"

    fun key(fifths: Int): String = when {
        fifths == 0 -> if (en) "no sharps or flats" else "ingen faste fortegn"
        fifths > 0 -> if (en) "key $fifths sharp${if (fifths == 1) "" else "s"}" else "$fifths kryss"
        else -> if (en) "key ${-fifths} flat${if (fifths == -1) "" else "s"}" else "${-fifths} b"
    }

    fun tempo(bpm: Int) = "tempo $bpm"
    fun rehearsal(mark: String) = if (en) "rehearsal $mark" else "øvingsbokstav $mark"

    fun position(p: TsPos): String = (if (en) "beat " else "slag ") + positionShort(p)

    /** Position without the word "beat": "4 and", "4-og", "3, triplet 2". */
    fun positionShort(p: TsPos): String {
        val b = p.beat
        if (p.num == 0) return "$b"
        val g = gcd(p.num, p.den)
        val num = p.num / g
        val den = p.den / g
        return when {
            num == 1 && den == 2 -> if (en) "$b and" else "$b-og"
            num == 1 && den == 4 -> if (en) "$b e" else "$b, 2. av 4"
            num == 3 && den == 4 -> if (en) "$b a" else "$b, 4. av 4"
            den == 3 -> if (en) "$b, triplet ${num + 1}" else "$b, triol ${num + 1}"
            else -> if (en) "$b plus $num/$den" else "$b pluss $num/$den"
        }
    }

    fun positionBrief(p: TsPos): String = positionShort(p)

    fun timePosition(seconds: Int): String {
        if (seconds < 60) return if (en) "at $seconds seconds" else "ved $seconds sekunder"
        val m = seconds / 60
        val s = seconds % 60
        return if (en) "at $m minute${if (m == 1) "" else "s"} $s seconds" else "ved $m minutt${if (m == 1) "" else "er"} $s sekunder"
    }

    fun adLibEntry(a: Int, b: Int, s: Int) =
        if (en) "Ad lib, free time, bars $a to $b, about $s seconds." else "Ad lib, fritt tempo, takt $a til $b, omtrent $s sekunder."

    fun aTempo(bpm: Int) = if (en) "A tempo, $bpm beats per minute." else "A tempo, $bpm slag per minutt."

    fun heldAbout(seconds: Double) = if (en) "held about ${number(seconds)} seconds" else "holdes omtrent ${number(seconds)} sekunder"

    fun number(x: Double): String {
        val s = if (x == floor(x)) x.toLong().toString() else x.toString()
        return if (en) s else s.replace('.', ',')
    }

    fun held(pitch: String, bar: Int?, pos: String?): String {
        if (pos == null) return if (en) "$pitch held" else "$pitch holdes"
        val where = if (en) listOfNotNull(bar?.let { "bar $it" }, "beat $pos").joinToString(" ")
        else listOfNotNull(bar?.let { "takt $it" }, "slag $pos").joinToString(" ")
        return if (en) "$pitch held, from $where" else "$pitch holdes, fra $where"
    }

    fun tiedTo(dur: String, bar: Int?) =
        if (en) "tied to $dur" + (bar?.let { " in bar $it" } ?: "") else "bundet til $dur" + (bar?.let { " i takt $it" } ?: "")

    fun tiedChain(beats: Double): String {
        val whole = floor(beats).toLong()
        val half = beats - whole >= 0.5
        val text = if (en) (if (half) "$whole and a half" else "$whole") else (if (half) "$whole og et halvt" else "$whole")
        return if (en) "tied, $text beats in all" else "bundet, $text slag i alt"
    }

    fun tuplet(t: TsTuplet): String = if (t.actual == 3 && t.normal == 2) {
        if (en) "triplet, ${t.index} of 3" else "triol, ${t.index} av 3"
    } else {
        if (en) "${t.actual} in the time of ${t.normal}, ${t.index} of ${t.actual}" else "${t.actual} på ${t.normal}, ${t.index} av ${t.actual}"
    }

    fun articulation(a: String): String = if (en) a else when (a) {
        "accent" -> "aksent"; "fermata" -> "fermat"
        else -> a
    }

    fun dynamic(d: String): String = DYNAMICS[d] ?: d

    fun uncertain() = if (en) "uncertain" else "usikker"
    fun veryUncertain() = if (en) "very uncertain" else "svært usikker"
    fun confidencePercent(p: Int) = if (en) "confidence $p percent" else "sikkerhet $p prosent"

    fun sources(ids: List<String>): String {
        val names = ids.map { SOURCE_NAMES[it] ?: it }
        val word = if (names.size == 1) (if (en) "source" else "kilde") else (if (en) "sources" else "kilder")
        return "$word ${joinAnd(names)}"
    }

    fun joinAnd(items: List<String>): String {
        val and = if (en) " and " else " og "
        return when (items.size) {
            0 -> ""
            1 -> items[0]
            else -> items.dropLast(1).joinToString(", ") + and + items.last()
        }
    }

    fun chord(names: List<String>) = if (en) "chord, ${names.size} notes: ${names.joinToString(", ")}" else "akkord, ${names.size} toner: ${names.joinToString(", ")}"

    fun writtenAndSounds(written: String, concert: String) =
        if (en) "written $written, sounds $concert" else "skrevet $written, klinger $concert"

    fun partName(p: TsPart) = if (en) p.name else p.nameNb ?: p.name
    fun concertPitch() = if (en) "Concert pitch" else "Klingende tone"
    fun writtenPitch(p: TsPart?): String {
        val instrument = if (en) p?.instrument?.let(::instrumentSpoken) else p?.instrumentNb ?: p?.instrument
        val head = if (en) "Written pitch" else "Skrevet tone"
        return instrument?.let { "$head, $it" } ?: head
    }

    private fun gcd(a: Int, b: Int): Int = if (b == 0) a else gcd(b, a % b)

    companion object {
        val EN_TYPES = mapOf(
            "breve" to "double whole note", "whole" to "whole note", "half" to "half note", "quarter" to "quarter note",
            "eighth" to "eighth note", "16th" to "sixteenth note", "32nd" to "thirty-second note", "64th" to "sixty-fourth note",
        )
        val NB_TYPES = mapOf(
            "breve" to ("brevis" to "brevis"), "whole" to ("helnote" to "hel"), "half" to ("halvnote" to "halv"),
            "quarter" to ("fjerdedelsnote" to "fjerdedel"), "eighth" to ("åttendedelsnote" to "åttendedel"),
            "16th" to ("sekstendedelsnote" to "sekstendedel"), "32nd" to ("trettitodelsnote" to "trettitodel"),
            "64th" to ("sekstifiredelsnote" to "sekstifiredel"),
        )
        val NB_REST_STEM = mapOf(
            "breve" to "brevis", "whole" to "hel", "half" to "halv", "quarter" to "fjerdedels", "eighth" to "åttendedels",
            "16th" to "sekstendedels", "32nd" to "trettitodels", "64th" to "sekstifiredels",
        )
        val DYNAMICS = mapOf(
            "pp" to "pianissimo", "p" to "piano", "mp" to "mezzo-piano", "mf" to "mezzo-forte", "f" to "forte", "ff" to "fortissimo",
        )
        val SOURCE_NAMES = mapOf(
            "swiftf0" to "SwiftF0", "muscriptor" to "MuScriptor", "basic-pitch" to "Basic Pitch", "mega53" to "Mega-53",
            "beat-this" to "Beat This", "solo" to "solo stem",
        )
    }
}
