package no.brasscribe.play.ui

import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.nativeKeyCode
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import no.brasscribe.play.score.StandPages
import no.brasscribe.design.BrasscribeNumericStyle
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.audio.RealisticSynth
import no.brasscribe.play.compositionJsonFor
import no.brasscribe.play.lineup
import no.brasscribe.play.isSoloTake
import androidx.compose.ui.semantics.heading
import no.brasscribe.play.model.Uncertainty
import no.brasscribe.play.score.ScoreController
import no.brasscribe.play.score.ScorePalette
import no.brasscribe.play.score.ScoreUiState

/** Index of the part a player most likely wants first: the lineup's lead (Solo Cornet, 1st Cornet in a quartet), else the first part. */
fun defaultPart(parts: List<String>, lineup: no.brasscribe.play.Lineup? = null): Int = no.brasscribe.play.leadPartIndex(parts, lineup)

private enum class Sheet { PARTS, SPEED, LOOP, SOUND, PRACTICE, NOTICE, MAPPED, SOURCE }

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ScoreScreen(vm: PlayViewModel) {
    val context = LocalContext.current
    val res = androidx.compose.ui.platform.LocalResources.current
    val result by vm.result.collectAsState()
    val status by vm.status.collectAsState()
    val options by vm.output.collectAsState()
    val checkedMap by vm.checked.collectAsState()
    val r = result ?: return
    val c = BrasscribeTheme.colors
    val reducedMotion = remember {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    }
    val controller = remember(r) {
        val ct = vm.container
        ScoreController(context, reducedMotion, ct.core, ct.bandSoundMap, ct.bandSoundFont(),
            r.compositionJsonFor(ct.core)).also { vm.scoreController = it }
    }
    val st by controller.state.collectAsState()
    var textView by rememberSaveable { mutableStateOf(false) }
    var sheet by remember { mutableStateOf<Sheet?>(null) }
    var writtenTip by rememberSaveable { mutableStateOf(false) }
    // The music stand (design/music-stand.md, ui/MusicStand.kt): the score alone, in pages.
    val ms = rememberMusicStand()
    val performance = ms.open

    LaunchedEffect(controller, c) {
        controller.setNotationColors(ScorePalette(c.bg.toArgb(), c.ink.toArgb(), c.staff.toArgb(), c.cursor.toArgb(),
            c.uncertain.toArgb(), c.veryUncertain.toArgb(), c.loopTint.toArgb(), c.isHighContrast, c.adlibTint.toArgb()))
    }
    LaunchedEffect(controller) {
        // One part first (the full score is one tap away in Parts); a key shift re-renders once.
        // Your part first (the seat's, or this score's pick); every part for a conductor or a seat the lineup lacks.
        controller.load(r.musicXml.toByteArray()) { names -> vm.yourPart(names, r).index?.let { setOf(it) } ?: names.indices.toSet() }
        (options.keyShift - r.appliedTranspose).takeIf { it != 0 }?.let { controller.setKeyShift(it) }
    }
    DisposableEffect(controller) {
        onDispose {
            // Export needs the score's MIDI after this screen has gone, never the synth with the SoundFont.
            vm.scoreMidi = controller.midiSource()
            if (vm.scoreController === controller) vm.scoreController = null
            controller.release()
        }
    }
    // Settings > Sound: open with the realistic instruments when the player chose them.
    LaunchedEffect(st.loaded) { if (st.loaded && vm.container.realisticByDefault && !st.realistic) controller.setRealistic(true) }

    val single = st.shown.size == 1
    val partName = st.parts.getOrNull(st.shown.minOrNull() ?: 0).orEmpty()
    val shownText = if (single) PartNames.display(partName) else stringResource(R.string.show_all_parts)
    val override by vm.myPartOverride.collectAsState()
    val your = remember(st.parts, r, override, vm.container.seat) { vm.yourPart(st.parts, r) }
    // Mute my part mutes your part; with no part of your own ("I conduct or listen") it is not offered.
    val myPart = your.index
    val sources = remember(r) { vm.partSources(r) }
    val stateText = stringResource(if (st.playing) R.string.player_playing else R.string.player_paused)
    val summary = stringResource(R.string.score_summary, st.title.ifBlank { r.composition?.title.orEmpty() }, shownText, st.bar, st.totalBars)
    val nextBar = stringResource(R.string.action_next_bar)
    val prevBar = stringResource(R.string.action_prev_bar)
    val nextPart = stringResource(R.string.action_next_part)
    val prevPart = stringResource(R.string.action_prev_part)
    val playBar = stringResource(R.string.action_play_bar)
    val toCheck = remember(r, checkedMap) { r.composition?.let { itemsToCheck(it, checkedMap, vm.container.core) } ?: 0 }
    val grouped = r.composition?.review?.isNotEmpty() == true
    // The part on screen: where it came from, and when it is yours in a lineup without your seat, which part it is.
    val shownIndex = st.shown.singleOrNull()
    val shownSource = shownIndex?.let { st.parts.getOrNull(it) }?.let { sources[it.replace('\u00A0', ' ').trim()] }
    val mappedLine = your.mapped?.let { mappedText(it, vm.container.seat.readsOrNull, vm.container.seats) }
    // Said once, politely, when the score opens (4.1.3); it stays on screen above the music.
    val noticeSeen by vm.mappedNoticeSeen.collectAsState()
    val mappedShortLine = your.mapped?.let { mappedShort(it) }
    val mine = shownIndex != null && shownIndex == your.index
    val showMapped = mappedShortLine != null && !noticeSeen && (mine || your.index == null)
    LaunchedEffect(st.loaded, mappedLine) { if (st.loaded && mappedLine != null && !noticeSeen) vm.status.value = no.brasscribe.play.Status(mappedLine, quiet = true) }
    val writtenTipText = stringResource(R.string.written_tip_full,
        controller.writtenKey()?.let { stringResource(R.string.written_pitch_for, it) } ?: stringResource(R.string.written_pitch))

    fun movePart(delta: Int) {
        if (st.parts.isEmpty()) return
        val cur = st.shown.minOrNull() ?: 0
        val next = Math.floorMod(cur + delta, st.parts.size)
        controller.showParts(setOf(next))
        vm.status.value = no.brasscribe.play.Status(res.getString(R.string.part_of, st.parts[next], next + 1, st.parts.size))
    }
    fun moveBar(delta: Int) {
        controller.goToBar(st.bar + delta)
        vm.status.value = no.brasscribe.play.Status(res.getString(R.string.bar_heading, (st.bar + delta).coerceIn(1, st.totalBars)))
    }

    // ---- The music stand ------------------------------------------------------------------------
    val shape = standShape()
    val configuration = androidx.compose.ui.platform.LocalConfiguration.current
    val activity = remember(context) { context.findActivity() }
    val container = vm.container
    val assistive = rememberAssistive(container.assistiveOverride)
    // Tab or Space since the last touch; a Bluetooth pedal (arrows, Page Up/Down) keeps nothing up.
    val keyboard = ms.keyboardControls
    val keepControls = remember(ms.open) { container.standKeepControls }
    val follow = remember(ms.open) { container.standFollow }
    val standButton = remember { FocusRequester() }
    val scoreFocus = remember { FocusRequester() }
    // With no answer yet, the stand names a part only when the score has a known lead (not in a pop score).
    val yours = if (vm.container.seat == no.brasscribe.play.SeatChoice.NotSet && override == null) MusicStandRules.yourPart(st.parts, r.lineup) else your.index
    val onlyMineOffered = MusicStandRules.offersOnlyMine(st.parts, yours)
    var libraryEntry by rememberSaveable { mutableStateOf<String?>(null) }
    var focusOpener by remember { mutableStateOf(false) }
    StandWindow(ms.open)

    fun quiet(text: String) { vm.status.value = no.brasscribe.play.Status(text, quiet = true) }
    fun enterStand(origin: StandOrigin) {
        if (ms.open) return
        textView = false; sheet = null
        ms.origin = origin
        ms.before = if (st.loaded) st.shown.toList() else emptyList()
        ms.topBar = st.bar
        ms.layer = !st.playing || assistive || keepControls
        ms.hint = false
        ms.open = true
    }
    fun leaveStand() {
        if (!ms.open) return
        ms.open = false
        ms.pages = null
        ms.hint = false
        controller.setStandLayout(null)
        if (ms.before.isNotEmpty() && ms.before.toSet() != st.shown) controller.showParts(ms.before.toSet())
        if (ms.locked) { lockRotation(activity, false); ms.locked = false }
        if (ms.origin == StandOrigin.LIBRARY) {
            // Back to the library, focus on the score's row, and "Music stand closed." said there.
            vm.focusEntry.value = libraryEntry
            libraryEntry = null
            vm.back()
        } else {
            quiet(res.getString(R.string.stand_left))
            focusOpener = true
        }
    }
    /** [touch]: a swipe or a page button restarts the hide timer; a page key (a pedal) does not. */
    fun turnPage(to: Int, touch: Boolean = true) {
        val p = ms.pages ?: return
        val t = to.coerceIn(0, p.count - 1)
        if (touch) ms.touches++
        // Past either end the page stays, and says where it is, so a pedal press is never silent.
        if (t == ms.page) {
            if (to != t) quiet(res.getString(if (to < 0) R.string.stand_first_page else R.string.stand_last_page))
            return
        }
        ms.topBar = p.topBar(t)
        val bars = p.bars(t)
        quiet(res.getString(R.string.stand_page_turned, t + 1, p.count, bars.first, bars.last))
    }
    fun hideLayer() {
        if (!container.standHintShown) { container.standHintShown = true; ms.hint = true }
        ms.layer = false
    }
    fun tapMusic() {
        ms.keyboardControls = false
        ms.touches++
        ms.hint = false
        if (!ms.layer) { ms.layer = true; return }
        // With a screen reader, switch access or the setting, the controls stay.
        if (assistive || keepControls) return
        // Focus never lands on nothing: it goes to the score before the layer goes.
        if (ms.layerFocused) runCatching { scoreFocus.requestFocus() }
        hideLayer()
    }
    fun toggleLock() {
        val on = !ms.locked
        lockRotation(activity, on)
        ms.locked = on
        quiet(res.getString(if (on) R.string.stand_locked else R.string.stand_unlocked))
    }
    fun toggleRepeat() {
        val loop = st.loop
        val last = ms.lastLoop
        when {
            loop != null -> { ms.lastLoop = loop; controller.setLoop(null); vm.say(R.string.loop_cleared) }
            last != null -> { controller.setLoop(last); vm.say(R.string.loop_set_announce, last.first, last.last) }
            else -> sheet = Sheet.LOOP
        }
    }
    fun standCommand(cmd: StandCommand, showsControls: Boolean) {
        // Only Tab and Space bring the controls up and keep them (§4.2). A page turner's keys just turn:
        // they neither show the layer nor restart its hide timer.
        if (showsControls && cmd != StandCommand.LEAVE) { ms.touches++; ms.layer = true; ms.keyboardControls = true }
        when (cmd) {
            StandCommand.NEXT_PAGE -> turnPage(ms.page + 1, touch = false)
            StandCommand.PREVIOUS_PAGE -> turnPage(ms.page - 1, touch = false)
            StandCommand.FIRST_PAGE -> turnPage(0, touch = false)
            StandCommand.LAST_PAGE -> turnPage(ms.pageCount - 1, touch = false)
            StandCommand.NEXT_BAR -> moveBar(1)
            StandCommand.PREVIOUS_BAR -> moveBar(-1)
            StandCommand.PLAY_PAUSE -> controller.togglePlay()
            StandCommand.LEAVE -> leaveStand()
            StandCommand.SHOW_CONTROLS -> Unit
        }
    }
    BackHandler(enabled = ms.open) { leaveStand() }
    // "Open on the music stand" in the library opens the score and the stand in one step.
    LaunchedEffect(Unit) {
        vm.standFromLibrary.value?.let { id -> vm.standFromLibrary.value = null; libraryEntry = id; enterStand(StandOrigin.LIBRARY) }
    }
    // The layout (the section 3 sizing table) and your part, once the score is there.
    // A narrow column (or zoom) takes fewer bars per system, never smaller or squeezed notes.
    val density = androidx.compose.ui.platform.LocalDensity.current.density
    val columnDp = if (ms.width <= 0f) 0f else ms.width / density
    val standBars = if (columnDp <= 0f) shape.barsPerSystem else MusicStandRules.barsFitting(shape.barsPerSystem, columnDp, st.zoom / 100f)
    LaunchedEffect(ms.open, st.loaded, standBars) {
        if (ms.open && st.loaded) controller.setStandLayout(standBars)
    }
    LaunchedEffect(ms.open, st.loaded, ms.onlyMine, yours) {
        if (!ms.open || !st.loaded) return@LaunchedEffect
        if (ms.before.isEmpty()) ms.before = st.shown.toList()
        val before = ms.before.toSet()
        val want = when {
            ms.onlyMine && onlyMineOffered && yours != null -> setOf(yours)
            // Off goes back to the parts shown before; when that was your part alone, to every part.
            onlyMineOffered && before == setOf(yours) -> st.parts.indices.toSet()
            else -> before
        }
        if (want.isNotEmpty() && want != st.shown) controller.showParts(want)
    }
    // The pages follow every new layout (a turn, Only my part, zoom): the place is kept as a bar.
    val renders by controller.renders.collectAsState()
    LaunchedEffect(ms.open, renders, ms.viewport) {
        ms.pages = if (ms.open && ms.viewport > 0f) controller.standSystems().let { sys ->
            StandPages(sys, ms.viewport, maxOf(controller.standContentHeight(), sys.lastOrNull()?.bottom ?: 0f)) }.takeIf { it.count > 0 } else null
    }
    // Playback turns the pages (Settings can turn that off); a bar moved by hand brings its page.
    LaunchedEffect(ms.open, st.bar, ms.pages) {
        val p = ms.pages ?: return@LaunchedEffect
        if (!ms.open || !st.playing || !follow) return@LaunchedEffect
        val to = p.followPlayback(ms.page, st.bar)
        if (to != ms.page) ms.topBar = p.topBar(to)
    }
    LaunchedEffect(ms.open, st.bar) {
        val p = ms.pages ?: return@LaunchedEffect
        if (!ms.open || st.playing) return@LaunchedEffect
        val to = p.pageShowing(ms.page, st.bar)
        if (to != ms.page) ms.topBar = p.topBar(to)
    }
    StandAutoHide(ms, st.playing, assistive, keyboard, keepControls, ::hideLayer)
    // Entering: focus on the score, and the announcement (section 6); leaving: focus back on the opener.
    val standTitle = st.title.ifBlank { r.composition?.title.orEmpty() }
    val position = standPosition(st, yours, standTitle, ms, shape)
    val entered = stringResource(R.string.stand_entered, position.part, st.bar, st.totalBars)
    val hintText = stringResource(R.string.stand_hint)
    LaunchedEffect(ms.open) {
        if (ms.open) {
            runCatching { scoreFocus.requestFocus() }
            quiet(if (assistive) entered else "$entered $hintText")
        } else if (focusOpener) {
            focusOpener = false
            runCatching { standButton.requestFocus() }
        }
    }
    DisposableEffect(Unit) { onDispose { if (ms.locked) lockRotation(activity, false) } }
    val autoRotateOff = rememberAutoRotateOff(ms.open && shape.lockAvailable)
    val held = rememberHeldOrientation(ms.open && shape.lockAvailable && autoRotateOff)
    val turnPill = ms.open && shape.lockAvailable && autoRotateOff && !ms.locked && held != null && held != configuration.orientation
    val standSummary = stringResource(R.string.stand_score_summary, position.part, st.bar, st.totalBars, ms.page + 1, ms.pageCount)

    // A phone on its side: the score keeps most of the height and the controls fold under it (ScoreSplit).
    val overflow = remember { OverflowRowState() }
    // The controls the row had no room for: the top bar's ⋯ sheet shows them first (one overflow entry, not two).
    val rowItems = remember { ArrayList<@Composable (Boolean) -> Unit>() }
    val compact = !performance && ScoreSplit.compact(configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE, configuration.screenHeightDp)
    val phoneUpright = !performance && !compact && configuration.smallestScreenWidthDp < 600
    var bottomHeight by remember { mutableStateOf(0) }
    var uprightFirstHidden by remember { mutableStateOf(Int.MAX_VALUE) }
    // Upright on a phone, in order of need: your part (and the stand), the lineup notice, what to check, the band sounds.
    val uprightLarge = largeText()
    val uprightItems = buildList<@Composable (Boolean) -> Unit> {
        add { inSheet ->
            if (!inSheet) FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = ScreenMargin),
                horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
                PracticeChip(if (mine) stringResource(R.string.stand_part_yours, shownText) else shownText, false, { sheet = Sheet.PARTS },
                    Modifier.semantics { testTag = "part-picker" }, icon = R.drawable.ic_bc_parts, role = Role.Button, trailingIcon = R.drawable.ic_bc_choose)
                if (!uprightLarge) shownSource?.let { SourceLabel(it, compact = true, onExplain = { sheet = Sheet.SOURCE }) }
            }
        }
        // At large text the pill is a line of its own, so the part picker alone is always there.
        if (uprightLarge && shownSource != null) add { inSheet ->
            SourceLabel(shownSource, if (inSheet) Modifier else Modifier.padding(horizontal = ScreenMargin), compact = true, onExplain = { sheet = Sheet.SOURCE })
        }
        if (showMapped) add { inSheet ->
            MappedBanner(mappedShortLine!!, { sheet = Sheet.MAPPED }, { vm.closeMappedNotice() }, if (inSheet) Modifier else Modifier.padding(horizontal = ScreenMargin))
        }
        if (toCheck > 0) add { inSheet ->
            Row(Modifier.fillMaxWidth().padding(horizontal = if (inSheet) BrasscribeSpace.s0 else ScreenMargin), verticalAlignment = Alignment.CenterVertically) {
                UncertainMark(false)
                Text(pluralStringResource(if (grouped) R.plurals.score_marked_places else R.plurals.score_marked, toCheck, toCheck), style = MaterialTheme.typography.bodyMedium,
                    color = c.textMuted, modifier = Modifier.weight(1f))
                PlainButton(stringResource(R.string.check_them), { sheet = null; vm.navigate(Screen.REVIEW) })
            }
        }
        // The stand after what is about this score; without room it is in the ⋯ sheet, which always offers it.
        add { inSheet -> if (!inSheet) Box(Modifier.padding(horizontal = ScreenMargin)) { MusicStandButton(standButton) { enterStand(StandOrigin.BUTTON) } } }
        if (st.basicTier) add { inSheet ->
            if (inSheet) BandSoundsMissing(st.bandSoundsExpected)
            else NoticeLine(stringResource(R.string.band_sounds_missing), { sheet = Sheet.NOTICE }, Modifier.padding(horizontal = ScreenMargin))
        }
    }
    Scaffold(
        containerColor = c.bg,
        topBar = {
            if (!performance) PlayTopBar(
                title = PartNames.shortTitle(st.title.ifBlank { r.composition?.title.orEmpty() }), onBack = { vm.back() },
                actions = {
                    IconButton({ sheet = Sheet.SOUND }, Modifier.size(48.dp).semantics { testTag = "top-more" }) { BcIcon(R.drawable.ic_bc_more, stringResource(R.string.more)) }
                    IconButton({ vm.navigate(Screen.EXPORT) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_export, stringResource(R.string.export)) }
                },
            )
        },
    ) { padding ->
      val statusBar = androidx.compose.foundation.layout.WindowInsets.statusBars.asPaddingValues().calculateTopPadding()
      val density = androidx.compose.ui.platform.LocalDensity.current
      // Two engraved systems (the tallest), so the score never shows less than two while the controls keep a row.
      val twoSystems = remember(renders) { controller.standSystems().maxOfOrNull { it.bottom - it.top }?.let { with(density) { (it * 2).toDp() } } ?: 0.dp }
      androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxSize().padding(if (performance) PaddingValues(0.dp) else padding)) {
        val controlsMax = ScoreSplit.controlsMax(
            available = (maxHeight + padding.calculateTopPadding() - statusBar).value, content = maxHeight.value,
            // On its side two systems if they fit; upright 55 % is plenty, and the controls keep the rest.
            twoSystems = if (compact) twoSystems.value else 0f).dp
        Column(Modifier.fillMaxSize().onPreviewKeyEvent { e ->
            val n = e.nativeKeyEvent
            when {
                ms.open -> standKey(e, ms.layerFocused, ::standCommand)
                // F opens the stand (a single-key shortcut on the score screen, 2.1.4).
                e.type == KeyEventType.KeyDown && !textView &&
                    MusicStandRules.opensStand(e.key.nativeKeyCode, n.isCtrlPressed, n.isAltPressed, n.isShiftPressed) -> { enterStand(StandOrigin.BUTTON); true }
                else -> false
            }
        }) {
            if (performance) MusicStandBand(position, shape, ms, onlyMineOffered, { ms.onlyMine = !ms.onlyMine }, ::toggleLock, ::leaveStand)
            // Upright, the score keeps at least 55 % of the height as it does on its side (ScoreSplit): what is
            // above and below it shares the rest, and scrolls inside its share when it needs more.
            val topMax = controlsMax * 0.4f
            val bottomMax = controlsMax - topMax
            // A phone upright: the lines above the score show whole or not at all; what has no room goes to the
            // top bar's ⋯ sheet, as on its side (rule 7: a control is never clipped). Zoom and the pitch are there.
            if (phoneUpright) FitColumn(
                (controlsMax - with(density) { bottomHeight.toDp() }).coerceAtLeast(0.dp), BrasscribeSpace.s2,
                uprightItems.map { item -> @Composable { item(false) } }, { uprightFirstHidden = it },
                Modifier.fillMaxWidth().semantics { testTag = "score-top" },
            )
            val topScroll = rememberScrollState()
            if (!performance && !compact && !phoneUpright) Box(Modifier.fillMaxWidth()) { Column(
                Modifier.fillMaxWidth().heightIn(max = topMax).verticalScroll(topScroll).semantics { testTag = "score-top" },
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
            // The score toolbar: the part picker with where the part came from, then zoom, written or concert
            // pitch, and the music stand.
            FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = ScreenMargin),
                horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
                PracticeChip(if (mine) stringResource(R.string.stand_part_yours, shownText) else shownText, false, { sheet = Sheet.PARTS },
                    Modifier.semantics { testTag = "part-picker" }, icon = R.drawable.ic_bc_parts, role = Role.Button, trailingIcon = R.drawable.ic_bc_choose)
                shownSource?.let { SourceLabel(it, compact = true, onExplain = { sheet = Sheet.SOURCE }) }
            }
            // Your part in a lineup without your seat: one line, closed once and then not shown for this score.
            if (showMapped) MappedBanner(mappedShortLine!!, { sheet = Sheet.MAPPED }, { vm.closeMappedNotice() },
                Modifier.padding(horizontal = ScreenMargin))
            FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = ScreenMargin),
                horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
                Row(Modifier.background(c.secondary, MaterialTheme.shapes.medium)) {
                    IconButton({ controller.setZoom(st.zoom - 10) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_zoom_out, stringResource(R.string.zoom_out)) }
                    IconButton({ controller.setZoom(st.zoom + 10) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_zoom_in, stringResource(R.string.zoom_in)) }
                }
                // The phone form, "As written" / "Concert pitch"; the ⓘ names the key the part is written in.
                val writtenLabel = stringResource(R.string.written_pitch)
                if (largeText()) {
                    PracticeChip(writtenLabel, !st.concertPitch, { controller.setConcertPitch(false) }, role = Role.RadioButton)
                    PracticeChip(stringResource(R.string.concert_pitch), st.concertPitch, { controller.setConcertPitch(true) }, role = Role.RadioButton)
                    IconButton({ writtenTip = !writtenTip }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_info, stringResource(R.string.written_tip_label)) }
                    MusicStandButton(standButton) { enterStand(StandOrigin.BUTTON) }
                } else Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { SingleChoiceSegmentedButtonRow(Modifier.weight(1f)) {
                    SegmentedButton(selected = !st.concertPitch, onClick = { controller.setConcertPitch(false) }, shape = SegmentedButtonDefaults.itemShape(0, 2),
                        colors = segmentColors(), icon = {}, modifier = Modifier.heightIn(min = 48.dp)) { Text(writtenLabel, maxLines = 1) }
                    SegmentedButton(selected = st.concertPitch, onClick = { controller.setConcertPitch(true) }, shape = SegmentedButtonDefaults.itemShape(1, 2),
                        colors = segmentColors(), icon = {}, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.concert_pitch), maxLines = 1) }
                }
                    IconButton({ writtenTip = !writtenTip }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_info, stringResource(R.string.written_tip_label)) }
                    Spacer(Modifier.size(BrasscribeSpace.s2))
                    MusicStandButton(standButton) { enterStand(StandOrigin.BUTTON) }
                }
            }
            if (writtenTip) InfoNote(writtenTipText, Modifier.padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s1))
            if (toCheck > 0) Row(Modifier.fillMaxWidth().padding(horizontal = ScreenMargin), verticalAlignment = Alignment.CenterVertically) {
                UncertainMark(false)
                Text(pluralStringResource(if (grouped) R.plurals.score_marked_places else R.plurals.score_marked, toCheck, toCheck), style = MaterialTheme.typography.bodyMedium,
                    color = c.textMuted, modifier = Modifier.weight(1f))
                PlainButton(stringResource(R.string.check_them), { vm.navigate(Screen.REVIEW) })
            }
            }
            // More above the score than its share: it fades out over a hairline, so it reads as scrolling, not cut.
            if (topScroll.canScrollForward) {
                Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().heightIn(min = 24.dp, max = 24.dp)
                    .background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(c.bg.copy(alpha = 0f), c.bg))))
                androidx.compose.material3.HorizontalDivider(Modifier.align(Alignment.BottomCenter), color = c.border)
            }
            }
            Box(Modifier.weight(1f).fillMaxWidth()
                .then(if (performance) Modifier.background(c.bg).windowInsetsPadding(
                    androidx.compose.foundation.layout.WindowInsets.safeDrawing.only(androidx.compose.foundation.layout.WindowInsetsSides.Horizontal)) else Modifier)
                .onSizeChanged { ms.viewport = it.height.toFloat(); ms.width = it.width.toFloat() }) {
                if (textView && !performance) {
                    PartTalkingScore(vm, r, st.shown.minOrNull() ?: 0, st.concertPitch) { bar -> controller.playBar(bar) }
                } else {
                    AndroidView(
                        factory = { controller.view },
                        // On the stand the surface over it is the score for TalkBack (with page actions).
                        modifier = if (performance) Modifier.fillMaxSize().clearAndSetSemantics { testTag = "score-view" } else Modifier.fillMaxSize().semantics {
                            testTag = "score-view"
                            contentDescription = summary
                            stateDescription = stateText
                            customActions = listOf(
                                CustomAccessibilityAction(nextBar) { moveBar(1); true },
                                CustomAccessibilityAction(prevBar) { moveBar(-1); true },
                                CustomAccessibilityAction(nextPart) { movePart(1); true },
                                CustomAccessibilityAction(prevPart) { movePart(-1); true },
                                CustomAccessibilityAction(playBar) { controller.playBar(st.bar); true },
                            )
                        },
                    )
                    if (!st.loaded) Text(stringResource(R.string.player_loading), Modifier.align(Alignment.Center))
                    st.error?.let { Text(stringResource(R.string.score_error, it), color = c.error, modifier = Modifier.align(Alignment.Center).padding(ScreenMargin)) }
                    if (performance) MusicStandOverlay(
                        controller, st, ms, shape, scoreFocus, standSummary, assistive, reducedMotion, onlyMineOffered,
                        turnPill, onTurnMusic = {
                            lockRotation(activity, true, if (held == android.content.res.Configuration.ORIENTATION_LANDSCAPE)
                                android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE else android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT)
                            ms.locked = true
                        },
                        onPage = ::turnPage, onBar = ::moveBar, onTap = ::tapMusic, onSpeed = { controller.setSpeed(it) },
                        onRepeat = ::toggleRepeat, onOnlyMine = { ms.onlyMine = !ms.onlyMine }, onLock = ::toggleLock,
                    )
                    // Status messages float over the bottom of the notation, clear of the player. On the stand they
                    // are heard, not drawn over the music. One line in both, so no message is lost at the switch.
                    StatusLine(if (performance) status?.copy(quiet = true) else status,
                        Modifier.align(Alignment.BottomCenter).padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s2))
                }
            }
            if (phoneUpright) Column(Modifier.fillMaxWidth().onSizeChanged { bottomHeight = it.height }) {
                // Mute my part stays in reach; the other practice chips are one tap away under Practice.
                PlayerBar(controller, st, myPart, onSpeed = { sheet = Sheet.SPEED }, onLoop = { sheet = Sheet.LOOP }, onBar = ::moveBar,
                    onPractice = { sheet = Sheet.PRACTICE })
            } else if (!performance && !compact) Column(Modifier.fillMaxWidth().heightIn(max = bottomMax).verticalScroll(rememberScrollState())) {
                // Not urgent: one line, the details in a sheet.
                if (st.basicTier) NoticeLine(stringResource(R.string.band_sounds_missing), { sheet = Sheet.NOTICE }, Modifier.padding(horizontal = ScreenMargin))
                PlayerBar(controller, st, myPart, onSpeed = { sheet = Sheet.SPEED }, onLoop = { sheet = Sheet.LOOP }, onBar = ::moveBar)
            }
            // On its side: one row (Play, bars, position, then Parts, Practice, View and the stand), wrapping
            // and scrolling inside its share at large text; notices fold to one line, details in a sheet.
            if (compact) Column(
                Modifier.fillMaxWidth().heightIn(max = controlsMax).verticalScroll(rememberScrollState())
                    .padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s1).semantics { testTag = "score-controls" },
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1),
            ) {
                // One line: what does not fit (at 200 % text, a long part name) moves behind More, into a sheet.
                val controlItems = buildList<@Composable (Boolean) -> Unit> {
                    add { _ -> PracticeChip(shownText, false, { sheet = Sheet.PARTS }, icon = R.drawable.ic_bc_parts, role = Role.Button, trailingIcon = R.drawable.ic_bc_choose) }
                    add { _ -> PracticeChip(stringResource(R.string.practice), false, { sheet = Sheet.PRACTICE }, icon = R.drawable.ic_bc_speed,
                        role = Role.Button, trailingIcon = R.drawable.ic_bc_choose) }
                    // The ⋯ sheet always offers the music stand, so the stand has no entry of its own there.
                    add { inSheet -> if (!inSheet) MusicStandButton(standButton) { enterStand(StandOrigin.BUTTON) } }
                    if (toCheck > 0) add { _ ->
                        PracticeChip(pluralStringResource(if (grouped) R.plurals.score_marked_places else R.plurals.score_marked, toCheck, toCheck),
                            false, { sheet = null; vm.navigate(Screen.REVIEW) }, role = Role.Button, trailingIcon = R.drawable.ic_bc_choose)
                    }
                    if (st.basicTier) add { inSheet ->
                        // In the More sheet there is room for the notice in full.
                        if (inSheet) BandSoundsMissing(st.bandSoundsExpected)
                        else NoticeLine(stringResource(R.string.band_sounds_missing), { sheet = Sheet.NOTICE })
                    }
                }
                rowItems.clear(); rowItems.addAll(controlItems)
                OverflowRow(
                    overflow, BrasscribeSpace.s2,
                    lead = { Transport(controller, st, ::moveBar) },
                    items = controlItems,
                    more = null,
                    flexibleMin = if (st.basicTier) 160.dp else null,
                )
            }
        }
      }
    }

    when (sheet) {
        Sheet.PARTS -> PartsSheet(st, controller, your.index, sources, onMakeMine = { vm.makeMyPart(st.parts[it].replace('\u00A0', ' ').trim()) },
            onWriteForAnother = if (r.isSoloTake && vm.container.seats.isNotEmpty()) ({ sheet = null; vm.navigate(Screen.OUTPUT) }) else null) { sheet = null }
        Sheet.SPEED -> BottomSheet({ sheet = null }) { SpeedControl(st.speed) { controller.setSpeed(it) } }
        Sheet.LOOP -> BottomSheet({ sheet = null }) {
            LoopControl(st.totalBars, st.loop, onSet = { a, b ->
                controller.setLoop(a..b); ms.lastLoop = a..b; vm.say(R.string.loop_set_announce, a, b); sheet = null
            }, onClear = { controller.setLoop(null); vm.say(R.string.loop_cleared); sheet = null }, invalid = { vm.say(R.string.loop_invalid, st.totalBars) })
        }
        Sheet.PRACTICE -> BottomSheet({ sheet = null }) {
            SubHeading(stringResource(R.string.practice))
            PracticeChips(controller, st, myPart, onSpeed = { sheet = Sheet.SPEED }, onLoop = { sheet = Sheet.LOOP })
        }
        Sheet.MAPPED -> BottomSheet({ sheet = null }) { mappedLine?.let { InfoNote(it, boxed = false) } }
        Sheet.SOURCE -> BottomSheet({ sheet = null }) {
            shownSource?.let { SubHeading(stringResource(sourceWords(it))); Text(stringResource(explainOf(it)), style = MaterialTheme.typography.bodyLarge) }
        }
        Sheet.NOTICE -> BottomSheet({ sheet = null }) {
            InfoNote(stringResource(R.string.band_sounds_missing), boxed = false)
            if (st.bandSoundsExpected.isNotBlank()) {
                SubHeading(stringResource(R.string.details_show))
                Text(st.bandSoundsExpected, style = MaterialTheme.typography.bodySmall, color = c.textMuted)
            }
        }
        Sheet.SOUND -> BottomSheet({ sheet = null }) {
            // First, under their own heading, the controls the row under the score had no room for.
            val hidden = when {
                compact -> rowItems.drop(overflow.firstHidden.coerceAtMost(rowItems.size))
                phoneUpright -> uprightItems.drop(uprightFirstHidden.coerceIn(1, uprightItems.size))
                else -> emptyList()
            }
            val standHidden = phoneUpright && uprightFirstHidden <= uprightItems.size - (if (st.basicTier) 2 else 1)
            if (hidden.size > if ((compact && overflow.firstHidden <= STAND_ITEM) || standHidden) 1 else 0) {
                SubHeading(stringResource(R.string.controls_hidden))
                Column(Modifier.semantics { testTag = "sheet-controls" }, verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                    for (item in hidden) item(true)
                }
            }
            // The View menu (the review's P2): Read aloud and the music stand, then the sound.
            SubHeading(stringResource(R.string.view_menu))
            Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                PracticeChip(stringResource(R.string.read_aloud), textView, { textView = !textView; sheet = null }, icon = R.drawable.ic_bc_talking_score)
                PracticeChip(stringResource(R.string.stand_enter), false, { sheet = null; enterStand(StandOrigin.BUTTON) },
                    Modifier.semantics { testTag = "performance" }, icon = R.drawable.ic_stand_music_stand, role = Role.Button)
            }
            // On a phone on its side the zoom and the written or concert pitch live here, not over the score.
            if (compact || phoneUpright) {
                Row(Modifier.background(c.secondary, MaterialTheme.shapes.medium)) {
                    IconButton({ controller.setZoom(st.zoom - 10) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_zoom_out, stringResource(R.string.zoom_out)) }
                    IconButton({ controller.setZoom(st.zoom + 10) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_zoom_in, stringResource(R.string.zoom_in)) }
                }
                val writtenLabel = controller.writtenKey()?.let { stringResource(R.string.written_pitch_for, it) } ?: stringResource(R.string.written_pitch)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    PracticeChip(writtenLabel, !st.concertPitch, { controller.setConcertPitch(false) }, role = Role.RadioButton)
                    PracticeChip(stringResource(R.string.concert_pitch), st.concertPitch, { controller.setConcertPitch(true) }, role = Role.RadioButton)
                }
                InfoNote(stringResource(R.string.written_tip))
            }
            SoundChoice(st.realistic, st.soundPackParts, st.humanized, st.bandSoundFont || (st.loaded && !st.basicTier)) { on -> controller.setRealistic(on) } }
        null -> Unit
    }
}

