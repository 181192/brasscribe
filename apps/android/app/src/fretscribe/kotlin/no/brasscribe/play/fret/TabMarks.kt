package no.brasscribe.play.fret

import android.content.res.Resources
import no.brasscribe.play.R
import no.brasscribe.play.engine.Tab

/** What the tab view's numbers come from that the generated theme does not carry yet (design/fretscribe/tokens/tokens.json, `tab`). */
object TabTokens {
    /** `tab.numeral-scale`: fret numbers relative to body text. */
    const val NUMERAL_SCALE = 1.5
    /** `typography.body`: the size the numerals are relative to, in sp. */
    const val BODY_SP = 16.0
    /** `tab.mark-size-line-spaces`: the height of "?" and the boxed "!" in tab line spaces. */
    const val MARK_LINE_SPACES = 1.4f
    /** `tab.uncertain-threshold-default`: a note below this confidence gets a "?". */
    const val UNCERTAIN_THRESHOLD = 0.4
    /** `color.*.uncertain-tint`: the wash behind a doubtful numeral. High contrast has shapes only, so no wash. */
    const val UNCERTAIN_TINT_LIGHT = 0xFFFCF0DB.toInt()
    const val UNCERTAIN_TINT_DARK = 0xFF3B3325.toInt()
    /** The playback cursor's line and a repeat's brackets, in dp. */
    const val CURSOR_DP = 3f
}

/** How large the page is set: alphaTab's scale, from the size of the numerals, the system's text size, the zoom and the room there is. */
object TabSize {
    /** The narrowest page, in alphaTab's units (dp at scale 1): the tab clef, a time signature and a bar of a few notes. */
    const val MIN_PAGE_UNITS = 140.0

    /**
     * alphaTab's scale for [percent] zoom.
     * - [base] makes the numerals [TabTokens.NUMERAL_SCALE] times body text, and they follow the text size ([fontScale]).
     * - On a screen wider than it is tall ([landscape]) a larger text size does not make the page larger than two
     *   lines to the [roomDp] there is, nor smaller than at the ordinary text size ([lineUnits]: the height of a
     *   line in alphaTab's units). On a phone on its side that leaves the ordinary size:
     *   with the numerals twice as large, less than one line would be in view. The zoom is on top of it.
     * - Never larger than a page of [MIN_PAGE_UNITS] across [widthDp]: past that a bar no longer fits the width, and
     *   alphaTab presses its notes together instead of letting the page scroll sideways.
     */
    /**
     * About how tall a line of the page is with the space around it, in alphaTab's units, for an instrument of
     * [strings] strings in [layout]: the staff's line spaces, the stems or the notation staff, and the space between
     * lines. It is reckoned, not measured, so the size is known before the page is engraved.
     */
    fun lineUnits(strings: Int, layout: no.brasscribe.play.engine.TabLayout?): Double {
        val tab = 60.0 + 13.0 * (strings - 1)
        return when (layout) {
            no.brasscribe.play.engine.TabLayout.NOTATION -> 105.0
            no.brasscribe.play.engine.TabLayout.TAB_AND_NOTATION -> tab + 110.0
            else -> tab
        }
    }

    fun scale(base: Double, percent: Int, fontScale: Float, widthDp: Float, roomDp: Float, landscape: Boolean, lineUnits: Double): Double {
        val twoLines = if (landscape && lineUnits > 0) maxOf(base, roomDp / (2 * lineUnits)) else Double.MAX_VALUE
        return minOf(minOf(base * fontScale, twoLines) * percent / 100.0, widthDp / MIN_PAGE_UNITS)
    }
}

enum class MarkKind { DOUBT, NO_PLACE }

/** Why a note has no place on the instrument. */
enum class NoPlaceWhy { TOO_LOW, TOO_HIGH, OTHER }

/** One note under a mark. */
data class MarkedNote(
    val kind: MarkKind,
    /** Its place in the tab's notes; null for a "!" read from the page alone, which says no more than a name. */
    val note: Int?,
    val string: Int? = null,
    val fret: Int? = null,
    /** The pitch as it is spelled on the page; null when the page does not spell it. */
    val step: String? = null,
    val alter: Int = 0,
    /** The note as the boxed words name it ("D1"), for a note the tab staff leaves out. */
    val name: String? = null,
    val why: NoPlaceWhy = NoPlaceWhy.OTHER,
)

