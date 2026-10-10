package no.brasscribe.play.fret

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.layout.onSizeChanged
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.calculateEndPadding
import androidx.compose.foundation.layout.calculateStartPadding
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.platform.LocalView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeColors
import no.brasscribe.design.BrasscribeScore
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.engine.Tab
import no.brasscribe.play.engine.TabLayout
import no.brasscribe.play.ui.BcIcon
import no.brasscribe.play.ui.InfoNote
import no.brasscribe.play.ui.OutlineButton
import no.brasscribe.play.ui.PlainButton
import no.brasscribe.play.ui.PlayTopBar
import no.brasscribe.play.ui.currentLang
import kotlin.math.roundToInt

/** A tab ready to show: the page, what the page says about its own notes, the data when the computer gave it, and the marks. */
class TabSheet(val musicXml: String, val index: TabIndex, val tab: Tab?, val marks: TabMarks) {
    val layout: TabLayout? get() = tab?.layout?.takeIf { it.id != null } ?: when {
        index.tabStaff == null -> TabLayout.NOTATION
        index.staves > 1 -> TabLayout.TAB_AND_NOTATION
        else -> TabLayout.TAB
    }

    /** The tuning's id ("drop-d") when it is one the app has words for; else the name the page or the data gives. */
    val tuning: String get() = tab?.preset?.let(SongCheck::tuningOf)
        ?: SongFacts.OPEN_STRINGS.entries.firstOrNull { it.value == SongFacts.openStrings(musicXml) }?.key?.let(SongCheck::tuningOf)
        ?: tab?.instrument?.tuning?.name ?: index.tuningName ?: FrettedInstrument.STANDARD_TUNING

    val capo: Int get() = tab?.instrument?.capo ?: index.capo

    /** The strings of the instrument, as the data or the page's staff tuning has them; four when neither says. */
    val strings: Int get() = tab?.instrument?.tuning?.strings?.size?.takeIf { it > 0 } ?: SongFacts.openStrings(musicXml).size.takeIf { it > 0 } ?: 4

    /** Quarter notes a minute. */
    val tempo: Int? get() = tab?.tempoBpm?.let { Math.round(it).toInt() } ?: index.tempo

    companion object {
        /** Reads the page, and asks for the data with [tab]; a computer that is away leaves the page's own marks. */
        suspend fun read(musicXml: String, tab: suspend () -> Tab?): TabSheet {
            val data = try {
                withContext(Dispatchers.IO) { tab() }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.w(PlayViewModel.TAG, "the tab's notes could not be read; the marks are the page's own", e)
                null
            }
            return withContext(Dispatchers.Default) {
                val index = TabIndex.parse(musicXml)
                TabSheet(musicXml, index, data, TabMarks.of(index, data))
            }
        }
    }
}

/**
 * Where the player was in each song, and the size the tab is read at, while the app runs: the tab view
 * comes back to them after a visit to Check the song. (A turn of the phone and a stopped app are the
 * saved state's.)
 */
internal object TabPlaces {
    private val bars = HashMap<String, Int>()
    @Volatile var zoom: Int = 100

    /** The bar (counted from 0) [song] was last read at; 0 for a song not read yet. */
    fun bar(song: String): Int = synchronized(bars) { bars[song] ?: 0 }

    fun keep(song: String, bar: Int) = synchronized(bars) { bars[song] = bar }

    fun forget() = synchronized(bars) { bars.clear(); zoom = 100 }
}

/** The tab on screen, for the tests that look at its engraving. */
@androidx.annotation.VisibleForTesting
internal object TabScreenProbe {
    @Volatile var view: TabView? = null
    /** The size the screen wants the page at; the view on screen has it once it has been made. */
    @Volatile var wanted: Double = 0.0
    /** Views made so far. */
    @Volatile var made: Int = 0
}