/** The way onto the music stand (section 5.1): outline, with the icon and a visible label. */
@Composable
private fun MusicStandButton(focus: FocusRequester, onClick: () -> Unit) {
    PracticeChip(stringResource(R.string.stand_enter), false, onClick,
        Modifier.focusRequester(focus).semantics { testTag = "stand-enter" }, icon = R.drawable.ic_stand_music_stand, role = Role.Button)
}

@Composable
private fun segmentColors() = SegmentedButtonDefaults.colors(
    activeContainerColor = BrasscribeTheme.colors.surfaceRaised, activeContentColor = BrasscribeTheme.colors.text,
    activeBorderColor = BrasscribeTheme.colors.borderStrong,
    inactiveContainerColor = BrasscribeTheme.colors.secondary, inactiveContentColor = BrasscribeTheme.colors.textMuted,
    inactiveBorderColor = BrasscribeTheme.colors.border,
)

/** Index of the music stand in the row under the score (the ⋯ sheet has its own entry for it). */
private const val STAND_ITEM = 2

@Composable
private fun BottomSheet(onDismiss: () -> Unit, content: @Composable () -> Unit) {
    // No drag handle: it is a 32 dp wide target; the scrim and Back close the sheet.
    PlaySheet(onDismiss, BrasscribeTheme.colors.surfaceRaised, dragHandle = false) {
        Column(Modifier.padding(horizontal = ScreenMargin).padding(bottom = BrasscribeSpace.s6)
            .verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) { content() }
    }
}

