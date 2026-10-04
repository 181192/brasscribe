package no.brasscribe.play.score

import alphaTab.AlphaTabView
import alphaTab.LayoutMode
import alphaTab.PlayerMode
import alphaTab.ScrollMode
import alphaTab.collections.DoubleList
import alphaTab.core.ecmaScript.Uint8Array
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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
    /** The realistic instruments are being loaded (it takes a few seconds for a band). */
    val realisticLoading: Boolean = false,
    val keyShift: Int = 0,
    /** Parts playing a real instrument from the sound pack in the realistic tier. */
    val soundPackParts: Int = 0,
    /** The realistic tier plays humanized notes (the Rust core). */
    val humanized: Boolean = false,
    /** The band SoundFont replaced alphaTab's built-in one. */
    val bandSoundFont: Boolean = false,
    /**
     * No band sounds on this install: the basic tier (alphaTab's General MIDI set) plays. The UI shows
     * R.string.band_sounds_missing, with [bandSoundsExpected] (where the sounds were looked for) as detail.
     */
    val basicTier: Boolean = false,
    val bandSoundsExpected: String = "",
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
    private val reducedMotion: Boolean,
    private val core: no.brasscribe.play.model.CoreBridge = no.brasscribe.play.model.KotlinCoreBridge,
    /** Band SoundFont part map (sounds/mapping.json); null keeps alphaTab's General MIDI programs. */
    private val soundMap: BandSoundMap? = null,
    /**
     * A sideloaded band SoundFont; without one the phone SoundFont bundled in the APK is used
     * ([BandSoundFontFile]), and only without both does alphaTab keep its General MIDI SoundFont.
     */
    private val bandSoundFont: java.io.File? = null,
    /** The Composition the score came from, for humanization; asked for off the main thread, when the realistic sound starts. */
    private val compositionJson: () -> String? = { null },
) {
    val view: AlphaTabView = AlphaTabView(context, null)
    private var channels = IntArray(0)
    private var percussion: List<Boolean> = emptyList()
    private var gains = DoubleArray(0)
    private var sounds: List<TrackSound?> = emptyList()
    /** Parts sfizz plays in the realistic tier; every other part stays on alphaTab's band SoundFont. */
    private var sfizzParts: Set<Int> = emptySet()
    private val humanized = HumanizedPlayer(core)
    private var humanizedReady = false
    private val _state = MutableStateFlow(ScoreUiState())
    val state: StateFlow<ScoreUiState> = _state
    private var score: Score? = null
    private val writtenTransposition = HashMap<Int, Double>()
    private val _renders = MutableStateFlow(0)
    /** Counts finished renders: the music stand lays out its pages again after each one. */
    val renders: StateFlow<Int> = _renders
    private val innerScroll: android.widget.ScrollView? = view.findViewById(net.alphatab.R.id.innerScroll)

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
        // The shared output stage (gain + soft limiter) in front of alphaTab's output, on every new player.
        StagedSynthOutput.install(view.api)
        view.api.playerReady.on { StagedSynthOutput.install(view.api) }
        view.importantForAccessibility = android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        view.api.playerStateChanged.on { e ->
            val playing = e.state == PlayerState.Playing
            _state.value = _state.value.copy(playing = playing)
            view.post { if (!released) followFocus(playing) }
            if (_state.value.realistic && humanizedReady) {
                if (playing) humanized.start(::channelAudible) else humanized.stop()
            } else if (!playing) RealisticSynth.fadeOut()
        }
        view.api.playerPositionChanged.on { e ->
            if (_state.value.realistic && humanizedReady) humanized.position(humanized.secondsAt(e.currentTick), view.api.playbackSpeed)
        }
        // Channel volumes reset when the MIDI is regenerated (every render), so the balance follows it.
        // (api.midiLoaded cannot be used: in alphaTab 1.8.4 on Android its getter recurses forever.)
        // The engraving's size comes with the render; the surface is only measured to it on a later layout pass.
        view.api.renderFinished.on { e -> engravedWidth = e.totalWidth }
        view.api.postRenderFinished.on {
            applyVolumes(); overlays().forEach { it.refresh() }
            hideCredit()
            // After alphaTab's own handlers, so the stand reads this render's layout, not the last one.
            view.post { _renders.value++ }
            preloadSoundFont()
        }

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
                    is NoteOnEvent -> if (sfizzChannel(ev.channel.toInt()) && channelAudible(ev.channel.toInt())) RealisticSynth.noteOn(ev.channel.toInt(), ev.noteKey.toInt(), ev.noteVelocity.toInt())
                    is NoteOffEvent -> if (sfizzChannel(ev.channel.toInt())) RealisticSynth.noteOff(ev.channel.toInt(), ev.noteKey.toInt())
                }
            }
        }
    }

    /**
     * The music stand's layout (design/music-stand.md §3): a fixed number of bars per system, and the
     * stand turns the pages itself, so alphaTab neither scrolls to the cursor nor takes taps or keys (a
     * tap shows the controls, the stand's own surface over the view takes the drags, and a page
     * turner's arrows must not scroll the view by a screen). Null goes back to the ordinary score.
     * Only the layout is engraved again: the music keeps playing.
     */
    fun setStandLayout(barsPerRow: Int?) {
        val on = barsPerRow != null
        val rows = (barsPerRow ?: -1).toDouble()
        if (view.settings.display.barsPerRow == rows && on == (view.settings.player.scrollMode == ScrollMode.Off)) return
        view.settings.display.barsPerRow = rows
        view.settings.player.scrollMode = when {
            on -> ScrollMode.Off
            reducedMotion -> ScrollMode.OffScreen
            else -> ScrollMode.Continuous
        }
        view.settings.player.enableUserInteraction = !on
        view.api.updateSettings()
        view.descendantFocusability = if (on) android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS else android.view.ViewGroup.FOCUS_AFTER_DESCENDANTS
        if (_state.value.loaded) view.api.render()
    }

    /**
     * The engraved title block (title, composer, arranger, words, rights) on or off. The score upright shows it; on the
     * music stand and on a phone on its side the top band names the score, and the music needs the room (the block took a
     * third of it there). Shared and printed files are not engraved here, and keep theirs.
     */
    fun setTitleShown(on: Boolean) {
        if (SCORE_INFO.all { view.settings.notation.isNotationElementVisible(it) == on }) return
        for (e in SCORE_INFO) view.settings.notation.elements.set(e, on)
        view.api.updateSettings()
        if (_state.value.loaded) view.api.render()
    }

    /** The engraved systems in view pixels (alphaTab's layout units times the display density). */
    fun standSystems(): List<StandSystem> {
        val systems = view.api.boundsLookup?.staffSystems ?: return emptyList()
        val f = view.resources.displayMetrics.density
        return (0 until systems.length.toInt()).mapNotNull { i ->
            val sys = systems[i]
            val bars = sys.bars
            if (bars.length.toInt() == 0) return@mapNotNull null
            val b = sys.realBounds
            StandSystem((b.y * f).toFloat(), ((b.y + b.h) * f).toFloat(),
                bars[0].index.toInt() + 1, bars[bars.length.toInt() - 1].index.toInt() + 1)
        }
    }

    /** Width of the last finished engraving in alphaTab's layout units. */
    private var engravedWidth = 0.0

    /**
     * alphaTab signs every engraving with "rendered by alphaTab" under the last system. The score is the
     * music alone (alphaTab is credited in About, as with BarSnippet), so the surface is cut off there.
     * The clip is taken from the engraving, never from the surface's current size: when a render finishes
     * before the surface has been laid out to it (the first render of a freshly opened score, often), the
     * surface is still 0 wide and a clip from that width hides the whole score.
     */
    private fun hideCredit() {
        val surface = view.findViewById<android.view.View>(net.alphatab.R.id.renderSurface) ?: return
        val systems = view.api.boundsLookup?.staffSystems
        if (systems == null || systems.length.toInt() == 0) { surface.clipBounds = null; return }
        // The system's real bounds take in the credit line; its visual bounds end with the music.
        val b = systems[systems.length.toInt() - 1].visualBounds
        val (right, bottom) = creditClip(engravedWidth, b.y + b.h, view.resources.displayMetrics.density)
        surface.clipBounds = android.graphics.Rect(0, 0, right, bottom)
    }

    /** Height of the engraving in view pixels. */
    fun standContentHeight(): Float = view.findViewById<android.view.View>(net.alphatab.R.id.renderSurface)?.height?.toFloat() ?: 0f

    /** Shows the stand's window from [y] view pixels down. */
    fun scrollStandTo(y: Int) { innerScroll?.scrollTo(0, y.coerceAtLeast(0)) }

    /** A parsed score and its playback plan, built off the main thread and applied on it. */
    private class Parsed(
        val score: Score, val names: List<String>, val shown: Set<Int>, val percussion: List<Boolean>,
        val channels: IntArray, val sounds: List<TrackSound?>, val gains: DoubleArray, val band: Boolean,
    )

    /** The thread the last parse ran on, for the test that it is never the main thread. */
    @androidx.annotation.VisibleForTesting
    @Volatile internal var parsedOn: Thread? = null

    /**
     * Parses MusicXML (or any format alphaTab reads) and renders the given tracks (default: the first).
     * The parse and the playback plan run on [Dispatchers.Default] (a band score's MusicXML is about
     * 2 MB); the result is applied and rendered on the main thread. Cancelling the caller (the screen
     * left while the score loads) leaves the controller unloaded, with no error and no render.
     */
    suspend fun load(bytes: ByteArray, pick: (List<String>) -> Set<Int> = { setOf(0) }) {
        val settings = view.settings
        val context = view.context
        val p = try {
            withContext(Dispatchers.Default) { parse(bytes, pick, settings, context) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            _state.value = _state.value.copy(error = e.message ?: e.javaClass.simpleName)
            return
        }
        if (released) return
        try {
            val s = p.score
            score = s
            collectMarks(s)
            colourUncertainty(s)
            s.tracks.forEach { t -> writtenTransposition[t.index.toInt()] = t.staves[0].displayTranspositionPitch }
            percussion = p.percussion
            channels = p.channels
            sounds = p.sounds
            gains = p.gains
            _state.value = _state.value.copy(
                loaded = true, error = null, title = s.title, parts = p.names, shown = p.shown,
                totalBars = s.masterBars.length.toInt(), channels = p.channels.toList(), basicTier = !p.band,
                bandSoundsExpected = if (p.band) "" else "assets/${BandSoundFontFile.ASSET}; ${context.getExternalFilesDir(null)?.resolve("sounds")}",
            )
            render()
        } catch (e: Throwable) {
            _state.value = _state.value.copy(error = e.message ?: e.javaClass.simpleName)
        }
    }

    private suspend fun parse(bytes: ByteArray, pick: (List<String>) -> Set<Int>, settings: alphaTab.Settings, context: Context): Parsed {
        parsedOn = Thread.currentThread()
        val marked = markVeryUncertain(bytes)
        currentCoroutineContext().ensureActive()
        val s = AlphaTabMusicXml.parse(marked, settings)
        currentCoroutineContext().ensureActive()
        val names = BandPlan.partNames(s)
        val shown = pick(names).filter { it < names.size }.toSet().ifEmpty { setOf(0) }
        // Banks only exist in the band SoundFont; alphaTab's General MIDI one has bank 0 alone, and a
        // pitched channel on a missing bank is silent, so the basic tier keeps bank 0.
        val band = bandSoundFont?.isFile == true || BandSoundFontFile.available(context)
        return prepareSound(s, names, shown, band, PercussionKit.programs(bytes.decodeToString()))
    }

    /** The playback plan ([BandPlan]), which "Listen to this bar" plays too. */
    private fun prepareSound(s: Score, names: List<String>, shown: Set<Int>, band: Boolean, kits: List<Int?>): Parsed {
        val plan = BandPlan.apply(s, names, soundMap, band, kits)
        return Parsed(s, names, shown, plan.percussion, plan.channels, plan.sounds, plan.gains, band)
    }

    private var soundFontRequested = false
    /** The band SoundFont is in alphaTab's synth, or there is none to load (the basic tier). */
    private var soundFontSettled = false
    /** What to play once the band SoundFont has loaded: the Play that asked for it. */
    private var afterSoundFont: (() -> Unit)? = null

    /** The band SoundFont this score read, weakly: a test checks nothing keeps it once alphaTab has it. */
    @androidx.annotation.VisibleForTesting
    @Volatile internal var soundFontBytes: java.lang.ref.WeakReference<ByteArray>? = null

    private var preloadScheduled = false

    /**
     * The band SoundFont is not loaded when the score opens: alphaTab holds about three times the file
     * (some 220 MB of heap for the 73 MB phone SoundFont), and a score opened and left at once, or one
     * opened after another, need not pay for it. Once the score has shown for [SOUNDFONT_PRELOAD_MS]
     * it loads in the background, so Play starts at once; a Play before that loads it ([withSoundFont]).
     */
    private fun preloadSoundFont() {
        if (preloadScheduled || soundFontRequested) return
        preloadScheduled = true
        view.postDelayed({ if (!released) loadBandSoundFont() }, SOUNDFONT_PRELOAD_MS)
    }

    /**
     * Runs [action] with the band SoundFont in the synth, loading it first if it is not yet (a Play
     * right after the score opened waits some 0.4 s for it). A second call while it loads replaces the
     * first (Play, then Pause before the sound came, plays nothing).
     */
    private fun withSoundFont(action: () -> Unit) {
        if (soundFontSettled) { action(); return }
        afterSoundFont = action
        loadBandSoundFont()
    }

    /** The band SoundFont is in (or will not come): runs the Play waiting for it. */
    private fun soundFontSettled() {
        soundFontSettled = true
        val action = afterSoundFont ?: return
        afterSoundFont = null
        if (!released) action()
    }

    /** Replaces alphaTab's built-in SoundFont with the band SoundFont (found and read off the UI thread). */
    private fun loadBandSoundFont() {
        if (soundFontRequested) return
        soundFontRequested = true
        val context = view.context
        Thread({
            val t0 = System.nanoTime()
            val sf = BandSoundFontFile.resolve(context, bandSoundFont?.takeIf { it.isFile } ?: BandSoundFontFile.sideloaded(context))
            if (sf == null) { view.post { soundFontSettled() }; return@Thread }
            // One copy only, handed over and then dropped: alphaTab copies the sample chunk into its own
            // buffer while it loads, so nothing here may keep this array (or the handler below) alive.
            var bytes: ByteArray? = runCatching { sf.readBytes() }.getOrElse {
                android.util.Log.w("BrasscribePlay", "band SoundFont unreadable", it)
                view.post { soundFontSettled() }
                return@Thread
            }
            val megabytes = bytes!!.size shr 20
            soundFontBytes = java.lang.ref.WeakReference(bytes)
            var listening = false
            fun attempt(tries: Int) {
                if (released) { bytes = null; return }
                // api.loadSoundFont(ByteArray) returns false on Android (AndroidUiFacade's `when` compares the
                // value, not the type), so the synth gets the bytes directly.
                val player = view.api.player
                val data = bytes ?: return
                val ok = player != null && runCatching {
                    if (!listening) {
                        listening = true
                        player.soundFontLoaded.on {
                            // alphaTab's synth thread keeps the message it last ran, the load with the file's
                            // bytes, until it takes another: send it a no-op so those bytes can go now.
                            runCatching { player.masterVolume = player.masterVolume }
                            _state.value = _state.value.copy(bandSoundFont = true)
                            android.util.Log.i("BrasscribePlay", "band SoundFont %s (%d MB) loaded by alphaTab in %d ms"
                                .format(sf.name, megabytes, (System.nanoTime() - t0) / 1_000_000))
                            view.post { soundFontSettled() }
                        }
                    }
                    player.loadSoundFont(Uint8Array(data.asUByteArray()), false); true
                }.getOrDefault(false)
                if (ok) bytes = null
                else if (tries > 0) view.postDelayed({ attempt(tries - 1) }, 200)
                else {
                    bytes = null
                    android.util.Log.w("BrasscribePlay", "alphaTab player not ready for the band SoundFont")
                    soundFontSettled()
                }
            }
            view.post { attempt(50) }
        }, "band-soundfont").start()
    }

    /** Applies each part's balance (and mutes alphaTab's copy of the parts sfizz plays). */
    private fun applyVolumes() {
        val s = score ?: return
        for (i in 0 until s.tracks.length.toInt()) {
            val silent = _state.value.realistic && i in sfizzParts
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

    /** The instrument key the shown part is written for ("B♭", "E♭"), or null for concert-pitch parts. */
    fun writtenKey(): String? {
        val i = _state.value.shown.singleOrNull() ?: return null
        val t = writtenTransposition[i]?.toInt() ?: return null
        return when (Math.floorMod(-t, 12)) { 2 -> "B♭"; 9 -> "E♭"; 7 -> "F"; 3 -> "A"; else -> null }
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
        StagedSynthOutput.install(view.api)
        if (no.brasscribe.play.BuildConfig.DEBUG) {
            if (_state.value.playing) android.util.Log.i("BrasscribePlay", "note-ons per channel: $notesPerChannel")
            else if (!_state.value.realistic) { notesPerChannel.clear(); view.api.midiEventsPlayedFilter = alphaTab.collections.List(MidiEventType.NoteOn) }
        }
        if (_state.value.playing) { fadeThen { view.api.playPause() }; return }
        // Play again before the SoundFont came: the player changed their mind, nothing plays.
        if (afterSoundFont != null) { afterSoundFont = null; return }
        withSoundFont {
            if (!view.api.isReadyForPlayback) android.util.Log.w("BrasscribePlay", "player not ready (state ${view.api.playerState})")
            view.api.playPause()
        }
    }
    fun stop() { RealisticSynth.fadeOut(); fadeThen { view.api.stop() } }

    /**
     * Stop and pause: the band fades out over [STOP_FADE_MS] before the player stops, so a note
     * is not cut with a click and a long release does not ring on after the user asked for
     * silence. Seeking keeps the natural release (it does not come through here).
     */
    private var fading: android.animation.ValueAnimator? = null
    private fun fadeThen(action: () -> Unit) {
        fading?.cancel()
        val volume = view.api.masterVolume
        fading = android.animation.ValueAnimator.ofFloat(1f, 0f).apply {
            duration = STOP_FADE_MS
            addUpdateListener { view.api.masterVolume = volume * (it.animatedValue as Float) }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                private var done = false
                private fun finish() {
                    if (done) return
                    done = true
                    action()
                    view.api.masterVolume = volume
                    fading = null
                }
                override fun onAnimationEnd(animation: android.animation.Animator) = finish()
                override fun onAnimationCancel(animation: android.animation.Animator) = finish()
            })
            start()
        }
    }

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

    private fun sfizzChannel(channel: Int): Boolean = channels.indexOf(channel).let { it >= 0 && it in sfizzParts }

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
        withSoundFont { view.api.play() }
    }

    fun setCountIn(on: Boolean) {
        view.api.countInVolume = if (on) METRONOME_VOLUME else 0.0
        _state.value = _state.value.copy(countIn = on)
    }

    fun setMetronome(on: Boolean) {
        view.api.metronomeVolume = if (on) METRONOME_VOLUME else 0.0
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
        val (found, adLib) = no.brasscribe.play.score.collectMarks(s)
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

    private fun colourUncertainty(s: Score) = colourMarks(s, marks, palette)

    /**
     * Realistic tier on: every pitched part plays an SFZ instrument through sfizz on its own channel
     * with its band balance, humanized by the core; alphaTab keeps the kit, metronome and count-in.
     */
    fun setRealistic(on: Boolean): Boolean {
        val s = score ?: return false
        realisticWanted = on
        realisticJob?.cancel()
        realisticJob = null
        if (!on) {
            humanized.stop()
            view.api.midiEventsPlayedFilter = alphaTab.collections.List()
            sfizzParts = emptySet()
            _state.value = _state.value.copy(realistic = false, humanized = false, realisticLoading = false)
            applyVolumes()
            // After any load still running: the lifecycle thread takes them in order. The instruments stay
            // loaded while the score is open, so turning it on again is quick.
            RealisticSynth.post { RealisticSynth.allOff(); RealisticSynth.stop() }
            return true
        }
        // Loading a band's instruments and humanizing every note takes seconds: in the background, with the
        // choice shown as loading meanwhile. alphaTab is only touched here, on the main thread.
        val channels = channels.copyOf()
        val percussion = percussion
        val sounds = sounds
        val gains = gains
        val context = view.context.applicationContext
        _state.value = _state.value.copy(realisticLoading = true)
        realisticJob = scope.launch {
            val ready = try {
                withContext(RealisticSynth.lifecycle) {
                    if (!RealisticSynth.start()) return@withContext null
                    val pack = SoundPack(context)
                    val playing = HashSet<Int>()
                    for (i in 0 until s.tracks.length.toInt()) {
                        ensureActive()
                        if (percussion.getOrElse(i) { false }) continue
                        val ch = channels[i]
                        // One SFZ per part sounds one target: single_voice_gain_db, not the layered preset's gain.
                        RealisticSynth.setGain(ch, (sounds.getOrNull(i)?.singleVoiceGain ?: gains.getOrElse(i) { 1.0 }).toFloat())
                        // A part without an installed SFZ stays on the band SoundFont (never a test tone).
                        val sfz = sounds.getOrNull(i)?.let { pack.sfzFor(it) }
                        if (sfz != null && RealisticSynth.load(ch, sfz)) playing += i
                    }
                    ensureActive()
                    val t0 = System.nanoTime()
                    val skip = percussion.indices.map { it !in playing }
                    val count = runCatching { humanized.prepare(s, channels, skip, compositionJson()) }
                        .onFailure { android.util.Log.w("BrasscribePlay", "humanization unavailable", it) }.getOrDefault(0)
                    android.util.Log.i("BrasscribePlay", "realistic tier: %d parts with installed instruments, %d humanized notes in %d ms, channels %s"
                        .format(playing.size, count, (System.nanoTime() - t0) / 1_000_000, channels.toList()))
                    playing to count
                }
            } finally {
                _state.value = _state.value.copy(realisticLoading = false)
            }
            if (ready == null || released || !realisticWanted || score !== s) return@launch
            val (playing, count) = ready
            sfizzParts = playing
            humanizedReady = count > 0
            view.api.midiEventsPlayedFilter = alphaTab.collections.List(MidiEventType.NoteOn, MidiEventType.NoteOff)
            _state.value = _state.value.copy(realistic = true, soundPackParts = playing.size, humanized = humanizedReady)
            if (_state.value.playing && humanizedReady) humanized.start(::channelAudible)
            applyVolumes()
        }
        return true
    }

    private val appContext: Context = context.applicationContext
    private val audio: android.media.AudioManager? = appContext.getSystemService(android.media.AudioManager::class.java)

    /** A call, another player or a voice assistant takes the sound: the score pauses, as a music player does. */
    private val focusRequest = android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN)
        .setAudioAttributes(android.media.AudioAttributes.Builder().setUsage(android.media.AudioAttributes.USAGE_MEDIA)
            .setContentType(android.media.AudioAttributes.CONTENT_TYPE_MUSIC).build())
        .setOnAudioFocusChangeListener({ change ->
            if (change == android.media.AudioManager.AUDIOFOCUS_LOSS || change == android.media.AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) pauseForSystem()
        }, android.os.Handler(android.os.Looper.getMainLooper()))
        .build()

    /** Headphones pulled out (or Bluetooth gone): pause rather than play on through the speaker. */
    private val noisy = object : android.content.BroadcastReceiver() {
        override fun onReceive(context: Context, intent: android.content.Intent) {
            if (intent.action == android.media.AudioManager.ACTION_AUDIO_BECOMING_NOISY) pauseForSystem()
        }
    }
    private var focusHeld = false

    /** Holds the audio focus and listens for unplugged headphones while the score plays; lets both go when it stops. */
    private fun followFocus(playing: Boolean) {
        if (playing == focusHeld) return
        focusHeld = playing
        if (playing) {
            val granted = audio?.requestAudioFocus(focusRequest) != android.media.AudioManager.AUDIOFOCUS_REQUEST_FAILED
            androidx.core.content.ContextCompat.registerReceiver(appContext, noisy,
                android.content.IntentFilter(android.media.AudioManager.ACTION_AUDIO_BECOMING_NOISY), androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED)
            // During a phone call the focus is refused: the score does not play over it.
            if (!granted) pauseForSystem()
        } else {
            audio?.abandonAudioFocusRequest(focusRequest)
            runCatching { appContext.unregisterReceiver(noisy) }
        }
    }

    private fun pauseForSystem() {
        if (!released && _state.value.playing) togglePlay()
    }

    /** Main-thread work for the controller: cancelled when it is released. */
    private val scope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + Dispatchers.Main.immediate)
    private var realisticJob: kotlinx.coroutines.Job? = null
    /** The realistic sound was last asked for (on) or turned off. */
    private var realisticWanted = false

    /** Standard MIDI file of the loaded score, generated by alphaTab. */
    fun midiBytes(): ByteArray? = midiSource()?.bytes()

    /**
     * The loaded score's MIDI and the parts on screen, without the view: the export screen keeps this
     * once the score screen has gone, and not the controller, whose synth holds the band SoundFont.
     */
    fun midiSource(): ScoreMidi? {
        val s = score ?: return null
        return ScoreMidi(s, view.settings, _state.value.shown)
    }

    /** Set once the screen let go of the controller: a parse that ends later is dropped, and nothing waiting for the SoundFont plays. */
    private var released = false

    fun release() {
        released = true
        afterSoundFont = null
        realisticJob?.cancel()
        scope.cancel()
        humanized.release()
        followFocus(playing = false)
        runCatching { view.api.stop() }
        // The output stream closes and the instruments (about 100 MB for a band) are freed: after any load
        // still running for this score, and before the next score's, on the tier's own thread.
        RealisticSynth.post { RealisticSynth.allOff(); RealisticSynth.stop(); RealisticSynth.unloadAll() }
    }
}

