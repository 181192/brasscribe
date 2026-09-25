package no.brasscribe.play.score

import alphaTab.AlphaTabView
import alphaTab.LayoutMode
import alphaTab.PlayerMode
import alphaTab.ScrollMode
import alphaTab.collections.DoubleList
import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.midi.AlphaSynthMidiFileHandler
import alphaTab.midi.MidiEventType
import alphaTab.midi.MidiFile
import alphaTab.midi.MidiFileGenerator
import alphaTab.midi.NoteOffEvent
import alphaTab.midi.NoteOnEvent
import alphaTab.model.Score
import alphaTab.model.Track
import alphaTab.synth.PlaybackRange
import alphaTab.synth.PlayerState
import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import no.brasscribe.play.audio.RealisticSynth

/** The part of the score the player sees and hears, in plain values for Compose. */
data class ScoreUiState(
    val loaded: Boolean = false,
    val error: String? = null,
    val title: String = "",
    val parts: List<String> = emptyList(),
    val shown: Set<Int> = emptySet(),
    val muted: Set<Int> = emptySet(),
    val soloed: Set<Int> = emptySet(),
    val playing: Boolean = false,
    val bar: Int = 1,
    val totalBars: Int = 1,
    val speed: Int = 100,
    val loop: IntRange? = null,
    val countIn: Boolean = false,
    val metronome: Boolean = false,
    val concertPitch: Boolean = false,
    val zoom: Int = 100,
    val realistic: Boolean = false,
    val keyShift: Int = 0,
)

/**
 * Owns the alphaTab view (notation, cursor, synth) and exposes the practice controls: part selection,
 * mute and solo, speed without pitch change, bar-range loop, count-in, metronome, concert pitch, zoom,
 * and the realistic sfizz tier, which takes over the note events while alphaTab's own instruments are
 * silenced (the metronome and count-in stay on alphaTab).
 */
class ScoreController(context: Context, reducedMotion: Boolean) {
    val view: AlphaTabView = AlphaTabView(context, null)
    private val _state = MutableStateFlow(ScoreUiState())
    val state: StateFlow<ScoreUiState> = _state
    private var score: Score? = null
    private val writtenTransposition = HashMap<Int, Double>()

    init {
        view.settings.apply {
            display.layoutMode = LayoutMode.Page
            player.playerMode = PlayerMode.EnabledSynthesizer
            player.enableCursor = true
            player.enableUserInteraction = true
            player.enableAnimatedBeatCursor = !reducedMotion
            player.scrollMode = if (reducedMotion) ScrollMode.OffScreen else ScrollMode.Continuous
        }
        view.api.updateSettings()
        view.importantForAccessibility = android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        view.api.playerStateChanged.on { e ->
            _state.value = _state.value.copy(playing = e.state == PlayerState.Playing)
            if (e.state != PlayerState.Playing) RealisticSynth.allOff()
        }
        view.api.playedBeatChanged.on { beat -> _state.value = _state.value.copy(bar = beat.voice.bar.index.toInt() + 1) }
        view.api.error.on { e -> _state.value = _state.value.copy(error = e.message ?: e.javaClass.simpleName) }
        view.api.midiEventsPlayed.on { e ->
            if (!_state.value.realistic) return@on
            for (ev in e.events) {
                when (ev) {
                    is NoteOnEvent -> if (channelAudible(ev.channel.toInt())) RealisticSynth.noteOn(ev.channel.toInt() % 16, ev.noteKey.toInt(), ev.noteVelocity.toInt())
                    is NoteOffEvent -> RealisticSynth.noteOff(ev.channel.toInt() % 16, ev.noteKey.toInt())
                }
            }
        }
    }

    /** Parses MusicXML (or any format alphaTab reads) and renders the given tracks (default: the first). */
    fun load(bytes: ByteArray, pick: (List<String>) -> Set<Int> = { setOf(0) }) {
        try {
            val s = ScoreLoader.loadScoreFromBytes(Uint8Array(bytes.asUByteArray()), view.settings)
            score = s
            s.tracks.forEach { t -> writtenTransposition[t.index.toInt()] = t.staves[0].displayTranspositionPitch }
            // alphaTab keeps MusicXML part names with no-break spaces; plain spaces read and match better.
            val names = (0 until s.tracks.length.toInt()).map { i ->
                s.tracks[i].name.ifBlank { s.tracks[i].shortName }.replace(' ', ' ').trim()
            }
            val shown = pick(names).filter { it < names.size }.toSet().ifEmpty { setOf(0) }
            _state.value = _state.value.copy(
                loaded = true, error = null, title = s.title, parts = names,
                shown = shown, totalBars = s.masterBars.length.toInt(),
            )
            render()
        } catch (e: Throwable) {
            _state.value = _state.value.copy(error = e.message ?: e.javaClass.simpleName)
        }
    }

    private fun tracks(indexes: Collection<Int>): alphaTab.collections.List<Track> {
        val s = score ?: return alphaTab.collections.List()
        return alphaTab.collections.List(*indexes.sorted().map { s.tracks[it] }.toTypedArray())
    }

    private fun render() {
        val s = score ?: return
        view.api.renderScore(s, DoubleList(*_state.value.shown.sorted().map { it.toDouble() }.toDoubleArray()))
    }

    fun showParts(indexes: Set<Int>) {
        if (indexes.isEmpty()) return
        _state.value = _state.value.copy(shown = indexes)
        render()
    }

