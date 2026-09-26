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
import alphaTab.model.BeatStyle
import alphaTab.model.BeatSubElement
import alphaTab.model.NoteStyle
import alphaTab.model.NoteSubElement
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
    /** Beat within the bar (1-based) and the bar's beat count, for the beat counter. */
    val beat: Int = 1,
    val beatsInBar: Int = 4,
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
            // The overlay draws the uncertainty marks from the note heads.
            core.includeNoteBounds = true
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
        view.api.postRenderFinished.on { applyVolumes(); overlays().forEach { it.refresh() } }

        view.api.playedBeatChanged.on { beat ->
            val mb = beat.voice.bar.masterBar
            val beats = mb.timeSignatureNumerator.toInt().coerceAtLeast(1)
            val beatTicks = 960.0 * 4 / mb.timeSignatureDenominator.coerceAtLeast(1.0)
            val n = (beat.playbackStart / beatTicks).toInt() + 1
            _state.value = _state.value.copy(bar = beat.voice.bar.index.toInt() + 1, beat = n.coerceIn(1, beats), beatsInBar = beats)
        }
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
            val s = ScoreLoader.loadScoreFromBytes(Uint8Array(markVeryUncertain(bytes).asUByteArray()), view.settings)
            score = s
            collectMarks(s)
            colourUncertainty(s)
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
            runCatching { view.api.clearPlaybackRangeHighlight() }
        } else {
            // The loop tint over the looped bars (loop-tint), drawn by alphaTab's selection layer.
            runCatching {
                val staff = s.tracks[_state.value.shown.minOrNull() ?: 0].staves[0]
                val first = staff.bars[(range.first - 1).coerceIn(0, staff.bars.length.toInt() - 1)].voices[0].beats[0]
                val lastVoice = staff.bars[(range.last - 1).coerceIn(0, staff.bars.length.toInt() - 1)].voices[0]
                view.api.highlightPlaybackRange(first, lastVoice.beats[lastVoice.beats.length.toInt() - 1])
            }
            val bars = s.masterBars
            val first = bars[(range.first - 1).coerceIn(0, bars.length.toInt() - 1)]
            val lastIndex = range.last.coerceIn(1, bars.length.toInt())
            val end = if (lastIndex < bars.length.toInt()) bars[lastIndex].start else bars[lastIndex - 1].start + bars[lastIndex - 1].calculateDuration()
            view.api.playbackRange = PlaybackRange().apply { startTick = first.start; endTick = end }
            view.api.isLooping = true
            view.api.tickPosition = first.start
        }
        _state.value = _state.value.copy(loop = range)
        tints.loop = range
        tints.invalidate()
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
     * Notation colours from the theme tokens. alphaTab engraves in black on a transparent background,
     * which is unreadable on the dark and high-contrast surfaces, so paper and ink are set explicitly.
     * Colours are ARGB ints (PlayTokens through Color.toArgb).
     */
    fun setNotationColors(p: ScorePalette) {
        palette = p
        view.setBackgroundColor(p.paper)
        view.beatCursorFillColor = p.cursor
        // The cursor views sit over the notation, so the tints are translucent colours that read as
        // the token tint over the paper (cursor-tint: the cursor at 20 %; loop-tint for the loop).
        view.barCursorFillColor = if (p.highContrast) 0 else (p.cursor and 0x00FFFFFF) or (0x33 shl 24)
        view.selectionFillColor = if (p.highContrast) 0 else overlayFor(p.loopTint, p.paper, 0.45)
        view.settings.display.resources.apply {
            mainGlyphColor = p.ink.toAlphaTabColor()
            secondaryGlyphColor = p.ink.toAlphaTabColor()
            scoreInfoColor = p.ink.toAlphaTabColor()
            staffLineColor = p.staff.toAlphaTabColor()
            barSeparatorColor = p.staff.toAlphaTabColor()
            barNumberColor = p.staff.toAlphaTabColor()
        }
        view.api.updateSettings()
        overlays().forEach { it.palette = p }
        score?.let { colourUncertainty(it) }
        if (_state.value.loaded) render() else overlay.invalidate()
    }

    private var palette: ScorePalette? = null

    /** The overlay with the uncertainty marks, the ad-lib tint and the review ring. */
    private val tints: NotationOverlay = NotationOverlay.attach(view, under = true)
    val overlay: NotationOverlay = NotationOverlay.attach(view, under = false)
    private fun overlays() = listOf(tints, overlay)
    private var marks: Map<alphaTab.model.Beat, Boolean> = emptyMap()

    /**
     * Finds the marked beats (their "?" text) and the free-time bars ("ad lib." up to "a tempo"),
     * then blanks the small text marks so alphaTab keeps their band and the overlay draws them.
     */
    private fun collectMarks(s: Score) {
        val found = HashMap<alphaTab.model.Beat, Boolean>()
        val adLib = HashSet<Int>()
        for (t in 0 until s.tracks.length.toInt()) for (st in s.tracks[t].staves) {
            var free = false
            for (bar in st.bars) {
                for (voice in bar.voices) for (beat in voice.beats) {
                    when (beat.text?.trim()?.lowercase()) {
                        "?" -> { found[beat] = false; beat.text = MARK_SPACE }
                        BOXED_QUESTION -> { found[beat] = true; beat.text = MARK_SPACE }
                        "ad lib.", "ad lib", "ad. lib." -> free = true
                        "a tempo" -> free = false
                    }
                }
                if (free) adLib += bar.index.toInt()
            }
        }
        marks = found
        overlay.marks = found
        tints.adLibBars = adLib
    }

    /** Rings one note of the rendered score (the review's note card). */
    fun ringNote(bar: Int, noteIndexInBar: Int) {
        val s = score ?: return
        val staff = s.tracks[_state.value.shown.minOrNull() ?: 0].staves[0]
        val b = if (bar in 1..staff.bars.length.toInt()) staff.bars[bar - 1] else null
        val beats = b?.voices?.let { v -> if (v.length > 0) (0 until v[0].beats.length.toInt()).map { v[0].beats[it] } else null }.orEmpty().filter { !it.isRest }
        overlay.ring = beats.getOrNull(noteIndexInBar)
        overlay.invalidate()
    }

    /**
     * Uncertain notes carry a "?" above them (MusicXML <words>) and, below 0.4 confidence, a boxed
     * "?" (enclosure="rectangle"), which alphaTab does not draw. The boxed one becomes U+2370, the
     * boxed question mark, so it keeps its shape in the score.
     */
    private fun markVeryUncertain(bytes: ByteArray): ByteArray {
        val xml = bytes.toString(Charsets.UTF_8)
        if (!xml.contains("enclosure=\"rectangle\"")) return bytes
        return VERY_UNCERTAIN_WORDS.replace(xml, "<words>$BOXED_QUESTION</words>").toByteArray(Charsets.UTF_8)
    }

    /** Colours each marked note (head, stem, flags, accidentals) and its mark: uncertain or very uncertain. */
    private fun colourUncertainty(s: Score) {
        val p = palette ?: return
        val uncertain = p.uncertain.toAlphaTabColor()
        val very = p.veryUncertain.toAlphaTabColor()
        for (t in 0 until s.tracks.length.toInt()) for (st in s.tracks[t].staves) for (bar in st.bars) for (voice in bar.voices) {
            for (beat in voice.beats) {
                val colour = when (marks[beat]) { false -> uncertain; true -> very; null -> null } ?: continue
                beat.style = BeatStyle().apply {
                    for (e in listOf(BeatSubElement.Effects, BeatSubElement.StandardNotationEffects, BeatSubElement.StandardNotationStem,
                        BeatSubElement.StandardNotationFlags)) colors.set(e, colour)
                }
                for (n in beat.notes) n.style = NoteStyle().apply {
                    for (e in listOf(NoteSubElement.StandardNotationNoteHead, NoteSubElement.StandardNotationAccidentals,
                        NoteSubElement.StandardNotationEffects)) colors.set(e, colour)
                }
            }
        }
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

/** Theme colours of the notation (design tokens, ARGB). */
data class ScorePalette(
    val paper: Int, val ink: Int, val staff: Int, val cursor: Int, val uncertain: Int, val veryUncertain: Int,
    val loopTint: Int, val highContrast: Boolean, val adlibTint: Int = loopTint,
)

private const val BOXED_QUESTION = "\u2370"
/** Blank text in place of a mark: alphaTab still reserves the text band above the note. */
private const val MARK_SPACE = "\u2003\u2003"
private val VERY_UNCERTAIN_WORDS = Regex("""<words\b[^>]*enclosure="rectangle"[^>]*>\?</words>""")

/** A colour with [alpha] that, drawn over [paper], gives [tint]. */
fun overlayFor(tint: Int, paper: Int, alpha: Double): Int {
    fun ch(c: Int, shift: Int) = (c shr shift) and 0xFF
    fun solve(shift: Int) = ((ch(tint, shift) - ch(paper, shift) * (1 - alpha)) / alpha).toInt().coerceIn(0, 255)
    return ((alpha * 255).toInt() shl 24) or (solve(16) shl 16) or (solve(8) shl 8) or solve(0)
}

private fun Int.toAlphaTabColor() = alphaTab.model.Color(
    ((this shr 16) and 0xFF).toDouble(),
    ((this shr 8) and 0xFF).toDouble(),
    (this and 0xFF).toDouble(),
    ((this ushr 24) and 0xFF).toDouble(),
)