/** A column of the tab with a mark above it: one beat of one staff, and the notes there that the mark is for. */
data class TabColumn(
    val staff: Int,
    /** The measure, counted from 0 as written. */
    val bar: Int,
    val barNumber: String,
    /** From the start of the measure, in alphaTab's ticks. */
    val onset: Int,
    /** 1 is the first beat of the bar. */
    val beat: Int,
    val notes: List<MarkedNote>,
    /** The column is in the pickup: the notes before the first full bar. */
    val pickup: Boolean = false,
) {
    /** A column with a note that has no place shows the boxed "!"; its doubtful notes are still tinted and described. */
    val kind: MarkKind get() = if (notes.any { it.kind == MarkKind.NO_PLACE }) MarkKind.NO_PLACE else MarkKind.DOUBT
}

/**
 * The marks of a tab, in reading order, with what the status line says: [doubtful] notes marked "?" and
 * [noPlace] notes under a "!", both as they are drawn. [unplaced] counts marked notes the page has no
 * column for (a note the writer folded into another, or a "!" the page and the data disagree about):
 * they are not drawn, and not in the other two counts.
 */
class TabMarks(val columns: List<TabColumn>, val doubtful: Int, val noPlace: Int, val unplaced: Int) {
    companion object {
        /**
         * The marks from the tab's data: a "?" for every note below [threshold], a boxed "!" for every note
         * without a place. Each is tied to its column through the note index of the page ([index]).
         *
         * Without [tab] (a saved song when the computer is away) the page itself is read: the confidence it
         * carries on its doubtful notes, and its boxed words.
         */
        fun of(index: TabIndex, tab: Tab?, threshold: Double = TabTokens.UNCERTAIN_THRESHOLD): TabMarks {
            val staff = index.markStaff
            val found = LinkedHashMap<Triple<Int, Int, Int>, MutableList<MarkedNote>>()
            /** A column's measure number, beat and whether it is in the pickup. */
            val places = HashMap<Triple<Int, Int, Int>, Triple<String, Int, Boolean>>()
            var unplaced = 0
            fun add(bar: Int, number: String, onset: Int, beat: Int, pickup: Boolean, note: MarkedNote) {
                val at = Triple(staff, bar, onset)
                places[at] = Triple(number, beat, pickup)
                found.getOrPut(at) { ArrayList() } += note
            }
            fun doubt(p: TabPiece) = add(p.bar, p.barNumber, p.onset, p.beat, p.pickup, MarkedNote(MarkKind.DOUBT, p.note, p.string, p.fret, p.step, p.alter))
            /** Where a note starts on the staff with the marks. */
            fun start(note: Int): TabPiece? = index.of(note).let { all -> all.firstOrNull { it.staff == staff && it.first } ?: all.firstOrNull { it.staff == staff } }

            if (tab == null) {
                // On a notation staff a note without a place is written, and may be in doubt as well: it is under the "!" its
                // boxed words give it, not also under a "?".
                val boxed = index.noPlace.filter { it.staff == staff }
                fun underABox(p: TabPiece) = p.string == null && boxed.any { b -> b.bar == p.bar && b.onset == p.onset && b.names.any { it.startsWith(p.step) } }
                index.pieces.filter { it.staff == staff && it.confidence != null && it.confidence < threshold && !underABox(it) }.forEach(::doubt)
                for (b in index.noPlace.filter { it.staff == staff }) for (name in b.names.ifEmpty { listOf("") }) {
                    add(b.bar, b.barNumber, b.onset, b.beat, b.pickup, MarkedNote(MarkKind.NO_PLACE, null, name = name.ifEmpty { null }))
                }
            } else {
                val lowest = tab.instrument.tuning.strings.minOfOrNull { it.openPitch + tab.instrument.capo }
                val highest = tab.instrument.tuning.strings.maxOfOrNull { it.openPitch + tab.instrument.frets }
                // The boxed words of the page, one name each, in order: where the tab staff has no note to carry an index.
                val boxed = ArrayDeque(index.noPlace.filter { it.staff == staff }.flatMap { b -> b.names.ifEmpty { listOf("") }.map { b to it } })
                tab.notes.forEachIndexed { i, note ->
                    val placed = !note.outOfRange && note.position != null
                    if (!placed) {
                        val why = when {
                            lowest != null && note.pitch < lowest -> NoPlaceWhy.TOO_LOW
                            highest != null && note.pitch > highest -> NoPlaceWhy.TOO_HIGH
                            else -> NoPlaceWhy.OTHER
                        }
                        // On a notation staff the note is written, with its index; on a tab staff only the boxed words stand for it.
                        val written = index.of(i).firstOrNull { it.first } ?: index.of(i).firstOrNull()
                        val words = boxed.removeFirstOrNull()
                        when {
                            written != null -> add(written.bar, written.barNumber, written.onset, written.beat, written.pickup,
                                MarkedNote(MarkKind.NO_PLACE, i, step = written.step, alter = written.alter, name = words?.second?.ifEmpty { null }, why = why))
                            words != null -> add(words.first.bar, words.first.barNumber, words.first.onset, words.first.beat, words.first.pickup,
                                MarkedNote(MarkKind.NO_PLACE, i, name = words.second.ifEmpty { null }, why = why))
                            else -> unplaced++
                        }
                    } else if (note.confidence < threshold) {
                        start(i)?.let(::doubt) ?: unplaced++
                    }
                }
                unplaced += boxed.size
            }
            val columns = found.entries
                .map { (at, notes) -> places.getValue(at).let { (number, beat, pickup) -> TabColumn(at.first, at.second, number, at.third, beat, notes, pickup) } }
                .sortedWith(compareBy({ it.bar }, { it.onset }))
            // The lines above the tab count what is drawn: a note under a "!" is not also a "?", and a note the page folded into another is neither.
            return TabMarks(columns, columns.sumOf { c -> c.notes.count { it.kind == MarkKind.DOUBT } }, columns.sumOf { c -> c.notes.count { it.kind == MarkKind.NO_PLACE } }, unplaced)
        }
    }
}