/** The tab's colours from the theme: ink numerals, the lines in the string colour, the doubt colour and its wash. */
internal fun tabPalette(c: BrasscribeColors) = TabPalette(
    paper = c.bg.toArgb(), ink = c.ink.toArgb(), string = c.staff.toArgb(), uncertain = c.uncertain.toArgb(),
    uncertainTint = when {
        c.isHighContrast -> null
        c.bg.luminance() > 0.5f -> TabTokens.UNCERTAIN_TINT_LIGHT
        else -> TabTokens.UNCERTAIN_TINT_DARK
    },
    cursor = c.cursor.toArgb(), cursorTint = c.cursorTint.toArgb().takeIf { !c.isHighContrast },
    repeat = c.loopEdge.toArgb(), repeatBand = c.loopTint.toArgb().takeIf { !c.isHighContrast },
)

/**
 * The tab (design/fretscribe/system.md §3), to read: the page engraved full width, the tuning in a chip
 * above it, and under that what there is to check. A "?" stands above every note Fretscribe is not sure
 * of and a boxed "!" above a note with no place; each can be tapped, or reached with the keyboard or a
 * screen reader, and says which note it is. The page gets more lines of fewer bars as it is made larger.
 *
 * It is also where the song is practised (design/fretscribe/flows.md §9): the recording is the sound, a
 * cursor stands at the beat it is at and the page follows it, and the player under the tab ([PracticeBar])
 * slows it down with its pitch kept and repeats the bars chosen. Space plays and pauses; with the screen or
 * the tab in focus, the left arrow goes back to the start of the repeat (a bar back when nothing is repeated)
 * and the right arrow a bar on.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TabScreen(vm: PlayViewModel) {
    val result by vm.result.collectAsState()
    val source by vm.source.collectAsState()
    val c = BrasscribeTheme.colors
    val context = LocalContext.current
    val resources = LocalResources.current
    val r = result ?: return
    val sheet by produceState<TabSheet?>(null, r.musicXml, r.jobId) {
        value = TabSheet.read(r.musicXml) { r.jobId?.let { id -> vm.container.engine()?.tab(id) } }
    }
    // The size and the bar being read are kept for the song: through a turn of the phone, a visit to Check the song, and the app being stopped.
    val song = r.jobId ?: r.musicXml.hashCode().toString()
    var zoom by rememberSaveable { mutableIntStateOf(TabPlaces.zoom) }
    var reading by rememberSaveable(song) { mutableIntStateOf(TabPlaces.bar(song)) }
    // The player scrolled up to a header that scrolls with the page: a new engraving (a zoom, a turn) leaves it in view.
    var headerShown by rememberSaveable(song) { mutableStateOf(false) }
    // With a screen reader that is explored by touch (TalkBack) the page opens at its top, the header first, so it is
    // read in order. Switch Access and a service that only speaks are used by sight: the page opens on its first line.
    val readFromTheTop = no.brasscribe.play.ui.rememberTouchExploration(vm.container.touchExplorationOverride)
    var told by remember { mutableStateOf<Int?>(null) }
    // Leaving a note (Close, Next ?, another mark) gives the player back the speed and repeat that Play this bar slowly took.
    val practice: PracticeModel = viewModel()
    LaunchedEffect(told) { practice.endSlowly() }
    // A mark the page is to show: asked for by "Check them" and Next ?, counted so the same mark can be asked for again.
    var reveal by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    val density = LocalDensity.current
    val fontScale = density.fontScale
    val scope = rememberCoroutineScope()
    val palette = tabPalette(c)

    fun checkTheSong() {
        val stack = vm.screen.value
        // Check the song is where the tab was opened from, or it is opened over the tab.
        if (stack.size >= 2 && stack[stack.size - 2] == Screen.OUTPUT) vm.back() else vm.navigate(Screen.OUTPUT)
    }

    val title = source?.name?.substringBeforeLast('.').orEmpty()
    val s = sheet
    // The columns with a note Fretscribe is not sure of, in reading order: where "Check them" and Next ? go.
    val doubts = remember(s) { s?.marks?.columns?.indices?.filter { i -> s.marks.columns[i].notes.any { it.kind == MarkKind.DOUBT } }.orEmpty() }
    // A phone on its side has little height: the note under the tab is then one row.
    val noteInOneRow = LocalConfiguration.current.screenHeightDp < 480
    fun showMark(column: Int) {
        told = column
        reveal = column to (reveal?.second ?: 0) + 1
    }
    // Practice. The recording follows the tab by the beats the computer tracked; the notes saved with a song have them too.
    val clock = remember(s, r.composition) { s?.let { TabClock.of(it.index, it.tab, r.composition) } }
    val recording = source?.file
    LaunchedEffect(practice, song, s, clock, recording) {
        if (s != null) practice.open(song, r.jobId, clock, recording, vm.savedScores.value.mapNotNull { it.jobId }.toSet())
    }
    // Leaving the tab, or the app, stops the sound; the song stays where it was.
    DisposableEffect(practice) { onDispose { practice.endSlowly(); practice.leave() } }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, practice) {
        val stopped = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) practice.pause() }
        lifecycle.addObserver(stopped)
        onDispose { lifecycle.removeObserver(stopped) }
    }
    // The screen stays on while the recording plays: the hands are on the instrument.
    val window = LocalView.current
    DisposableEffect(window, practice.playing) {
        window.keepScreenOn = practice.playing
        onDispose { window.keepScreenOn = false }
    }
    // The bar (counted from 0) and the beat the recording is at, for the player's line.
    var place by remember(song) { mutableStateOf<Pair<Int, Int>?>(null) }
    val reducedMotion = remember { android.provider.Settings.Global.getFloat(context.contentResolver, android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    val canPlay = clock != null && practice.recording == RecordingState.HERE
    var playerHeight by remember { mutableIntStateOf(0) }
    // One scroll moves the header (when it is not pinned), the marks and alphaTab's page.
    val scroll = rememberScrollState()
    var viewport by remember { mutableIntStateOf(0) }
    var canZoomIn by remember { mutableStateOf(true) }
    // The note about a mark, under the tab and the player. It is laid out after them in the body, not as the scaffold's
    // bottom bar: the keyboard's Tab follows the layout, and a scaffold's bars come before its content (WCAG 2.4.3).
    val noteShown = told?.let { s?.marks?.columns?.getOrNull(it) } != null
    val noteUnderTheTab: @Composable () -> Unit = {
    val at = told
    val column = at?.let { s?.marks?.columns?.getOrNull(it) }
    if (at != null && column != null) Column(Modifier.fillMaxWidth().background(c.bg).navigationBarsPadding()) {
        HorizontalDivider(thickness = 1.dp, color = c.border)
        // Until a note can be fixed here: listen to its bar slowly, and go on to the next "?". Next ? stays at the last
        // one, off and saying so, so the keyboard's focus is not lost (as the player's Next bar does).
        val next = doubts.firstOrNull { it > at }
        val showNext = next != null || doubts.size > 1
        val slowly = stringResource(R.string.fs_tab_note_slowly)
        val nextName = stringResource(R.string.fs_tab_note_next_name)
        val lastState = stringResource(R.string.fs_tab_note_last)
        // The note is read first, then what can be done about it, which is several keys away.
        val then = listOfNotNull(slowly.takeIf { canPlay }, nextName.takeIf { next != null }).takeIf { it.isNotEmpty() }
            ?.let { stringResource(R.string.fs_tab_note_actions, it.joinToString(", ")) }
        val words = TabWords.describe(resources, column, currentLang() == no.brasscribe.play.model.Lang.NB)
        val note: @Composable (Modifier) -> Unit = { m ->
            // In one row the words are a size smaller: the tab keeps the room for a whole column of it.
            Text(words, style = if (noteInOneRow) MaterialTheme.typography.bodyMedium else MaterialTheme.typography.bodyLarge, color = c.text,
                modifier = m.testTag("fs-tab-note").semantics { liveRegion = LiveRegionMode.Polite; if (then != null) contentDescription = "$words $then" })
        }
        val nextButton: @Composable () -> Unit = {
            TextButton({ next?.let(::showMark) }, Modifier.heightIn(min = 48.dp).testTag("fs-tab-note-next").semantics {
                contentDescription = nextName
                if (next == null) { disabled(); stateDescription = lastState }
            }, shape = BrasscribeButtonShape, colors = ButtonDefaults.textButtonColors(contentColor = if (next == null) c.text.copy(alpha = 0.38f) else c.text)) {
                Text(stringResource(R.string.fs_tab_note_next), style = MaterialTheme.typography.labelLarge, modifier = Modifier.clearAndSetSemantics { })
            }
        }
        val close: @Composable () -> Unit = {
            IconButton({ told = null }, Modifier.size(48.dp).testTag("fs-tab-note-close")) { BcIcon(R.drawable.ic_bc_close, stringResource(R.string.fs_tab_note_close)) }
        }
        if (noteInOneRow) {
            // Low on height (a phone on its side): one row, Play this bar slowly as an icon that keeps its name.
            Row(
                Modifier.fillMaxWidth().padding(start = BrasscribeSpace.s4, end = BrasscribeSpace.s1),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1),
            ) {
                note(Modifier.weight(1f))
                if (canPlay) IconButton({ practice.playBarSlowly(column.bar) }, Modifier.size(48.dp).testTag("fs-tab-note-slowly")) {
                    BcIcon(R.drawable.ic_bc_play, slowly)
                }
                if (showNext) nextButton()
                close()
            }
        } else {
            Row(
                Modifier.fillMaxWidth().padding(start = BrasscribeSpace.s4, end = BrasscribeSpace.s1, top = BrasscribeSpace.s2),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
                note(Modifier.weight(1f))
                close()
            }
            FlowRow(
                Modifier.fillMaxWidth().padding(start = BrasscribeSpace.s4, end = BrasscribeSpace.s4, bottom = BrasscribeSpace.s2),
                horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1),
            ) {
                if (canPlay) OutlineButton(slowly, { practice.playBarSlowly(column.bar) },
                    Modifier.testTag("fs-tab-note-slowly"), icon = R.drawable.ic_bc_play, fill = false)
                if (showNext) nextButton()
            }
        }
    }
    }
    Scaffold(
        // Space plays and pauses from anywhere on the screen, unless a button in focus takes it as its own press.
        modifier = Modifier.onKeyEvent {
            // A key held down sends its press again and again: only the first one counts.
            if (it.type == KeyEventType.KeyDown && it.key == Key.Spacebar && canPlay) { if (it.nativeKeyEvent.repeatCount == 0) practice.toggle(); true } else false
        },
        containerColor = c.bg,
        topBar = {
            PlayTopBar(title, vm::back, stringResource(R.string.back), titleIsHeading = true) {
                val percent = stringResource(R.string.fs_tab_zoom, zoom)
                fun set(to: Int) { zoom = to; TabPlaces.zoom = to }
                IconButton({ set((zoom - BrasscribeScore.zoomStep).coerceAtLeast(BrasscribeScore.zoomMin)) }, Modifier.size(48.dp).testTag("fs-tab-zoom-out"),
                    enabled = zoom > BrasscribeScore.zoomMin) {
                    BcIcon(R.drawable.ic_bc_zoom_out, stringResource(R.string.zoom_out) + ". " + percent)
                }
                IconButton({ set((zoom + BrasscribeScore.zoomStep).coerceAtMost(BrasscribeScore.zoomMax)) }, Modifier.size(48.dp).testTag("fs-tab-zoom-in"),
                    enabled = zoom < BrasscribeScore.zoomMax && canZoomIn) {
                    BcIcon(R.drawable.ic_bc_zoom_in, stringResource(R.string.zoom_in) + ". " + percent)
                }
            }
        },
    ) { padding ->
        // Page Up, Page Down, Home and End move the page, from wherever the keyboard's focus is on this screen.
        fun page(key: Key): Boolean {
            val by = when (key) {
                Key.PageDown -> 0.85f * viewport
                Key.PageUp -> -0.85f * viewport
                Key.MoveEnd -> scroll.maxValue.toFloat()
                Key.MoveHome -> -scroll.maxValue.toFloat()
                else -> return false
            }
            scope.launch { scroll.scrollBy(by) }
            return true
        }
        // The screen itself takes the keyboard's focus when it opens, so the keys work before anything on it has been reached.
        val keys = remember { FocusRequester() }
        LaunchedEffect(Unit) { runCatching { keys.requestFocus() } }
        // With the screen itself or the tab (one of its marks) in focus, the arrows move the song: left is back to the start of
        // the repeat, or a bar back; right a bar on. Elsewhere they move the focus, as arrows do.
        var screenFocused by remember { mutableStateOf(false) }
        var tabFocused by remember { mutableStateOf(false) }
        fun bar(key: Key): Boolean {
            if (!canPlay || !(screenFocused || tabFocused)) return false
            when (key) {
                Key.DirectionLeft -> if (practice.repeat != null) practice.toStart() else practice.step(-1)
                Key.DirectionRight -> practice.step(1)
                else -> return false
            }
            return true
        }
        // The note takes the room at the bottom when it is there, and keeps clear of the navigation bar itself.
        val direction = LocalLayoutDirection.current
        val around = PaddingValues(top = padding.calculateTopPadding(), start = padding.calculateStartPadding(direction),
            end = padding.calculateEndPadding(direction), bottom = if (noteShown) 0.dp else padding.calculateBottomPadding())
        Column(Modifier.fillMaxSize().padding(around).consumeWindowInsets(around)) {
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().onKeyEvent { it.type == KeyEventType.KeyDown && (page(it.key) || bar(it.key)) }
            .focusRequester(keys).onFocusChanged { screenFocused = it.isFocused }.focusable()) {
            if (s == null) {
                Column(Modifier.padding(horizontal = BrasscribeSpace.s4), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                    Text(stringResource(R.string.fs_tab_reading), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
                    LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
                }
                return@BoxWithConstraints
            }
            // The size: the text size and the zoom, never wider than a bar fits; on its side, large text stops at two lines to
            // the screen. It is known before the page is engraved, so the page is engraved once.
            val landscape = maxWidth > maxHeight
            val area = constraints.maxHeight
            val width = maxWidth.value
            val room = with(density) { area.toDp().value }
            val lineUnits = TabSize.lineUnits(s.strings, s.layout)
            fun scaleAt(percent: Int) = TabSize.scale(TabView.BASE_SCALE, percent, fontScale, width, room, landscape, lineUnits)
            val wanted = scaleAt(zoom)
            val larger = scaleAt(zoom + BrasscribeScore.zoomStep) > wanted
            SideEffect {
                canZoomIn = larger
                TabScreenProbe.wanted = wanted
            }
            // A size, a width or a set of colours is a view of its own (see TabView): a turned phone has a new one, as a new
            // size has. Several steps of the zoom in a row are one new view.
            val scale by produceState(wanted, wanted) {
                if (value != wanted) {
                    delay(250)
                    value = wanted
                }
            }
            val tab = remember(scale, palette, constraints.maxWidth) { TabView(context, scale, palette) }
            DisposableEffect(tab) {
                TabScreenProbe.view = tab
                TabScreenProbe.made++
                onDispose {
                    if (TabScreenProbe.view === tab) TabScreenProbe.view = null
                    tab.release()
                }
            }
            val engraving by tab.engraving.collectAsState()
            val e = engraving
            var placedFor by remember { mutableStateOf<TabEngraving?>(null) }
            var placedInset by remember { mutableIntStateOf(-1) }
            LaunchedEffect(tab, s) { tab.show(s.musicXml, s.layout, s.index, s.marks) }
            val tuning = tuningName(s.tuning)
            val capo = if (s.capo > 0) stringResource(R.string.fs_tab_capo, s.capo) else stringResource(R.string.fs_tab_no_capo)
            val chipName = stringResource(R.string.fs_tab_chip_name, tuningName(s.tuning, spoken = true), capo)
            val tempo = s.tempo
            val tempoSpoken = tempo?.let { stringResource(R.string.fs_tab_tempo_spoken, it) }
            var headerHeight by remember { mutableIntStateOf(0) }
            // The header stays above the tab while it leaves the tab most of the screen. On a phone on its side, or
            // with large text, it would take the room of the tab itself: then it is the top of the page and scrolls away with it.
            // (The player under the tab has its own room.)
            val pinned = !landscape && headerHeight * 3 <= area - playerHeight
            val inset = if (pinned) 0 else headerHeight
            val header: @Composable () -> Unit = {
                Column(Modifier.fillMaxWidth().onSizeChanged { headerHeight = it.height }.padding(horizontal = BrasscribeSpace.s4), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4)) {
                        // The tuning chip: a button whose name reads the whole state. The tuning and capo sheet comes later; for now it opens Check the song.
                        Box(
                            Modifier.sizeIn(minHeight = 48.dp).testTag("fs-tab-tuning")
                                .background(c.surfaceRaised, BrasscribeButtonShape).border(1.dp, c.borderStrong, BrasscribeButtonShape)
                                .clickable(role = Role.Button, onClick = ::checkTheSong)
                                .padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s2)
                                .semantics { contentDescription = chipName },
                            contentAlignment = Alignment.CenterStart,
                        ) {
                            Text(stringResource(R.string.fs_tab_chip, tuning, capo), style = MaterialTheme.typography.labelLarge, color = c.text,
                                modifier = Modifier.clearAndSetSemantics { })
                        }
                        // The tempo, which the page's own header would say: the page keeps the music.
                        if (tempo != null) Text(stringResource(R.string.fs_tab_tempo, tempo), style = MaterialTheme.typography.bodyLarge, color = c.textMuted,
                            modifier = Modifier.testTag("fs-tab-tempo").semantics { contentDescription = tempoSpoken.orEmpty() })
                    }
                    if (s.marks.doubtful > 0) Row(
                        // To the first "?" on the page, with its note open (Check the song only counts them).
                        Modifier.fillMaxWidth().sizeIn(minHeight = 48.dp).testTag("fs-tab-marked")
                            .clickable(role = Role.Button) { doubts.firstOrNull()?.let(::showMark) ?: checkTheSong() },
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
                    ) {
                        Text(pluralStringResource(R.plurals.fs_tab_marked, s.marks.doubtful, s.marks.doubtful),
                            style = MaterialTheme.typography.bodyMedium, color = c.textMuted, modifier = Modifier.weight(1f))
                        BcIcon(R.drawable.ic_bc_open, null, tint = c.textMuted)
                    }
                    if (s.marks.noPlace > 0) Text(pluralStringResource(R.plurals.fs_tab_no_place_count, s.marks.noPlace, s.marks.noPlace),
                        style = MaterialTheme.typography.bodyMedium, color = c.textMuted, modifier = Modifier.testTag("fs-tab-no-place").padding(vertical = BrasscribeSpace.s1))
                }
            }
            if (s.index.bars == 0) {
                Column {
                    header()
                    InfoNote(stringResource(R.string.fs_tab_failed), Modifier.padding(BrasscribeSpace.s4).testTag("fs-tab-failed"))
                }
                return@BoxWithConstraints
            }

            // The page is put where the bar being read is, after every engraving (a new size, a turn of the phone, coming
            // back) and when the header over the page changes height. From the start, the page opens on its first line: a
            // header that scrolls with the page (on its side, or with large text) is above it, a scroll up away, so the tab
            // and the player have the screen. It stays in view once the player has scrolled up to it, and with a screen
            // reader explored by touch the page opens at its top.
            LaunchedEffect(tab, e, inset) {
                if (e == null || (e === placedFor && inset == placedInset)) return@LaunchedEffect
                placedFor = null
                scroll.scrollTo(when {
                    reading != 0 -> inset + (e.topOfBar(reading) ?: 0)
                    readFromTheTop || headerShown -> 0
                    else -> inset
                })
                placedInset = inset
                placedFor = e
            }
            LaunchedEffect(tab, scroll, inset, e) {
                // What the page was put in place for is read with the scroll, in one snapshot: a scroll while the page is
                // being put in place, or one that only follows a page that became shorter, is not the player's.
                snapshotFlow { Triple(scroll.value, scroll.isScrollInProgress, placedFor) }.collect { (y, byHand, placed) ->
                    tab.scrollTo(y - inset)
                    if (byHand && e != null && placed === e) {
                        // Half the header or more, as for the bar being read: a pixel of it is not the player scrolling up to it.
                        headerShown = inset > 0 && y <= inset / 2
                        reading = if (y <= inset / 2) 0 else e.barAt(y - inset) ?: reading
                        TabPlaces.keep(song, reading)
                    }
                }
            }

            // A mark asked for ("Check them", Next ?) is brought into view when it is not, a third of the way down.
            // The request is done with once the mark is shown: a later engraving (a size, a turn, the text size) leaves the
            // page where the player has it. The whole column, the mark and its numerals, is put above the note under the tab.
            LaunchedEffect(reveal, e, inset) {
                val column = reveal?.first ?: return@LaunchedEffect
                val box = e?.boxes?.firstOrNull { it.column == column } ?: return@LaunchedEffect
                // The note under the tab opens with the request: the room left is known a frame later.
                withFrameNanos { }
                withFrameNanos { }
                val top = inset + box.top.roundToInt()
                val bottom = inset + box.columnBottom.roundToInt()
                if (top < scroll.value || bottom > scroll.value + viewport) {
                    val to = (top - viewport / 3).coerceAtLeast(bottom - viewport).coerceAtMost(top).coerceIn(0, scroll.maxValue)
                    if (reducedMotion) scroll.scrollTo(to) else scroll.animateScrollTo(to)
                }
                reveal = null
            }

            // The repeat's band and brackets, and the cursor at the beat the recording is at. The cursor moves from beat to
            // beat, and only while the recording plays or the player moved it: a still song draws nothing.
            LaunchedEffect(tab, practice.repeat) { tab.repeat = practice.repeat?.let { it.first..it.last } }
            var followed by remember(song) { mutableStateOf<Int?>(null) }
            var jumpsSeen by remember(song) { mutableIntStateOf(practice.jumps) }
            LaunchedEffect(tab, e, clock, canPlay, practice.playing, practice.at, practice.jumps, inset) {
                if (clock == null || e == null || !canPlay) {
                    tab.cursorAt(null)
                    place = null
                    return@LaunchedEffect
                }
                fun show(moved: Boolean) {
                    val now = clock.placeAt(practice.now())
                    tab.cursorAt(now)
                    val said = now.bar to clock.beatAt(now)
                    if (place != said) place = said
                    val line = e.lineOf(now.bar) ?: return
                    val newLine = followed?.let { it !in line.firstBar..line.lastBar } == true
                    followed = now.bar
                    val top = inset + line.top
                    val inView = top >= scroll.value && inset + line.bottom <= scroll.value + viewport
                    // The page follows the recording from line to line, with the line being played at the top and the ones to
                    // come under it; and it goes to where the player moved the song when that is out of view.
                    if ((newLine && practice.playing) || (moved && !inView)) scope.launch {
                        if (reducedMotion) scroll.scrollTo(top) else scroll.animateScrollTo(top)
                    }
                }
                show(moved = practice.playing || practice.jumps != jumpsSeen)
                jumpsSeen = practice.jumps
                if (!practice.playing) return@LaunchedEffect
                // While it plays, the recording is asked where it is about once a frame, on the main thread's own clock.
                val main = android.os.Handler(android.os.Looper.getMainLooper())
                val look = object : Runnable {
                    override fun run() {
                        show(moved = false)
                        main.postDelayed(this, 16)
                    }
                }
                main.postDelayed(look, 16)
                try {
                    kotlinx.coroutines.awaitCancellation()
                } finally {
                    main.removeCallbacks(look)
                }
            }

            val summary = listOfNotNull(
                title.takeIf { it.isNotEmpty() },
                stringResource(when (s.layout) {
                    TabLayout.NOTATION -> R.string.fs_tab_summary_notation
                    TabLayout.TAB_AND_NOTATION -> R.string.fs_tab_summary_tab_and_notation
                    else -> R.string.fs_tab_summary_tab
                }),
                chipName,
                tempoSpoken,
                pluralStringResource(R.plurals.fs_tab_bars, s.index.bars, s.index.bars),
                s.marks.doubtful.takeIf { it > 0 }?.let { pluralStringResource(R.plurals.fs_check_marked, it, it) },
                s.marks.noPlace.takeIf { it > 0 }?.let { pluralStringResource(R.plurals.fs_tab_no_place_count, it, it) },
            ).joinToString(". ") + "."
            Column(Modifier.fillMaxSize()) {
                if (pinned) header()
                Box(Modifier.weight(1f).fillMaxWidth().clipToBounds().onSizeChanged { viewport = it.height }.onFocusChanged { tabFocused = it.hasFocus }) {
                    // alphaTab's view fills the room and scrolls its own page (it draws the lines in view). While the header
                    // is still on screen above the page, the view is moved down under it.
                    key(tab) {
                        AndroidView({ tab.view }, Modifier.fillMaxSize().testTag("fs-tab")
                            .graphicsLayer { translationY = (inset - scroll.value).coerceAtLeast(0).toFloat() }
                            .semantics { contentDescription = summary; role = Role.Image })
                    }
                    // Over it, in one scroll: the header when it is not pinned, then a column of the page's own height with the marks.
                    // It takes the drags, the keyboard's focus and the screen reader. No stretch at the ends: the page under it would not stretch with it.
                    Column(Modifier.fillMaxSize().testTag("fs-tab-scroll").verticalScroll(scroll, overscrollEffect = null)) {
                        if (!pinned) header()
                        Box(Modifier.fillMaxWidth().height(with(density) { (e?.height ?: 0).toDp() })) {
                            // Each mark is an element of its own, in reading order: 48 dp, from the mark down over its numerals.
                            val target = with(density) { 48.dp.toPx() }
                            e?.boxes?.forEach { box ->
                                val column = s.marks.columns.getOrNull(box.column) ?: return@forEach
                                val tall = box.columnBottom - box.top
                                val wide = maxOf(target, box.width)
                                val top = if (tall >= target) box.top else box.top - (target - tall) / 2
                                var focused by remember { mutableStateOf(false) }
                                val words = TabWords.describe(resources, column, currentLang() == no.brasscribe.play.model.Lang.NB)
                                Box(
                                    Modifier.offset { IntOffset((box.centre - wide / 2).roundToInt(), top.roundToInt()) }
                                        .size(with(density) { wide.toDp() }, with(density) { maxOf(target, tall).toDp() })
                                        .testTag("fs-tab-mark-${box.column}")
                                        .onFocusChanged { focused = it.isFocused }
                                        .then(if (focused) Modifier.border(BrasscribeScore.focusWidth, c.focus, RoundedCornerShape(6.dp)) else Modifier)
                                        .clickable(role = Role.Button) { told = box.column }
                                        .semantics { contentDescription = words },
                                )
                            }
                        }
                    }
                }
                // The player, under the tab and after it in the keyboard's and a screen reader's order: the recording is the sound.
                Box(Modifier.fillMaxWidth().onSizeChanged { playerHeight = it.height }) {
                    PracticeBar(practice, s.index.measures, place, follows = clock != null,
                        canFetch = r.jobId != null && remember(practice.recording) { vm.container.engine() != null },
                        onFetch = { vm.container.engine()?.let(practice::fetch) })
                }
            }
        }
        noteUnderTheTab()
        }
    }
}
