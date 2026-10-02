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
import no.brasscribe.play.engine.Profile
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
 * The `tab` job's options. A first job is for the player's instrument and what was answered for this
 * song; a song written down again takes the options Check the song made for it.
 */
fun tabOptions(instrument: YourInstrument, answer: SongAnswer): TabOptions {
    answer.again?.let { return it }
    val mine = instrument.valid()
    return TabOptions(
        instrument = mine.kind,
        tuning = mine.tuning,
        // A capo is this song's, not the instrument's: Check the song asks about it.
        capo = 0,
        // The fingering style is left to the computer's default (as played).
        style = null,
        // Continue needs an answer, so this is never the player's: an unanswered job is taken as the computer takes it.
        recording = answer.recording ?: mine.kind.defaultRecording,
        octave = Octave.AUTO,
        layout = TabLayout.entries.firstOrNull { it.id == mine.reads.id } ?: TabLayout.TAB,
        // Chords are written as they were heard: the computer's default, so nothing is sent.
        chords = null,
    )
}

/**
 * What is this? as it stands before the player has answered. A ukulele or a mandolin starts on "Just my
 * instrument", as the computer takes it: in a song it only works when no guitar plays. A guitar or a bass
 * starts with nothing chosen.
 */
fun startingAnswer(instrument: YourInstrument): Recording? = instrument.valid().kind.let { if (it.aloneByDefault) it.defaultRecording else null }

/**
 * The profile ids the computer in use says it has, as it last answered; null until it has, or when it could
 * not be asked. What is this? and Check the song ask when they open.
 */
object ComputerProfiles {
    var listed: Set<String>? by mutableStateOf(null)
}

/**
 * The profile id a tab for [kind] is sent under, on a computer that has the profiles [listed] (null: not
 * known). `tab` where the computer has it. A computer from before it knows `bass-tab` only, which is the same
 * profile for a bass: a bass still goes there, under that id. Null: this computer cannot write a tab for the
 * instrument, and nothing is sent.
 */
fun tabProfile(kind: FrettedInstrument?, listed: Set<String>?): Profile? {
    val bass = kind?.isBass == true
    return when {
        // Not known: the id every computer that writes tab for the instrument has.
        listed == null -> if (bass) Profile.BASS_TAB else Profile.TAB
        Profile.TAB.id in listed -> Profile.TAB
        bass && Profile.BASS_TAB.id in listed -> Profile.BASS_TAB
        else -> null
    }
}

/**
 * [request] as a tab job: the tab options, and none of the band's (a seat, a clef, who plays the tune), under
 * the profile id the computer with [listed] has for the instrument ([tabProfile]; the usual id when it has none,
 * which the screens do not let through).
 */
fun tabJob(request: JobCreate, options: TabOptions, listed: Set<String>? = null): JobCreate =
    request.copy(profile = (tabProfile(options.instrument, listed) ?: Profile.TAB).id, seat = null, reads = null, lead = null).withTab(options)

/** One row of Check the song (design/fretscribe/flows.md §7): what Fretscribe heard, as the result tells it. */
sealed interface SongRow {
    /** The tuning the tab is written for, and the one the notes fit better when there is one; [kind]: the instrument, when it is known. */
    data class Tuning(val written: String, val soundsLike: String?, val kind: FrettedInstrument? = null) : SongRow

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

    /** The capo the tab is written for, 0 for none. Frets are counted from it. */
    data class Capo(val fret: Int) : SongRow

    /** Notes that were heard and are not in the tab: the instrument can't play them together with the others. */
    data class LeftOut(val count: Int) : SongRow

    /** Notes in the tab that were not heard: added to complete a chord, each marked "?". */
    data class Added(val count: Int) : SongRow
}

object SongCheck {
    /** A recording this far from A = 440 is worth a row; nearer than that is how any instrument is tuned. */
    const val REFERENCE_CENTS = 10

    /** The tuning id of a preset ("bass-4-drop-d" and "guitar-drop-d" are "drop-d"); null for a preset this version does not know. */
    fun tuningOf(preset: String): String? = FrettedInstrument.ofPreset(preset)?.second

    /** The instrument of a preset ("guitar-drop-d" is a six-string guitar); null for a preset this version does not know. */
    fun kindOf(preset: String): FrettedInstrument? = FrettedInstrument.ofPreset(preset)?.first

