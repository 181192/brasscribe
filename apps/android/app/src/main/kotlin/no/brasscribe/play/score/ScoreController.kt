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
    /** Parts playing a real instrument from the sound pack in the realistic tier. */
    val soundPackParts: Int = 0,
    /** The realistic tier plays humanized notes (the Rust core). */
    val humanized: Boolean = false,
    /** The band SoundFont replaced alphaTab's built-in one. */
    val bandSoundFont: Boolean = false,
    /** MIDI channel of each part as the synth plays it (index 9 = channel 10, drums). */
    val channels: List<Int> = emptyList(),
)

/**
 * Owns the alphaTab view (notation, cursor, synth) and exposes the practice controls: part selection,
 * mute and solo, speed without pitch change, bar-range loop, count-in, metronome, concert pitch, zoom,
 * and the realistic sfizz tier, which takes over the note events while alphaTab's own instruments are
 * silenced (the metronome and count-in stay on alphaTab).
 */
class ScoreController(
    context: Context,
    reducedMotion: Boolean,
    private val core: no.brasscribe.play.model.CoreBridge = no.brasscribe.play.model.KotlinCoreBridge,
    /** Band SoundFont part map (sounds/mapping.json); null keeps alphaTab's General MIDI programs. */
    private val soundMap: BandSoundMap? = null,
    /** brasscribe-band.sf2 when installed; alphaTab keeps its built-in SoundFont otherwise. */
    private val bandSoundFont: java.io.File? = null,
    /** The Composition the score came from, for humanization. */
    private val compositionJson: String? = null,
) {
    val view: AlphaTabView = AlphaTabView(context, null)
    private var channels = IntArray(0)
    private var percussion: List<Boolean> = emptyList()
    private var gains = DoubleArray(0)
    private val humanized = HumanizedPlayer(core)
    private var humanizedReady = false
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
            val playing = e.state == PlayerState.Playing
            _state.value = _state.value.copy(playing = playing)
            if (_state.value.realistic && humanizedReady) {
                if (playing) humanized.start(::channelAudible) else humanized.stop()
            } else if (!playing) RealisticSynth.allOff()
        }
        view.api.playerPositionChanged.on { e ->
            if (_state.value.realistic && humanizedReady) humanized.position(humanized.secondsAt(e.currentTick), view.api.playbackSpeed)
        }
        // Channel volumes reset when the MIDI is regenerated (every render), so the balance follows it.
        // (api.midiLoaded cannot be used: in alphaTab 1.8.4 on Android its getter recurses forever.)
        view.api.postRenderFinished.on { applyVolumes() }

        view.api.playedBeatChanged.on { beat -> _state.value = _state.value.copy(bar = beat.voice.bar.index.toInt() + 1) }
        view.api.error.on { e -> _state.value = _state.value.copy(error = e.message ?: e.javaClass.simpleName) }
        view.api.midiEventsPlayed.on { e ->
            if (no.brasscribe.play.BuildConfig.DEBUG) for (ev in e.events) if (ev is NoteOnEvent) notesPerChannel.merge(ev.channel.toInt(), 1, Int::plus)
            // Without humanization (no core) the realistic tier follows alphaTab's own note events.
            if (!_state.value.realistic || humanizedReady) return@on
            for (ev in e.events) {
                when (ev) {
                    is NoteOnEvent -> if (ev.channel.toInt() != ChannelPlan.DRUMS && channelAudible(ev.channel.toInt())) RealisticSynth.noteOn(ev.channel.toInt(), ev.noteKey.toInt(), ev.noteVelocity.toInt())
                    is NoteOffEvent -> RealisticSynth.noteOff(ev.channel.toInt(), ev.noteKey.toInt())
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
            prepareSound(s, names)
            loadBandSoundFont()
            _state.value = _state.value.copy(
                loaded = true, error = null, title = s.title, parts = names,
                shown = shown, totalBars = s.masterBars.length.toInt(),
            )
            render()
        } catch (e: Throwable) {
            _state.value = _state.value.copy(error = e.message ?: e.javaClass.simpleName)
        }
    }

    /**
     * One MIDI channel per part (drums on channel 10), the band SoundFont preset (program, bank) per
     * part, and its balance as channel gain. The MusicXML importer turns <midi-instrument> into
     * per-beat instrument and bank changes that would override the preset, so those are removed.
     */
    private fun prepareSound(s: Score, names: List<String>) {
        percussion = (0 until s.tracks.length.toInt()).map { i -> s.tracks[i].staves.any { it.isPercussion } }
        channels = ChannelPlan.forPlayback(percussion)
        gains = DoubleArray(names.size) { 1.0 }
        for (i in names.indices) {
            val t = s.tracks[i]
            t.playbackInfo.primaryChannel = channels[i].toDouble()
            t.playbackInfo.secondaryChannel = channels[i].toDouble()
            val sound = soundMap?.forPart(names[i]) ?: continue
            t.playbackInfo.program = if (sound.percussion) 0.0 else sound.program.toDouble()
            t.playbackInfo.bank = if (sound.percussion) 0.0 else sound.bank.toDouble()
            gains[i] = sound.gain
            for (staff in t.staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) {
                val keep = ArrayList<alphaTab.model.Automation>()
                for (a in beat.automations) if (a.type != alphaTab.model.AutomationType.Instrument && a.type != alphaTab.model.AutomationType.Bank) keep += a
                if (keep.size != beat.automations.length.toInt()) beat.automations = alphaTab.collections.List(*keep.toTypedArray())
            }
        }
        _state.value = _state.value.copy(channels = channels.toList())
    }

    private var soundFontRequested = false

    /** Replaces alphaTab's built-in SoundFont with the band SoundFont (read off the UI thread). */
    private fun loadBandSoundFont() {
        val sf = bandSoundFont?.takeIf { it.isFile } ?: return
        if (soundFontRequested) return
        soundFontRequested = true
        Thread({
            val t0 = System.nanoTime()
            val bytes = runCatching { sf.readBytes() }.getOrElse {
                android.util.Log.w("BrasscribePlay", "band SoundFont unreadable", it); return@Thread
            }
            fun attempt(tries: Int) {
                // api.loadSoundFont(ByteArray) returns false on Android (AndroidUiFacade's `when` compares the
                // value, not the type), so the synth gets the bytes directly.
                val player = view.api.player
                val ok = player != null && runCatching {
                    player.soundFontLoaded.on {
                        _state.value = _state.value.copy(bandSoundFont = true)
                        android.util.Log.i("BrasscribePlay", "band SoundFont %s (%d MB) loaded by alphaTab in %d ms"
                            .format(sf.name, bytes.size shr 20, (System.nanoTime() - t0) / 1_000_000))
                    }
                    player.loadSoundFont(Uint8Array(bytes.asUByteArray()), false); true
                }.getOrDefault(false)
                if (!ok) if (tries > 0) view.postDelayed({ attempt(tries - 1) }, 200)
                else android.util.Log.w("BrasscribePlay", "alphaTab player not ready for the band SoundFont")
            }
            view.post { attempt(50) }
        }, "band-soundfont").start()
    }

    /** Applies each part's balance (and mutes alphaTab's pitched parts while sfizz plays them). */
    private fun applyVolumes() {
        val s = score ?: return
        for (i in 0 until s.tracks.length.toInt()) {
            val silent = _state.value.realistic && !percussion.getOrElse(i) { false }
            view.api.changeTrackVolume(alphaTab.collections.List(s.tracks[i]), if (silent) 0.0 else gains.getOrElse(i) { 1.0 })
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

    /** Debug builds count the note-ons alphaTab plays per MIDI channel and log them on pause. */
    private val notesPerChannel = java.util.TreeMap<Int, Int>()

    fun togglePlay() {
        applyVolumes()
        if (no.brasscribe.play.BuildConfig.DEBUG) {
            if (_state.value.playing) android.util.Log.i("BrasscribePlay", "note-ons per channel: $notesPerChannel")
            else if (!_state.value.realistic) { notesPerChannel.clear(); view.api.midiEventsPlayedFilter = alphaTab.collections.List(MidiEventType.NoteOn) }
        }
        if (!view.api.isReadyForPlayback) android.util.Log.w("BrasscribePlay", "player not ready (state ${view.api.playerState})")
        view.api.playPause()
    }
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
        val i = channels.indexOf(channel).takeIf { it >= 0 } ?: return s.tracks.length > 0
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

    /**
     * Realistic tier on: every pitched part plays an SFZ instrument through sfizz on its own channel
     * with its band balance, humanized by the core; alphaTab keeps the kit, metronome and count-in.
     */
    fun setRealistic(on: Boolean): Boolean {
        val s = score ?: return false
        if (on && !RealisticSynth.start()) return false
        if (on) {
            val pack = SoundPack(view.context)
            var installed = 0
            for (i in 0 until s.tracks.length.toInt()) {
                if (percussion.getOrElse(i) { false }) continue
                val ch = channels[i]
                RealisticSynth.setGain(ch, gains.getOrElse(i) { 1.0 }.toFloat())
                if (RealisticSynth.regions(ch) > 0) { installed++; continue }
                val sfz = pack.sfzFor(s.tracks[i].name.replace('\u00A0', ' '))
                if (sfz != null && RealisticSynth.load(ch, sfz)) installed++ else RealisticSynth.loadTestTone(ch)
            }
            val t0 = System.nanoTime()
            val count = runCatching { humanized.prepare(s, channels, percussion, compositionJson) }
                .onFailure { android.util.Log.w("BrasscribePlay", "humanization unavailable", it) }.getOrDefault(0)
            humanizedReady = count > 0
            android.util.Log.i("BrasscribePlay", "realistic tier: %d parts with installed instruments, %d humanized notes in %d ms, channels %s"
                .format(installed, count, (System.nanoTime() - t0) / 1_000_000, channels.toList()))
            view.api.midiEventsPlayedFilter = alphaTab.collections.List(MidiEventType.NoteOn, MidiEventType.NoteOff)
            _state.value = _state.value.copy(realistic = true, soundPackParts = installed, humanized = humanizedReady)
            if (_state.value.playing && humanizedReady) humanized.start(::channelAudible)
        } else {
            humanized.stop()
            view.api.midiEventsPlayedFilter = alphaTab.collections.List()
            RealisticSynth.allOff(); RealisticSynth.stop()
            _state.value = _state.value.copy(realistic = false, humanized = false)
        }
        applyVolumes()
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
        humanized.release()
        RealisticSynth.allOff()
        runCatching { view.api.stop() }
    }
}