/** A score's MIDI, generated by alphaTab on demand, and the parts that were on screen. */
class ScoreMidi(private val score: Score, private val settings: alphaTab.Settings, val shown: Set<Int>) {
    fun bytes(): ByteArray {
        val midi = MidiFile()
        MidiFileGenerator(score, settings, AlphaSynthMidiFileHandler(midi, true)).generate()
        return midi.toBinary().buffer.asByteArray()
    }
}

/** Theme colours of the notation (design tokens, ARGB). */
data class ScorePalette(
    val paper: Int, val ink: Int, val staff: Int, val cursor: Int, val uncertain: Int, val veryUncertain: Int,
    val loopTint: Int, val highContrast: Boolean, val adlibTint: Int = loopTint,
    val selectionTint: Int = adlibTint, val selectionEdge: Int = ink,
)

/** The engraved title block: title, subtitle, composer, words, music, copyright. */
private val SCORE_INFO = listOf(
    alphaTab.NotationElement.ScoreTitle, alphaTab.NotationElement.ScoreSubTitle, alphaTab.NotationElement.ScoreArtist,
    alphaTab.NotationElement.ScoreAlbum, alphaTab.NotationElement.ScoreWords, alphaTab.NotationElement.ScoreMusic,
    alphaTab.NotationElement.ScoreWordsAndMusic, alphaTab.NotationElement.ScoreCopyright,
)