/** What a mark says: to a screen reader, and on the screen when it is tapped. */
object TabWords {
    private fun pitch(step: String, alter: Int, bokmal: Boolean): String {
        if (!bokmal) return step + when (alter) { 1 -> "-sharp"; -1 -> "-flat"; 2 -> "-double-sharp"; -2 -> "-double-flat"; else -> "" }
        val natural = if (step == "B") "H" else step
        return when (alter) {
            1 -> "${natural}iss"
            -1 -> when (step) { "E" -> "Ess"; "A" -> "Ass"; "B" -> "B"; else -> "${step}ess" }
            2 -> "${natural}ississ"
            -2 -> when (step) { "E" -> "Essess"; "A" -> "Assass"; "B" -> "Bess"; else -> "${step}essess" }
            else -> natural
        }
    }

    /** "3rd": strings are named by number, 1st the highest, never by a note name (the tuning changes that). */
    fun ordinal(res: Resources, n: Int): String = res.getStringArray(R.array.fs_tab_ordinals).getOrNull(n - 1) ?: n.toString()

    /** "Bar 13, beat 2. 3rd string, fret 7, D-flat. Fretscribe isn't sure about this one." */
    fun describe(res: Resources, column: TabColumn, bokmal: Boolean): String {
        val parts = ArrayList<String>()
        parts += if (column.pickup) res.getString(R.string.fs_tab_pickup_beat, column.beat) else res.getString(R.string.fs_tab_bar_beat, column.barNumber, column.beat)
        for (n in column.notes) when (n.kind) {
            MarkKind.DOUBT -> {
                val name = n.step?.let { pitch(it, n.alter, bokmal) }
                parts += when {
                    n.string == null || n.fret == null -> name?.let { "$it." }.orEmpty()
                    n.fret == 0 -> res.getString(R.string.fs_tab_place_open, ordinal(res, n.string), name.orEmpty())
                    else -> res.getString(R.string.fs_tab_place, ordinal(res, n.string), n.fret, name.orEmpty())
                }
                parts += res.getString(R.string.fs_tab_not_sure)
            }
            MarkKind.NO_PLACE -> {
                val name = n.step?.let { pitch(it, n.alter, bokmal) } ?: n.name
                parts += when {
                    name == null -> res.getString(R.string.fs_tab_no_place)
                    n.why == NoPlaceWhy.TOO_LOW -> res.getString(R.string.fs_tab_no_place_low, name)
                    n.why == NoPlaceWhy.TOO_HIGH -> res.getString(R.string.fs_tab_no_place_high, name)
                    else -> res.getString(R.string.fs_tab_no_place_named, name)
                }
            }
        }
        return parts.filter { it.isNotBlank() }.joinToString(" ")
    }
}