/**
 * The player (system.md §5): Play first (the round ink primary), previous and next bar, the position
 * and a beat counter that never flashes, then the practice chips, which wrap onto a second row and
 * never clip: Speed, Loop, Count-in, Metronome and Mute my part.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PlayerBar(controller: ScoreController, st: ScoreUiState, myPart: Int?, onSpeed: () -> Unit, onLoop: () -> Unit, onBar: (Int) -> Unit,
                      onPractice: (() -> Unit)? = null) {
    val c = BrasscribeTheme.colors
    Surface(
        Modifier.fillMaxWidth().padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s2).navigationBarsPadding(),
        shape = MaterialTheme.shapes.large, color = c.surfaceRaised, border = BorderStroke(1.dp, c.border), shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(BrasscribeSpace.s3), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            Transport(controller, st, onBar, Modifier.fillMaxWidth())
            // At large text the practice chips sit behind one Practice button (system.md §2).
            var practice by rememberSaveable { mutableStateOf(false) }
            val large = largeText()
            // Upright on a phone: one row, Mute my part and Practice ▾ (Speed, Repeat, Count-in, Metronome in its sheet).
            if (onPractice != null) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    if (myPart != null) PracticeChip(stringResource(R.string.mute_my_part), myPart in st.muted, { controller.setMuted(myPart, myPart !in st.muted) },
                        icon = R.drawable.ic_bc_play_along)
                    PracticeChip(stringResource(R.string.practice), st.speed != 100 || st.loop != null || st.countIn || st.metronome, onPractice,
                        icon = R.drawable.ic_bc_speed, role = Role.Button, trailingIcon = R.drawable.ic_bc_choose)
                }
                return@Column
            }
            if (large) PracticeChip(stringResource(R.string.practice), practice, { practice = !practice }, icon = R.drawable.ic_bc_speed,
                role = Role.Button, trailingIcon = R.drawable.ic_bc_choose)
            if (!large || practice) PracticeChips(controller, st, myPart, onSpeed, onLoop)
        }
    }
}

/** Play first (the round ink primary), previous and next bar, then the position and the beat counter. */
@Composable
private fun Transport(controller: ScoreController, st: ScoreUiState, onBar: (Int) -> Unit, modifier: Modifier = Modifier) {
    val c = BrasscribeTheme.colors
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        FilledIconButton(
            controller::togglePlay, Modifier.size(56.dp).semantics { testTag = "play" }, shape = CircleShape,
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.primary, contentColor = c.onPrimary),
        ) { BcIcon(if (st.playing) R.drawable.ic_bc_pause else R.drawable.ic_bc_play, stringResource(if (st.playing) R.string.pause else R.string.play)) }
        IconButton({ onBar(-1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_previous_bar, stringResource(R.string.action_prev_bar)) }
        IconButton({ onBar(1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_next_bar, stringResource(R.string.action_next_bar)) }
        Column(Modifier.padding(start = BrasscribeSpace.s1)) {
            Text(stringResource(R.string.bar_of, st.bar, st.totalBars), style = BrasscribeNumericStyle.copy(fontWeight = FontWeight.SemiBold))
            BeatCounter(st.beat, st.beatsInBar)
        }
    }
}

