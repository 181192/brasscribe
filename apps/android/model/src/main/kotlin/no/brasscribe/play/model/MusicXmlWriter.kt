package no.brasscribe.play.model

/**
 * Writes monophonic parts of a Composition as MusicXML 4.0 partwise: transposing parts with
 * `<transpose>`, notes split at bar lines and tied, rests filling gaps, and uncertainty encoded as
 * colour plus notehead shape (parentheses below 0.4).
 *
 * This covers what the app creates on its own (a solo part from the microphone). Full-band scores
 * come from the engine, and later from the Rust core's writer.
 */
object MusicXmlWriter {
    private const val UNCERTAIN = "#0063A6"
    private const val VERY_UNCERTAIN = "#B04A00"

    fun write(composition: Composition, parts: List<PartSpec>): String {
        val map = TickMap(composition)
        val tpb = composition.ticksPerBeat
        val lastBar = maxOf(1, map.barOf(maxOf(0, composition.endTick - 1)))
        val sb = StringBuilder()
        sb.append("""<?xml version="1.0" encoding="UTF-8"?>""").append('\n')
        sb.append("""<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">""").append('\n')
        sb.append("""<score-partwise version="4.0">""").append('\n')
        sb.append("  <work><work-title>").append(esc(composition.title)).append("</work-title></work>\n")
        sb.append("  <identification><encoding><software>Brasscribe Play</software></encoding></identification>\n")
        sb.append("  <part-list>\n")
        parts.forEachIndexed { i, p ->
            sb.append("""    <score-part id="P${i + 1}"><part-name>""").append(esc(p.name)).append("</part-name>")
            sb.append("""<score-instrument id="P${i + 1}-I1"><instrument-name>""").append(esc(p.name)).append("</instrument-name></score-instrument>")
            sb.append("""<midi-instrument id="P${i + 1}-I1"><midi-channel>${i % 15 + 1}</midi-channel><midi-program>${p.instrument.midiProgram + 1}</midi-program></midi-instrument>""")
            sb.append("</score-part>\n")
        }
        sb.append("  </part-list>\n")
        parts.forEachIndexed { i, p ->
            val voice = composition.voice(p.voiceId) ?: Voice(p.voiceId, VoiceRole.MELODY, emptyList())
            sb.append("""  <part id="P${i + 1}">""").append('\n')
            writePart(sb, composition, map, voice, p.instrument, lastBar, tpb)
            sb.append("  </part>\n")
        }
        sb.append("</score-partwise>\n")
        return sb.toString()
    }

    private data class Seg(val start: Int, val dur: Int, val note: Note?, val tieStart: Boolean, val tieStop: Boolean)