    fun togglePlay() = view.api.playPause()
    fun stop() { view.api.stop(); RealisticSynth.allOff() }

    fun setSpeed(percent: Int) {
        val p = percent.coerceIn(25, 150)
        view.api.playbackSpeed = p / 100.0
        _state.value = _state.value.copy(speed = p)
    }

    fun setMuted(index: Int, muted: Boolean) {
        view.api.changeTrackMute(tracks(listOf(index)), muted)
        _state.value = _state.value.copy(muted = if (muted) _state.value.muted + index else _state.value.muted - index)
    }

    fun setSolo(index: Int, solo: Boolean) {
        view.api.changeTrackSolo(tracks(listOf(index)), solo)
        _state.value = _state.value.copy(soloed = if (solo) _state.value.soloed + index else _state.value.soloed - index)
    }

    private fun channelAudible(channel: Int): Boolean {
        val s = score ?: return true
        val st = _state.value
        val track = s.tracks.firstOrNull { it.playbackInfo.primaryChannel.toInt() == channel || it.playbackInfo.secondaryChannel.toInt() == channel }
            ?: return true
        val i = track.index.toInt()
        return i !in st.muted && (st.soloed.isEmpty() || i in st.soloed)
    }

    /** Loops bars [from]..[to] (1-based, inclusive); null clears the loop. */
    fun setLoop(range: IntRange?) {
        val s = score ?: return
        if (range == null) {
            view.api.playbackRange = null
            view.api.isLooping = false
        } else {
            val bars = s.masterBars
            val first = bars[(range.first - 1).coerceIn(0, bars.length.toInt() - 1)]
            val lastIndex = range.last.coerceIn(1, bars.length.toInt())
            val end = if (lastIndex < bars.length.toInt()) bars[lastIndex].start else bars[lastIndex - 1].start + bars[lastIndex - 1].calculateDuration()
            view.api.playbackRange = PlaybackRange().apply { startTick = first.start; endTick = end }
            view.api.isLooping = true
            view.api.tickPosition = first.start
        }
        _state.value = _state.value.copy(loop = range)
    }

    fun goToBar(bar: Int) {
        val s = score ?: return
        val b = bar.coerceIn(1, s.masterBars.length.toInt())
        view.api.tickPosition = s.masterBars[b - 1].start
        _state.value = _state.value.copy(bar = b)
    }

    fun playBar(bar: Int) {
        setLoop(bar..bar)
        view.api.isLooping = false
        view.api.play()
    }

    fun setCountIn(on: Boolean) {
        view.api.countInVolume = if (on) 1.0 else 0.0
        _state.value = _state.value.copy(countIn = on)
    }

    fun setMetronome(on: Boolean) {
        view.api.metronomeVolume = if (on) 1.0 else 0.0
        _state.value = _state.value.copy(metronome = on)
    }

    /** Written pitch shows each part as the player reads it; concert pitch shows what sounds. */
    fun setConcertPitch(on: Boolean) {
        val s = score ?: return
        _state.value = _state.value.copy(concertPitch = on)
        applyDisplayTransposition(s)
        render()
    }

    /** Transposes playback and notation of every part by [semitones]. */
    fun setKeyShift(semitones: Int) {
        val s = score ?: return
        view.api.changeTrackTranspositionPitch(s.tracks, semitones.toDouble())
        _state.value = _state.value.copy(keyShift = semitones)
        applyDisplayTransposition(s)
        render()
    }

    // alphaTab shows note - displayTranspositionPitch.
    private fun applyDisplayTransposition(s: Score) {
        val st = _state.value
        s.tracks.forEach { t ->
            val written = if (st.concertPitch) 0.0 else writtenTransposition[t.index.toInt()] ?: 0.0
            t.staves.forEach { staff -> staff.displayTranspositionPitch = written - st.keyShift }
        }
    }

    fun setZoom(percent: Int) {
        val z = percent.coerceIn(50, 400)
        view.settings.display.scale = z / 100.0
        view.api.updateSettings()
        _state.value = _state.value.copy(zoom = z)
        render()
    }

    /** Realistic tier on: alphaTab's instruments go silent and their note events drive sfizz. */
    fun setRealistic(on: Boolean): Boolean {
        val s = score ?: return false
        if (on && !RealisticSynth.start()) return false
        if (on) for (ch in 0 until 16) if (RealisticSynth.regions(ch) == 0) RealisticSynth.loadTestTone(ch)
        view.api.changeTrackVolume(s.tracks, if (on) 0.0 else 1.0)
        view.api.midiEventsPlayedFilter = if (on) alphaTab.collections.List(MidiEventType.NoteOn, MidiEventType.NoteOff) else alphaTab.collections.List()
        if (!on) { RealisticSynth.allOff(); RealisticSynth.stop() }
        _state.value = _state.value.copy(realistic = on)
        return true
    }

    /** Standard MIDI file of the loaded score, generated by alphaTab. */
    fun midiBytes(): ByteArray? {
        val s = score ?: return null
        val midi = MidiFile()
        MidiFileGenerator(s, view.settings, AlphaSynthMidiFileHandler(midi, true)).generate()
        return midi.toBinary().buffer.asByteArray()
    }

    fun release() {
        RealisticSynth.allOff()
        runCatching { view.api.stop() }
    }
}