    /** The frets a capo can be asked for: 0 is none. */
    val CAPO_FRETS = 0..TabOptions.MAX_CAPO

    /** A capo is asked about for this tab: a guitar or a ukulele, or any tab that was written for one. */
    fun asksCapo(tab: Tab): Boolean = tab.instrument.capo > 0 || kindOf(tab.preset)?.let(Instrument::of)?.takesCapo == true

    /**
     * The options [tab] was made with, read back from the result and from [stages] of its job (a full song was
     * separated first). This is what a song is written down again with, one thing changed: it holds for a
     * song opened from Your songs and after the app was restarted, when nothing else remembers the answers.
     */
    fun optionsOf(tab: Tab, stages: List<String>): TabOptions {
        val made = FrettedInstrument.ofPreset(tab.preset)
        return TabOptions(
            instrument = made?.first,
            tuning = made?.second,
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
        add(SongRow.Tuning(tuningOf(tab.preset) ?: tab.preset, tab.suggestedTuning?.let { tuningOf(it.preset) }, kindOf(tab.preset)))
        if (asksCapo(tab)) add(SongRow.Capo(tab.instrument.capo))
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
        if (tab.unplayableDropped > 0) add(SongRow.LeftOut(tab.unplayableDropped))
        if (tab.inferredNotes > 0) add(SongRow.Added(tab.inferredNotes))
    }
}

/** What a saved song's row on Home says: read from the tab's MusicXML and its notes, as the library keeps them. */
data class SongFacts(val strings: Int?, val tuning: String?, val toCheck: Int, val kind: FrettedInstrument? = null) {
    companion object {
        private val STEPS = mapOf('C' to 0, 'D' to 2, 'E' to 4, 'F' to 5, 'G' to 7, 'A' to 9, 'B' to 11)

        /** The open strings of each tuning, lowest first (core/target-fretted/src/instrument.rs). */
        val OPEN_STRINGS: Map<String, List<Int>> = mapOf(
            "guitar-standard" to listOf(40, 45, 50, 55, 59, 64),
            "guitar-eb-standard" to listOf(39, 44, 49, 54, 58, 63),
            "guitar-d-standard" to listOf(38, 43, 48, 53, 57, 62),
            "guitar-c-standard" to listOf(36, 41, 46, 51, 55, 60),
            "guitar-drop-d" to listOf(38, 45, 50, 55, 59, 64),
            "guitar-drop-c" to listOf(36, 43, 48, 53, 57, 62),
            "guitar-drop-b" to listOf(35, 42, 47, 52, 56, 61),
            "guitar-dadgad" to listOf(38, 45, 50, 55, 57, 62),
            "guitar-open-g" to listOf(38, 43, 50, 55, 59, 62),
            "guitar-open-d" to listOf(38, 45, 50, 54, 57, 62),
            "guitar-open-e" to listOf(40, 47, 52, 56, 59, 64),
            "guitar-7-standard" to listOf(35, 40, 45, 50, 55, 59, 64),
            "guitar-7-eb-standard" to listOf(34, 39, 44, 49, 54, 58, 63),
            "guitar-8-standard" to listOf(30, 35, 40, 45, 50, 55, 59, 64),
            "bass-4-standard" to listOf(28, 33, 38, 43),
            "bass-4-eb-standard" to listOf(27, 32, 37, 42),
            "bass-4-d-standard" to listOf(26, 31, 36, 41),
            "bass-4-drop-d" to listOf(26, 33, 38, 43),
            "bass-4-bead" to listOf(23, 28, 33, 38),
            "bass-5-standard" to listOf(23, 28, 33, 38, 43),
            "bass-5-drop-a" to listOf(21, 28, 33, 38, 43),
            "bass-6-standard" to listOf(23, 28, 33, 38, 43, 48),
            "ukulele-high-g" to listOf(60, 64, 67, 69),
            "ukulele-low-g" to listOf(55, 60, 64, 69),
            "ukulele-baritone" to listOf(50, 55, 59, 64),
            "mandolin" to listOf(55, 62, 69, 76),
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
            return SongFacts(open.size.takeIf { it > 0 }, preset?.let(SongCheck::tuningOf), toCheck, preset?.let(SongCheck::kindOf))
        }
    }
}
