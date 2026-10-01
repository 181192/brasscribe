package no.brasscribe.play.fret

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.neverEqualPolicy
import androidx.compose.runtime.setValue
import no.brasscribe.play.Source
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.Octave
import no.brasscribe.play.engine.OctaveSource
import no.brasscribe.play.engine.Recording
import no.brasscribe.play.engine.Tab
import no.brasscribe.play.engine.TabLayout
import no.brasscribe.play.engine.TabNote
import no.brasscribe.play.engine.TabOptions
import no.brasscribe.play.model.CompositionJson

/**
 * What the player answered for one recording: What is this? ([recording], null until it is answered), and
 * what Check the song asked for ([again]: the options to write the same recording down with once more).
 */
data class SongAnswer(val recording: Recording? = null, val again: TabOptions? = null)

/**
 * The answers for the recording in hand, kept while it is the one being worked on: another recording
 * starts with none. They are for this song only; Your instrument is never changed by them.
 */
object SongAnswers {
    // The recording and its answers change together; every set is a change, also the same answer for another recording.
    private var asked by mutableStateOf<Pair<Source?, SongAnswer>>(null to SongAnswer(), neverEqualPolicy())

    /** The answers for [source]; none when it is another recording than the one asked about, also the same file opened again. */
    fun of(source: Source?): SongAnswer {
        val (recording, answer) = asked
        return if (source != null && source === recording) answer else SongAnswer()
    }

    fun set(source: Source?, value: SongAnswer) {
        asked = source to value
    }
}

/**
 * The `bass-tab` job's options. A first job is for the player's instrument and what was answered for this
 * song; a song written down again takes the options Check the song made for it.
 */
fun tabOptions(instrument: YourInstrument, answer: SongAnswer): TabOptions {
    answer.again?.let { return it }
    val chosen = instrument.jobOptions()
    val fretted = FrettedInstrument.entries.firstOrNull { it.id == chosen.instrument } ?: FrettedInstrument.BASS_4
    return TabOptions(
        instrument = fretted,
        tuning = chosen.tuning.takeIf { it in fretted.tunings } ?: FrettedInstrument.STANDARD_TUNING,
        capo = 0,
        // The fingering style is left to the computer's default (as played).
        style = null,
        // Continue needs an answer, so this is never the player's: an unanswered job is separated first, which also suits a bass alone.
        recording = answer.recording ?: Recording.SONG,
        octave = Octave.AUTO,
        layout = TabLayout.entries.firstOrNull { it.id == chosen.layout } ?: TabLayout.TAB,
    )
}

/** [request] as a bass-tab job: the tab options, and none of the band's (a seat, a clef, who plays the tune). */
fun tabJob(request: JobCreate, options: TabOptions): JobCreate =
    request.copy(seat = null, reads = null, lead = null).withTab(options)

/** One row of Check the song (design/fretscribe/flows.md §7): what Fretscribe heard, as the result tells it. */
sealed interface SongRow {
    /** The tuning the tab is written for, and the one the notes fit better when there is one. */
    data class Tuning(val written: String, val soundsLike: String?) : SongRow

    /**
     * The line was moved by [shift] semitones, by the octave check or because the player [chosen] it; or
     * [notesMoved] single notes were written an octave lower than they were heard.
     */
    data class Octave(val shift: Int, val chosen: Boolean, val notesMoved: Int) : SongRow

    /** The recording is tuned [cents] away from A = 440 (positive is sharp); [retuned]: the notes were read with that allowed for. */
    data class ReferencePitch(val cents: Int, val retuned: Boolean) : SongRow

    data class KeyAndTempo(val fifths: Int, val minor: Boolean, val bpm: Int, val beats: Int, val beatUnit: Int) : SongRow

    /** Notes marked "?". */
    data class Doubtful(val count: Int) : SongRow

    /** Notes no string of the instrument can play. */
    data class NoPlace(val count: Int) : SongRow
}

object SongCheck {
    /** A recording this far from A = 440 is worth a row; nearer than that is how any instrument is tuned. */
    const val REFERENCE_CENTS = 10

    /** The tuning id of a preset ("bass-4-drop-d" is "drop-d"); null for a preset this version does not know. */
    fun tuningOf(preset: String): String? = FrettedInstrument.entries.firstNotNullOfOrNull { i ->
        val id = i.id ?: return@firstNotNullOfOrNull null
        preset.removePrefix("$id-").takeIf { it != preset && it in i.tunings }
    }

    /** The number of strings of a preset's instrument ("bass-5-standard" has 5). */
    fun stringsOf(preset: String): Int? = FrettedInstrument.entries.firstOrNull { it.id != null && preset.startsWith("${it.id}-") }
        ?.id?.substringAfterLast('-')?.toIntOrNull()

    /**
     * The options [tab] was made with, read back from the result and from [stages] of its job (a full song was
     * separated first). This is what a song is written down again with, one thing changed: it holds for a
     * song opened from Your songs and after the app was restarted, when nothing else remembers the answers.
     */
    fun optionsOf(tab: Tab, stages: List<String>): TabOptions {
        val fretted = FrettedInstrument.entries.firstOrNull { it.id != null && tab.preset.startsWith("${it.id}-") }
        return TabOptions(
            instrument = fretted,
            tuning = tuningOf(tab.preset),
            capo = tab.instrument.capo,
            style = tab.style.takeIf { it.id != null },
            recording = if (stages.any { it == "stems" }) Recording.SONG else Recording.INSTRUMENT,
            octave = if (tab.octaveSource != OctaveSource.CHOSEN) Octave.AUTO else when {
                tab.octaveShift < 0 -> Octave.DOWN
                tab.octaveShift > 0 -> Octave.UP
                else -> Octave.AS_HEARD
            },
            layout = tab.layout.takeIf { it.id != null },
        )
    }