/** Speed, Loop, Count-in, Metronome and Mute my part; they wrap and never clip. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PracticeChips(controller: ScoreController, st: ScoreUiState, myPart: Int?, onSpeed: () -> Unit, onLoop: () -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        PracticeChip(stringResource(R.string.speed_chip, st.speed), st.speed != 100, onSpeed, icon = R.drawable.ic_bc_speed, role = Role.Button)
        PracticeChip(st.loop?.let { stringResource(R.string.loop_chip_on, it.first, it.last) } ?: stringResource(R.string.loop),
            st.loop != null, onLoop, icon = R.drawable.ic_bc_loop, role = Role.Button)
        PracticeChip(stringResource(R.string.count_in), st.countIn, { controller.setCountIn(!st.countIn) }, icon = R.drawable.ic_bc_count_in)
        PracticeChip(stringResource(R.string.metronome), st.metronome, { controller.setMetronome(!st.metronome) }, icon = R.drawable.ic_bc_metronome)
        if (myPart != null) PracticeChip(stringResource(R.string.mute_my_part), myPart in st.muted, { controller.setMuted(myPart, myPart !in st.muted) }, icon = R.drawable.ic_bc_play_along)
    }
}

/** "1 2 3 4" with the current beat underlined and bold; it never flashes (WCAG 2.3.1). */
@Composable
private fun BeatCounter(beat: Int, beats: Int) {
    val c = BrasscribeTheme.colors
    val desc = stringResource(R.string.beat_of, beat, beats)
    Row(Modifier.semantics(mergeDescendants = true) { contentDescription = desc }, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        for (b in 1..beats.coerceAtMost(12)) Text(
            "$b", style = BrasscribeNumericStyle.copy(
                fontWeight = if (b == beat) FontWeight.Bold else FontWeight.Normal,
                textDecoration = if (b == beat) TextDecoration.Underline else TextDecoration.None,
            ), color = if (b == beat) c.text else c.textMuted,
        )
    }
}

