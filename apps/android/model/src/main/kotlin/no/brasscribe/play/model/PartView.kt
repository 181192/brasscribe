package no.brasscribe.play.model

/** One navigable stop of a part: a note (or a run of empty bars) plus its talking-score data. */
data class PartEvent(
    val index: Int,
    val bar: Int,
    val tick: Int,
    val note: Note?,
    val stop: TsStop,
) {
    val uncertainty: Uncertainty get() = note?.uncertainty ?: Uncertainty.CONFIDENT
}

data class PartBar(val number: Int, val events: List<PartEvent>)

/**
 * A single part of a Composition laid out for review and screen-reader navigation: notes in time
 * order, grouped into bars, each with the event data the announcer speaks.
 */
class PartView(
    val composition: Composition,
    val voice: Voice,
    val instrument: Instrument,
    val partName: String,
    val partNameNb: String = partName,
    val checked: Set<Int> = emptySet(),
    /** Spells the notes (the Rust core's ps13 when available). */
    private val core: CoreBridge = KotlinCoreBridge,
) {
    val tickMap = TickMap(composition)
    private val tpb = composition.ticksPerBeat
    val totalBars: Int = tickMap.totalBars

    val tsPart = TsPart(partName, partNameNb, instrument.keyEn, instrument.keyNb)

    val events: List<PartEvent> by lazy { buildEvents() }
    val bars: List<PartBar> by lazy { events.groupBy { it.bar }.map { (b, e) -> PartBar(b, e) } }

    fun eventsInBar(bar: Int): List<PartEvent> = events.filter { it.bar == bar }

    private val sortedNotes = voice.notes.sortedWith(compareBy({ it.start }, { it.pitch }))

    /** Concert spelling of every note, in [sortedNotes] order. */
    private val concertSpelling: List<SpelledPitch> by lazy {
        core.spell(sortedNotes.map { it.start.toDouble() / tpb }, sortedNotes.map { it.pitch }, composition.keys.firstOrNull()?.fifths)
    }

    /** The piece opens with a pickup: some voice has a note before the first downbeat. */
    private val hasPickup: Boolean = composition.voices.any { v -> v.notes.any { it.start < 0 } }

    private fun buildEvents(): List<PartEvent> {
        val notes = sortedNotes
        val out = mutableListOf<PartEvent>()
        // With a pickup in the piece, a part that rests through it rests from the pickup (bar 0) on.
        var lastBar = if (hasPickup) PICKUP_BAR - 1 else 0
        for ((i, n) in notes.withIndex()) {
            val bar = tickMap.barOf(n.start)
            if (bar - lastBar > 1) {
                val first = lastBar + 1
                val count = bar - first
                out += PartEvent(out.size, first, tickMap.barStart(first), null,
                    TsStop(TsEvent(kind = "bar-rest", bars = count), barInfo(first), tsPart, keyAt(first), totalBars))
            }
            lastBar = maxOf(lastBar, tickMap.barOf(n.end - 1))
            out += PartEvent(out.size, bar, n.start, n, noteStop(i, n, bar))
        }
        return markRegionChanges(out)
    }

    /**
     * The first event inside a free-time region announces the region ("Ad lib…"); the first event after
     * it announces the tempo it returns to ("A tempo…"). Everything else in the region stays quiet.
     */
    private fun markRegionChanges(events: List<PartEvent>): List<PartEvent> {
        var prevRegion: TsFreeRegion? = null
        return events.map { e ->
            val bar = e.stop.bar ?: return@map e.also { prevRegion = null }
            val region = bar.freeRegion
            val newBar = when {
                region != null -> bar.copy(freeRegion = region.copy(entering = prevRegion == null))
                prevRegion != null -> bar.copy(tempoBpm = kotlin.math.floor(composition.bpm + 0.5).toInt(), aTempo = true)
                else -> bar
            }
            prevRegion = region
            e.copy(stop = e.stop.copy(bar = newBar))
        }
    }

    private fun keyAt(bar: Int): Int = instrument.writtenFifths(tickMap.keyAt(maxOf(0, tickMap.barStart(bar))).fifths)

    private fun barInfo(bar: Int): TsBar {
        val start = maxOf(0, tickMap.barStart(bar))
        val region = composition.freeRegionAt(start)?.let { r ->
            TsFreeRegion(tickMap.barOf(r.start), tickMap.barOf(maxOf(r.start, r.end - 1)), r.startS, r.endS)
        }
        return TsBar(bar, freeRegion = region)
    }

    private fun noteStop(index: Int, n: Note, bar: Int): TsStop {
        val barStart = tickMap.barStart(bar)
        val meter = tickMap.meterAt(maxOf(0, n.start))
        val compound = meter.beatUnit == 8 && meter.beats % 3 == 0 && meter.beats > 3
        val beatTicks = if (compound) tpb * 3 / 2 else tpb * 4 / meter.beatUnit
        val inBar = n.start - barStart
        val beat = inBar / beatTicks + 1
        val offset = inBar % beatTicks
        val pos = TsPos(beat, offset, if (offset == 0) 1 else beatTicks, if (compound) true else null).reduced()

        val barEnd = tickMap.barEnd(bar)
        val firstLen = minOf(n.dur, barEnd - n.start).coerceAtLeast(1)
        val value = Durations.split(firstLen, tpb).first()
        val tie = when {
            firstLen < n.dur -> {
                val rest = n.dur - firstLen
                val next = Durations.split(minOf(rest, tickMap.ticksPerBar(barEnd)), tpb).first()
                if (rest > tickMap.ticksPerBar(barEnd)) TsTie(start = true, chainBeats = n.dur.toDouble() / tpb)
                else TsTie(start = true, next = TsTieNext(bar + 1, next.type, next.dots))
            }
            Durations.split(firstLen, tpb).size > 1 -> {
                val next = Durations.split(firstLen, tpb)[1]
                TsTie(start = true, next = TsTieNext(bar, next.type, next.dots))
            }
            else -> null
        }
        val event = TsEvent(
            kind = "note",
            pos = pos,
            type = value.type,
            dots = value.dots,
            tuplet = if (value.triplet) TsTuplet(3, 2, (offset / value.ticks(tpb)) % 3 + 1) else null,
            tie = tie,
            written = instrument.written(concertSpelling[index]),
            concert = concertSpelling[index],
            articulations = n.articulations.map { it.name.lowercase() },
            confidence = n.confidence,
            sources = n.sources,
            checked = index in checked,
            timeS = n.onsetS,
            performedS = if (n.onsetS != null && n.offsetS != null) n.offsetS - n.onsetS else null,
        )
        return TsStop(event, barInfo(bar), tsPart, keyAt(bar), totalBars)
    }

    private fun TsPos.reduced(): TsPos {
        if (num == 0) return copy(num = 0, den = 1)
        var a = num
        var b = den
        while (b != 0) { val t = a % b; a = b; b = t }
        return copy(num = num / a, den = den / a)
    }

    /** Announcement for event [i] after [previous] (null at the start of navigation). */
    fun announce(i: Int, previous: PartEvent?, settings: TsSettings, lang: Lang, bridge: CoreBridge): String {
        val e = events[i]
        val ctx = TsContext(part = if (previous == null) null else partName, bar = previous?.bar)
        return bridge.announce(e.stop, ctx, settings, lang)
    }
}