internal const val BOXED_QUESTION = "\u2370"
/** Blank text in place of a mark: alphaTab still reserves the text band above the note. */
internal const val MARK_SPACE = "\u2003\u2003"
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

private const val STOP_FADE_MS = 80L

/** How long a score shows before the band SoundFont loads without a Play asking for it. */
private const val SOUNDFONT_PRELOAD_MS = 1_500L

/**
 * The surface's clip that cuts off alphaTab's credit line: the engraving's full width ([engravedWidth],
 * alphaTab units) and down to the end of the last system's music ([musicBottom], alphaTab units), in view
 * pixels at [density]. Returned as (right, bottom); the clip's left and top are 0.
 */
internal fun creditClip(engravedWidth: Double, musicBottom: Double, density: Float): Pair<Int, Int> {
    val right = kotlin.math.ceil(engravedWidth * density).toInt()
    val bottom = kotlin.math.ceil(musicBottom * density).toInt()
    // Without a width from the render (none reported), leave the sides open rather than hide the score.
    return (if (right > 0) right else Int.MAX_VALUE / 2) to bottom
}

/** alphaTab's metronome and count-in volume: the click lands at the shared level through the output stage. */
private val METRONOME_VOLUME = no.brasscribe.play.audio.PlaybackLevels.factor(no.brasscribe.play.audio.PlaybackLevels.METRONOME_GAIN_DB).toDouble()