    private val EN = listOf("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
    private val NB = listOf("en", "to", "tre", "fire", "fem", "seks", "sju", "åtte", "ni", "ti", "elleve", "tolv")
    private val NB_UNITS = mapOf(2 to "halve", 4 to "firedels", 8 to "åttedels", 16 to "sekstendedels")
    private val EN_UNITS = mapOf(2 to "two", 4 to "four", 8 to "eight", 16 to "sixteen")

    /** A time signature as it is said: "two-four" (bokmål «to firedels»); the digits for one with no words here. */
    fun meterWords(beats: Int, beatUnit: Int, bokmal: Boolean): String {
        val count = (if (bokmal) NB else EN).getOrNull(beats - 1)
        val unit = (if (bokmal) NB_UNITS else EN_UNITS)[beatUnit]
        return if (count == null || unit == null) "$beats $beatUnit" else if (bokmal) "$count $unit" else "$count-$unit"
    }

    /** The rows the result has something to say for, in the order of the screen. */
    fun rows(tab: Tab): List<SongRow> = buildList {
        add(SongRow.Tuning(tuningOf(tab.preset) ?: tab.preset, tab.suggestedTuning?.let { tuningOf(it.preset) }))
        val chosen = tab.octaveSource == OctaveSource.CHOSEN
        if (tab.octaveShift != 0 || tab.octaveNotesMoved > 0 || chosen) add(SongRow.Octave(tab.octaveShift, chosen, tab.octaveNotesMoved))
        tab.referencePitch?.let { r ->
            val cents = Math.round(r.cents).toInt()
            if (kotlin.math.abs(r.cents) > REFERENCE_CENTS) add(SongRow.ReferencePitch(cents, r.retuned))
        }
        add(SongRow.KeyAndTempo(tab.key.fifths, tab.key.mode == no.brasscribe.play.engine.KeyMode.MINOR, Math.round(tab.tempoBpm).toInt(),
            tab.meter.beats, tab.meter.beatUnit))
        val doubtful = tab.notes.count { it.doubtful }
        if (doubtful > 0) add(SongRow.Doubtful(doubtful))
        val noPlace = tab.notes.count { it.outOfRange || it.position == null }
        if (noPlace > 0) add(SongRow.NoPlace(noPlace))
    }
}

/** What a saved song's row on Home says: read from the tab's MusicXML and its notes, as the library keeps them. */
data class SongFacts(val strings: Int?, val tuning: String?, val toCheck: Int) {
    companion object {
        private val STEPS = mapOf('C' to 0, 'D' to 2, 'E' to 4, 'F' to 5, 'G' to 7, 'A' to 9, 'B' to 11)

        /** The open strings of each tuning, lowest first (core/target-fretted/src/instrument.rs). */
        val OPEN_STRINGS: Map<String, List<Int>> = mapOf(
            "bass-4-standard" to listOf(28, 33, 38, 43),
            "bass-4-eb-standard" to listOf(27, 32, 37, 42),
            "bass-4-d-standard" to listOf(26, 31, 36, 41),
            "bass-4-drop-d" to listOf(26, 33, 38, 43),
            "bass-4-bead" to listOf(23, 28, 33, 38),
            "bass-5-standard" to listOf(23, 28, 33, 38, 43),
            "bass-5-drop-a" to listOf(21, 28, 33, 38, 43),
            "bass-6-standard" to listOf(23, 28, 33, 38, 43, 48),
        )

        /** The open strings a tab's MusicXML is written for (its staff tuning), lowest first; empty without one. */
        fun openStrings(musicXml: String): List<Int> =
            Regex("""<staff-tuning\b[^>]*>(.*?)</staff-tuning>""", RegexOption.DOT_MATCHES_ALL).findAll(musicXml).mapNotNull { m ->
                val body = m.groupValues[1]
                fun field(name: String) = Regex("<$name>\\s*([^<\\s]+)\\s*</$name>").find(body)?.groupValues?.get(1)
                val step = field("tuning-step")?.firstOrNull()?.let(STEPS::get) ?: return@mapNotNull null
                val octave = field("tuning-octave")?.toIntOrNull() ?: return@mapNotNull null
                val alter = field("tuning-alter")?.toDoubleOrNull()?.toInt() ?: 0
                (octave + 1) * 12 + step + alter
            }.toList().sorted()

        /** [compositionJson]: the notes with their confidence, as the computer wrote them. */
        fun of(musicXml: String, compositionJson: String?): SongFacts {
            val open = openStrings(musicXml)
            val preset = OPEN_STRINGS.entries.firstOrNull { it.value == open }?.key
            val toCheck = compositionJson?.let { json ->
                runCatching { CompositionJson.decode(json).voices.sumOf { v -> v.notes.count { it.confidence < TabNote.DOUBT } } }.getOrNull()
            } ?: 0
            return SongFacts(open.size.takeIf { it > 0 }, preset?.let(SongCheck::tuningOf), toCheck)
        }
    }
}