    private fun writePart(sb: StringBuilder, c: Composition, map: TickMap, voice: Voice, inst: Instrument, lastBar: Int, tpb: Int) {
        // Monophonic line: later onsets cut earlier notes; notes before tick 0 are dropped.
        val notes = voice.notes.filter { it.start >= 0 }.sortedBy { it.start }.let { list ->
            list.mapIndexed { i, n ->
                val next = list.getOrNull(i + 1)
                if (next != null && next.start < n.end) n.copy(dur = maxOf(1, next.start - n.start)) else n
            }.filter { it.dur > 0 }
        }
        var cursor = 0
        var ni = 0
        for (bar in 1..lastBar) {
            val barStart = map.barStart(bar)
            val barEnd = map.barEnd(bar)
            sb.append("""    <measure number="$bar">""").append('\n')
            if (bar == 1 || map.meterAt(barStart).tick == barStart || map.keyAt(barStart).tick == barStart && barStart > 0) {
                val m = map.meterAt(barStart)
                sb.append("      <attributes>")
                if (bar == 1) sb.append("<divisions>$tpb</divisions>")
                sb.append("<key><fifths>${inst.writtenFifths(map.keyAt(barStart).fifths)}</fifths></key>")
                sb.append("<time><beats>${m.beats}</beats><beat-type>${m.beatUnit}</beat-type></time>")
                if (bar == 1) {
                    sb.append(if (inst == Instrument.BASS_TROMBONE) "<clef><sign>F</sign><line>4</line></clef>" else "<clef><sign>G</sign><line>2</line></clef>")
                    if (inst.chromatic != 0) {
                        val oct = inst.chromatic / 12
                        val chrom = inst.chromatic - oct * 12
                        val dia = inst.diatonic - oct * 7
                        sb.append("<transpose><diatonic>$dia</diatonic><chromatic>$chrom</chromatic>")
                        if (oct != 0) sb.append("<octave-change>$oct</octave-change>")
                        sb.append("</transpose>")
                    }
                }
                sb.append("</attributes>\n")
            }
            if (bar == 1) sb.append("""      <direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>${c.bpm.toInt()}</per-minute></metronome></direction-type><sound tempo="${c.bpm.toInt()}"/></direction>""").append('\n')
            c.freeRegionAt(barStart)?.takeIf { map.barOf(it.start) == bar }?.let {
                sb.append("""      <direction placement="above"><direction-type><words>${esc(it.label)}</words></direction-type></direction>""").append('\n')
            }
            // Segments inside this bar.
            val segs = mutableListOf<Seg>()
            cursor = barStart
            while (cursor < barEnd) {
                val n = notes.getOrNull(ni)
                if (n == null || n.start >= barEnd) {
                    segs += Seg(cursor, barEnd - cursor, null, false, false); cursor = barEnd
                } else if (n.start > cursor) {
                    segs += Seg(cursor, n.start - cursor, null, false, false); cursor = n.start
                } else {
                    val end = minOf(n.end, barEnd)
                    segs += Seg(cursor, end - cursor, n, tieStart = n.end > barEnd, tieStop = n.start < barStart)
                    cursor = end
                    if (n.end <= barEnd) ni++
                }
            }
            if (segs.all { it.note == null }) {
                sb.append("""      <note><rest measure="yes"/><duration>${barEnd - barStart}</duration></note>""").append('\n')
            } else for (s in segs) writeSeg(sb, s, inst, map, tpb)
            sb.append("    </measure>\n")
        }
    }

    private fun writeSeg(sb: StringBuilder, s: Seg, inst: Instrument, map: TickMap, tpb: Int) {
        val values = Durations.split(s.dur, tpb)
        var used = 0
        values.forEachIndexed { i, v ->
            val d = if (i == values.lastIndex) s.dur - used else v.ticks(tpb)
            used += d
            val n = s.note
            if (n == null) {
                sb.append("      <note><rest/><duration>$d</duration>${typeXml(v)}</note>\n")
                return@forEachIndexed
            }
            val written = inst.spellWritten(n.pitch, map.keyAt(maxOf(0, n.start)).fifths)
            val tieStop = s.tieStop || i > 0
            val tieStart = s.tieStart || i < values.lastIndex
            val color = when (n.uncertainty) {
                Uncertainty.CONFIDENT -> null
                Uncertainty.UNCERTAIN -> UNCERTAIN
                Uncertainty.VERY_UNCERTAIN -> VERY_UNCERTAIN
            }
            sb.append("      <note").append(color?.let { " color=\"$it\"" } ?: "").append(">")
            sb.append("<pitch><step>${written.step}</step>")
            if (written.alter != 0) sb.append("<alter>${written.alter}</alter>")
            sb.append("<octave>${written.octave}</octave></pitch>")
            sb.append("<duration>$d</duration>")
            if (tieStop) sb.append("""<tie type="stop"/>""")
            if (tieStart) sb.append("""<tie type="start"/>""")
            sb.append(typeXml(v))
            if (n.uncertainty == Uncertainty.VERY_UNCERTAIN) sb.append("""<notehead parentheses="yes" color="$color">normal</notehead>""")
            val notations = buildString {
                if (tieStop) append("""<tied type="stop"/>""")
                if (tieStart) append("""<tied type="start"/>""")
                if (i == 0 && !s.tieStop) {
                    val arts = n.articulations.filter { it == Articulation.STACCATO || it == Articulation.ACCENT || it == Articulation.TENUTO }
                    if (arts.isNotEmpty()) append("<articulations>").append(arts.joinToString("") { "<${it.name.lowercase().replace("accent", "accent")}/>" }).append("</articulations>")
                    if (Articulation.FERMATA in n.articulations) append("<fermata/>")
                }
            }
            if (notations.isNotEmpty()) sb.append("<notations>$notations</notations>")
            sb.append("</note>\n")
        }
    }

    private fun typeXml(v: NoteValue): String = buildString {
        append("<type>${v.type}</type>")
        repeat(v.dots) { append("<dot/>") }
        if (v.triplet) append("<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>")
    }

    private fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
}
