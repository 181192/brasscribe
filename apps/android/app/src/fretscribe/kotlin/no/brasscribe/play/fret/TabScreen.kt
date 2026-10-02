package no.brasscribe.play.fret

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.foundation.layout.Row
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
)

/**
 * The tab (design/fretscribe/system.md §3), to read: the page engraved full width, the tuning in a chip
 * above it, and under that what there is to check. A "?" stands above every note Fretscribe is not sure
 * of and a boxed "!" above a note with no place; each can be tapped, or reached with the keyboard or a
 * screen reader, and says which note it is. The page gets more lines of fewer bars as it is made larger.
 */
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
    var told by remember { mutableStateOf<Int?>(null) }
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
    // One scroll moves the header (when it is not pinned), the marks and alphaTab's page.
    val scroll = rememberScrollState()
    var viewport by remember { mutableIntStateOf(0) }
    var canZoomIn by remember { mutableStateOf(true) }
    Scaffold(
        containerColor = c.bg,
        topBar = {
            PlayTopBar(title, vm::back, stringResource(R.string.back)) {
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
        bottomBar = {
            val column = told?.let { s?.marks?.columns?.getOrNull(it) }
            if (column != null) Column(Modifier.fillMaxWidth().background(c.bg)) {
                HorizontalDivider(thickness = 1.dp, color = c.border)
                Row(
                    Modifier.fillMaxWidth().navigationBarsPadding().padding(start = BrasscribeSpace.s4, end = BrasscribeSpace.s1, top = BrasscribeSpace.s2, bottom = BrasscribeSpace.s2),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
                ) {
                    Text(TabWords.describe(resources, column, currentLang() == no.brasscribe.play.model.Lang.NB),
                        style = MaterialTheme.typography.bodyLarge, color = c.text,
                        modifier = Modifier.weight(1f).testTag("fs-tab-note").semantics { liveRegion = LiveRegionMode.Polite })
                    IconButton({ told = null }, Modifier.size(48.dp).testTag("fs-tab-note-close")) { BcIcon(R.drawable.ic_bc_close, stringResource(R.string.fs_tab_note_close)) }
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
        BoxWithConstraints(Modifier.fillMaxSize().padding(padding).onKeyEvent { it.type == KeyEventType.KeyDown && page(it.key) }.focusRequester(keys).focusable()) {
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
            val pinned = !landscape && headerHeight * 3 <= area
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
                        Modifier.fillMaxWidth().sizeIn(minHeight = 48.dp).testTag("fs-tab-marked").clickable(role = Role.Button, onClick = ::checkTheSong),
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
            // back) and when the header over the page changes height.
            LaunchedEffect(tab, e, inset) {
                if (e == null || (e === placedFor && inset == placedInset)) return@LaunchedEffect
                placedFor = null
                scroll.scrollTo(if (reading == 0) 0 else inset + (e.topOfBar(reading) ?: 0))
                placedInset = inset
                placedFor = e
            }
            LaunchedEffect(tab, scroll, inset, e) {
                // What the page was put in place for is read with the scroll, in one snapshot: a scroll while the page is
                // being put in place, or one that only follows a page that became shorter, is not the player's.
                snapshotFlow { Triple(scroll.value, scroll.isScrollInProgress, placedFor) }.collect { (y, byHand, placed) ->
                    tab.scrollTo(y - inset)
                    if (byHand && e != null && placed === e) {
                        reading = if (y <= inset / 2) 0 else e.barAt(y - inset) ?: reading
                        TabPlaces.keep(song, reading)
                    }
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
                Box(Modifier.weight(1f).fillMaxWidth().clipToBounds().onSizeChanged { viewport = it.height }) {
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
            }
        }
    }
}