@Composable
private fun SpeedControl(speed: Int, onChange: (Int) -> Unit) {
    val c = BrasscribeTheme.colors
    val label = stringResource(R.string.speed)
    val value = stringResource(R.string.speed_value, speed)
    SubHeading(stringResource(R.string.speed_chip, speed))
    Slider(
        value = speed.toFloat(),
        onValueChange = { onChange((it / 5).toInt() * 5) },
        valueRange = 25f..150f,
        steps = 24,
        colors = SliderDefaults.colors(thumbColor = c.primary, activeTrackColor = c.primary, inactiveTrackColor = c.border),
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = label; stateDescription = value },
    )
    Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        for (p in listOf(50, 75, 100)) OutlineButton(stringResource(R.string.speed_value, p), { onChange(p) }, Modifier.weight(1f))
    }
}

@Composable
private fun LoopControl(total: Int, loop: IntRange?, onSet: (Int, Int) -> Unit, onClear: () -> Unit, invalid: () -> Unit) {
    var from by rememberSaveable { mutableStateOf(loop?.first?.toString() ?: "1") }
    var to by rememberSaveable { mutableStateOf(loop?.last?.toString() ?: "4") }
    SubHeading(stringResource(R.string.loop_title))
    Text(stringResource(R.string.loop_tip), style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
    // Bar numbers, not dragging, set the range (WCAG 2.5.7).
    Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(from, { from = it.filter(Char::isDigit).take(4) }, label = { Text(stringResource(R.string.loop_from)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.weight(1f))
        OutlinedTextField(to, { to = it.filter(Char::isDigit).take(4) }, label = { Text(stringResource(R.string.loop_to)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.weight(1f))
    }
    PrimaryButton(stringResource(R.string.loop_set), {
        val a = from.toIntOrNull(); val b = to.toIntOrNull()
        if (a == null || b == null || a < 1 || b > total || a > b) invalid() else onSet(a, b)
    }, icon = R.drawable.ic_bc_loop)
    if (loop != null) OutlineButton(stringResource(R.string.loop_clear), onClear)
}

@Composable
private fun SoundChoice(realistic: Boolean, packParts: Int, humanized: Boolean, bandSoundFont: Boolean, onChange: (Boolean) -> Boolean) {
    val available = RealisticSynth.available
    val c = BrasscribeTheme.colors
    SubHeading(stringResource(R.string.sound))
    ChoiceGroup(2) {
        ChoiceCard(stringResource(R.string.sound_baseline), if (bandSoundFont) stringResource(R.string.sound_band_soundfont) else null, !realistic, true, 0) { onChange(false) }
        ChoiceCard(
            stringResource(R.string.sound_realistic),
            when {
                !available -> stringResource(R.string.sound_realistic_unavailable)
                realistic && packParts > 0 -> pluralStringResource(R.plurals.sound_pack_parts, packParts, packParts) +
                    if (humanized) " " + stringResource(R.string.sound_humanized) else ""
                else -> stringResource(R.string.sound_realistic_test_tone)
            },
            realistic, available, 1,
        ) { onChange(true) }
    }
    Text(stringResource(R.string.sound_note), style = MaterialTheme.typography.bodySmall, color = c.textMuted)
}

/**
 * Every part with its two labelled toggles, Mute and Only this (the review's P1: never "M" and "S",
 * which collide with Solo Cornet). The shown part is bold with a leading bar, not just highlighted.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PartsSheet(
    st: ScoreUiState, controller: ScoreController, yours: Int?, sources: Map<String, no.brasscribe.play.model.PartSource>,
    onMakeMine: (Int) -> Unit, onWriteForAnother: (() -> Unit)?, onDismiss: () -> Unit,
) {
    val c = BrasscribeTheme.colors
    val large = largeText()
    BottomSheet(onDismiss) {
        SubHeading(stringResource(R.string.parts))
        val all = st.shown.size > 1
        val mine = yours != null && st.shown == setOf(yours)
        Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            PracticeChip(stringResource(R.string.show_all_parts), all, { controller.showParts(st.parts.indices.toSet()); onDismiss() },
                Modifier.weight(1f), role = Role.RadioButton)
            // "Show one part" is your part; with none of your own there is no such choice.
            if (yours != null) PracticeChip(stringResource(R.string.show_one_part), mine, { controller.showParts(setOf(yours)); onDismiss() },
                Modifier.weight(1f), role = Role.RadioButton)
        }
        RowGroup {
            st.parts.forEachIndexed { i, english ->
                if (i > 0) RowDivider()
                val name = PartNames.display(english)
                val shown = i in st.shown
                val source = sources[english.replace('\u00A0', ' ').trim()]
                // One row per part (about 64 dp): the name, then Mute and Only this at the right.
                val toggles = @Composable {
                    PracticeChip(stringResource(R.string.mute), i in st.muted, { controller.setMuted(i, i !in st.muted) }, icon = R.drawable.ic_bc_mute,
                        accessibleName = stringResource(R.string.mute_part, name))
                    PracticeChip(stringResource(R.string.only_this), i in st.soloed, { controller.setSolo(i, i !in st.soloed) }, icon = R.drawable.ic_bc_solo,
                        accessibleName = stringResource(R.string.solo_part, name))
                }
                val label = @Composable { m: Modifier ->
                    Row(m.heightIn(min = 48.dp).clickable(role = Role.Button) { controller.showParts(setOf(i)); onDismiss() },
                        verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(4.dp).heightIn(min = 24.dp).background(if (shown) c.text else c.surfaceRaised))
                        Spacer(Modifier.size(BrasscribeSpace.s2))
                        Column {
                            Text(if (i == yours) stringResource(R.string.stand_part_yours, name) else name,
                                style = MaterialTheme.typography.titleMedium.copy(fontWeight = if (shown) FontWeight.Bold else FontWeight.Normal))
                            // Where it came from, in words with its icon (never a colour): the pill above the score explains it.
                            if (source != null) SourceLine(source)
                        }
                    }
                }
                val makeMine = @Composable { if (i != yours) PlainButton(stringResource(R.string.my_part_make), { onMakeMine(i) },
                    Modifier.padding(start = BrasscribeSpace.s3).semantics { testTag = "make-mine-$i" }) }
                if (large) Column(Modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s3, vertical = BrasscribeSpace.s2),
                    verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    label(Modifier.fillMaxWidth())
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) { toggles() }
                    makeMine()
                } else Column(Modifier.fillMaxWidth().padding(vertical = BrasscribeSpace.s2)) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s3),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                        label(Modifier.weight(1f))
                        toggles()
                    }
                    makeMine()
                }
            }
        }
        // A solo take: another player's instrument is chosen on How should the score be? (it re-arranges).
        if (onWriteForAnother != null) OutlineButton(stringResource(R.string.write_for_another), onWriteForAnother)
    }
}

/** A part's source in the mixer: its icon and words, small, under the part name. */
@Composable
private fun SourceLine(source: no.brasscribe.play.model.PartSource) {
    val c = BrasscribeTheme.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
        BcIcon(if (source == no.brasscribe.play.model.PartSource.ARRANGED) R.drawable.ic_bc_parts else R.drawable.ic_bc_record_mic, null,
            Modifier.size(16.dp), tint = c.textMuted)
        Text(stringResource(when (source) {
            no.brasscribe.play.model.PartSource.YOUR_RECORDING -> R.string.source_yours
            no.brasscribe.play.model.PartSource.RECORDING -> R.string.source_recording
            no.brasscribe.play.model.PartSource.ARRANGED -> R.string.source_arranged
        }), style = MaterialTheme.typography.bodySmall, color = c.textMuted)
    }
}

/** The words of a source pill. */
fun sourceWords(source: no.brasscribe.play.model.PartSource): Int = when (source) {
    no.brasscribe.play.model.PartSource.YOUR_RECORDING -> R.string.source_yours
    no.brasscribe.play.model.PartSource.RECORDING -> R.string.source_recording
    no.brasscribe.play.model.PartSource.ARRANGED -> R.string.source_arranged
}

/** A one-line notice that opens its details and can be closed; both targets 48 dp. */
@Composable
private fun MappedBanner(text: String, onOpen: () -> Unit, onClose: () -> Unit, modifier: Modifier = Modifier) {
    val c = BrasscribeTheme.colors
    Row(modifier.fillMaxWidth().background(c.surface, MaterialTheme.shapes.medium).border(1.dp, c.border, MaterialTheme.shapes.medium)
        .semantics { testTag = "mapped-notice" }, verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f).heightIn(min = 48.dp).clickable(role = Role.Button, onClick = onOpen).padding(start = BrasscribeSpace.s3),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            BcIcon(R.drawable.ic_bc_info, null, tint = c.text)
            Text(text, style = MaterialTheme.typography.bodyMedium, color = c.text, maxLines = 1,
                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
        }
        IconButton(onClose, Modifier.size(48.dp).semantics { testTag = "mapped-close" }) { BcIcon(R.drawable.ic_bc_close, stringResource(R.string.mapped_close)) }
    }
}

/**
 * A column that shows its [items] in order while each fits whole in [maxHeight], and leaves the rest out
 * (not drawn, not heard); [onFirstHidden] reports the first left out, so the ⋯ sheet can offer it.
 */
@Composable
private fun FitColumn(maxHeight: androidx.compose.ui.unit.Dp, gap: androidx.compose.ui.unit.Dp, items: List<@Composable () -> Unit>,
                      onFirstHidden: (Int) -> Unit, modifier: Modifier = Modifier) {
    androidx.compose.ui.layout.Layout({ items.forEach { it() } }, modifier) { measurables, constraints ->
        val limit = maxHeight.roundToPx()
        val gapPx = gap.roundToPx()
        val loose = constraints.copy(minHeight = 0, maxHeight = androidx.compose.ui.unit.Constraints.Infinity)
        val placeables = measurables.map { it.measure(loose) }
        var used = 0
        var shown = 0
        for ((i, p) in placeables.withIndex()) {
            val need = p.height + if (i > 0) gapPx else 0
            if (i > 0 && used + need > limit) break
            used += need
            shown++
        }
        onFirstHidden(shown)
        layout(constraints.maxWidth, used) {
            var y = 0
            for (i in 0 until shown) { placeables[i].placeRelative(0, y); y += placeables[i].height + gapPx }
        }
    }
}
