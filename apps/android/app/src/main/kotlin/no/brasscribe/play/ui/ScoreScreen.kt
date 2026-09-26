package no.brasscribe.play.ui

import android.app.Activity
import android.content.ContextWrapper
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
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
import no.brasscribe.design.BrasscribeNumericStyle
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.audio.RealisticSynth
import no.brasscribe.play.compositionJsonFor
import no.brasscribe.play.model.Uncertainty
import no.brasscribe.play.score.ScoreController
import no.brasscribe.play.score.ScorePalette
import no.brasscribe.play.score.ScoreUiState

/** Index of the part a player most likely wants first: the solo cornet, else the first part. */
fun defaultPart(parts: List<String>): Int =
    parts.indexOfFirst { it.trim().equals("Solo Cornet", ignoreCase = true) }.takeIf { it >= 0 } ?: 0

private enum class Sheet { PARTS, SPEED, LOOP, SOUND }

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
    // Playing live: the score alone, no system bars, screen awake. Rotation recreates the activity,
    // so this has to survive it.
    var performance by rememberSaveable { mutableStateOf(false) }
    PerformanceWindow(performance)
    BackHandler(enabled = performance) { performance = false }

    LaunchedEffect(controller, c) {
        controller.setNotationColors(ScorePalette(c.bg.toArgb(), c.ink.toArgb(), c.staff.toArgb(), c.cursor.toArgb(),
            c.uncertain.toArgb(), c.veryUncertain.toArgb(), c.loopTint.toArgb(), c.isHighContrast, c.adlibTint.toArgb()))
    }
    LaunchedEffect(controller) {
        // One part first (the full score is one tap away in Parts); a key shift re-renders once.
        controller.load(r.musicXml.toByteArray()) { names -> setOf(defaultPart(names)) }
        (options.keyShift - r.appliedTranspose).takeIf { it != 0 }?.let { controller.setKeyShift(it) }
    }
    DisposableEffect(controller) { onDispose { controller.release() } }

    val single = st.shown.size == 1
    val partName = st.parts.getOrNull(st.shown.minOrNull() ?: 0).orEmpty()
    val shownText = if (single) partName else stringResource(R.string.show_all_parts)
    val myPart = st.shown.minOrNull()?.takeIf { single } ?: defaultPart(st.parts)
    val stateText = stringResource(if (st.playing) R.string.player_playing else R.string.player_paused)
    val summary = stringResource(R.string.score_summary, st.title.ifBlank { r.composition?.title.orEmpty() }, shownText, st.bar, st.totalBars)
    val nextBar = stringResource(R.string.action_next_bar)
    val prevBar = stringResource(R.string.action_prev_bar)
    val nextPart = stringResource(R.string.action_next_part)
    val prevPart = stringResource(R.string.action_prev_part)
    val playBar = stringResource(R.string.action_play_bar)
    val toCheck = remember(r, checkedMap) {
        val comp = r.composition
        comp?.voices.orEmpty().sumOf { v ->
            val done = checkedMap[v.id].orEmpty()
            partViewFor(comp!!, v.id, done, vm.container.core).events.count { it.note != null && it.uncertainty != Uncertainty.CONFIDENT && it.index !in done }
        }
    }

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

    Scaffold(
        containerColor = c.bg,
        topBar = {
            if (!performance) PlayTopBar(
                title = st.title.ifBlank { r.composition?.title.orEmpty() }, onBack = { vm.back() },
                actions = {
                    IconButton({ sheet = Sheet.SOUND }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_more, stringResource(R.string.more)) }
                    IconButton({ vm.navigate(Screen.EXPORT) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_export, stringResource(R.string.export)) }
                },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(if (performance) PaddingValues(0.dp) else padding)) {
            // The score toolbar: part picker, written or concert pitch, zoom, Read aloud and Full screen.
            if (!performance) FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = ScreenMargin),
                horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
                PracticeChip(shownText, false, { sheet = Sheet.PARTS }, icon = R.drawable.ic_bc_parts, role = Role.Button, trailingIcon = R.drawable.ic_bc_choose)
                Row(Modifier.background(c.secondary, MaterialTheme.shapes.medium)) {
                    IconButton({ controller.setZoom(st.zoom - 10) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_zoom_out, stringResource(R.string.zoom_out)) }
                    IconButton({ controller.setZoom(st.zoom + 10) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_zoom_in, stringResource(R.string.zoom_in)) }
                }
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    SegmentedButton(selected = !st.concertPitch, onClick = { controller.setConcertPitch(false) }, shape = SegmentedButtonDefaults.itemShape(0, 2),
                        colors = segmentColors(), icon = {}, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.written_pitch), maxLines = 2) }
                    SegmentedButton(selected = st.concertPitch, onClick = { controller.setConcertPitch(true) }, shape = SegmentedButtonDefaults.itemShape(1, 2),
                        colors = segmentColors(), icon = {}, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.concert_pitch), maxLines = 2) }
                }
            }
            if (!performance) StatusLine(status, Modifier.padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s1))
            if (toCheck > 0 && !performance) Row(Modifier.fillMaxWidth().padding(horizontal = ScreenMargin), verticalAlignment = Alignment.CenterVertically) {
                UncertainMark(false)
                Text(pluralStringResource(R.plurals.score_marked, toCheck, toCheck), style = MaterialTheme.typography.bodyMedium,
                    color = c.textMuted, modifier = Modifier.weight(1f))
                PlainButton(stringResource(R.string.check_them), { vm.navigate(Screen.REVIEW) })
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                if (textView && !performance) {
                    PartTalkingScore(vm, r, st.shown.minOrNull() ?: 0, st.concertPitch) { bar -> controller.playBar(bar) }
                } else {
                    AndroidView(
                        factory = { controller.view },
                        modifier = Modifier.fillMaxSize().semantics {
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
                    if (performance) PerformanceBar(controller, st, Modifier.align(Alignment.BottomCenter), onBar = ::moveBar) { performance = false }
                }
            }
            if (!performance) PlayerBar(controller, st, myPart, onSpeed = { sheet = Sheet.SPEED }, onLoop = { sheet = Sheet.LOOP }, onBar = ::moveBar)
        }
    }

    when (sheet) {
        Sheet.PARTS -> PartsSheet(st, controller) { sheet = null }
        Sheet.SPEED -> BottomSheet({ sheet = null }) { SpeedControl(st.speed) { controller.setSpeed(it) } }
        Sheet.LOOP -> BottomSheet({ sheet = null }) {
            LoopControl(st.totalBars, st.loop, onSet = { a, b ->
                controller.setLoop(a..b); vm.say(R.string.loop_set_announce, a, b); sheet = null
            }, onClear = { controller.setLoop(null); vm.say(R.string.loop_cleared); sheet = null }, invalid = { vm.say(R.string.loop_invalid, st.totalBars) })
        }
        Sheet.SOUND -> BottomSheet({ sheet = null }) {
            // The View menu (the review's P2): Read aloud and Full screen, then the sound.
            SubHeading(stringResource(R.string.view_menu))
            Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                PracticeChip(stringResource(R.string.read_aloud), textView, { textView = !textView; sheet = null }, icon = R.drawable.ic_bc_talking_score)
                PracticeChip(stringResource(R.string.performance_enter), false, { textView = false; performance = true; sheet = null },
                    Modifier.semantics { testTag = "performance" }, icon = R.drawable.ic_bc_picture_in_picture, role = Role.Button)
            }
            SoundChoice(st.realistic, st.soundPackParts, st.humanized, st.bandSoundFont) { on -> controller.setRealistic(on) } }
        null -> Unit
    }
}

/** Screen awake and no system bars while the score is on a stand; both are restored on the way out. */
@Composable
private fun PerformanceWindow(enabled: Boolean) {
    val view = LocalView.current
    DisposableEffect(enabled) {
        val window = generateSequence(view.context) { (it as? ContextWrapper)?.baseContext }
            .filterIsInstance<Activity>().firstOrNull()?.window
        val bars = window?.let { WindowCompat.getInsetsController(it, view) }
        view.keepScreenOn = enabled
        if (enabled) {
            bars?.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars?.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            bars?.show(WindowInsetsCompat.Type.systemBars())
        }
        onDispose {
            view.keepScreenOn = false
            bars?.show(WindowInsetsCompat.Type.systemBars())
        }
    }
}

/** The only controls left on stage: Play, a bar either way, the bar you are on, and the way out. */
@Composable
private fun PerformanceBar(controller: ScoreController, st: ScoreUiState, modifier: Modifier = Modifier, onBar: (Int) -> Unit, onExit: () -> Unit) {
    val c = BrasscribeTheme.colors
    // Opaque: it sits on top of the notation.
    Surface(modifier.fillMaxWidth(), color = c.surfaceRaised, contentColor = c.text, border = BorderStroke(1.dp, c.border)) {
        Row(Modifier.fillMaxWidth().padding(BrasscribeSpace.s2), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            FilledIconButton(
                controller::togglePlay, Modifier.size(56.dp).semantics { testTag = "play" }, shape = CircleShape,
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.primary, contentColor = c.onPrimary),
            ) { BcIcon(if (st.playing) R.drawable.ic_bc_pause else R.drawable.ic_bc_play, stringResource(if (st.playing) R.string.pause else R.string.play)) }
            IconButton({ onBar(-1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_previous_bar, stringResource(R.string.action_prev_bar)) }
            IconButton({ onBar(1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_next_bar, stringResource(R.string.action_next_bar)) }
            Text(stringResource(R.string.bar_of, st.bar, st.totalBars), style = BrasscribeNumericStyle, modifier = Modifier.weight(1f))
            OutlineButton(stringResource(R.string.performance_exit), onExit, Modifier.semantics { testTag = "performance-exit" }, fill = false)
        }
    }
}

@Composable
private fun segmentColors() = SegmentedButtonDefaults.colors(
    activeContainerColor = BrasscribeTheme.colors.surfaceRaised, activeContentColor = BrasscribeTheme.colors.text,
    activeBorderColor = BrasscribeTheme.colors.borderStrong,
    inactiveContainerColor = BrasscribeTheme.colors.secondary, inactiveContentColor = BrasscribeTheme.colors.textMuted,
    inactiveBorderColor = BrasscribeTheme.colors.border,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BottomSheet(onDismiss: () -> Unit, content: @Composable () -> Unit) {
    // No drag handle: it is a 32 dp wide target; the scrim and Back close the sheet.
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = BrasscribeTheme.colors.surfaceRaised, dragHandle = null) {
        Column(Modifier.padding(horizontal = ScreenMargin).navigationBarsPadding().padding(bottom = BrasscribeSpace.s6)
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
private fun PlayerBar(controller: ScoreController, st: ScoreUiState, myPart: Int, onSpeed: () -> Unit, onLoop: () -> Unit, onBar: (Int) -> Unit) {
    val c = BrasscribeTheme.colors
    Surface(
        Modifier.fillMaxWidth().padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s2).navigationBarsPadding(),
        shape = MaterialTheme.shapes.large, color = c.surfaceRaised, border = BorderStroke(1.dp, c.border), shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(BrasscribeSpace.s3), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                FilledIconButton(
                    controller::togglePlay, Modifier.size(56.dp).semantics { testTag = "play" }, shape = CircleShape,
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.primary, contentColor = c.onPrimary),
                ) { BcIcon(if (st.playing) R.drawable.ic_bc_pause else R.drawable.ic_bc_play, stringResource(if (st.playing) R.string.pause else R.string.play)) }
                IconButton({ onBar(-1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_previous_bar, stringResource(R.string.action_prev_bar)) }
                IconButton({ onBar(1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_next_bar, stringResource(R.string.action_next_bar)) }
                Column(Modifier.weight(1f).padding(start = BrasscribeSpace.s1)) {
                    Text(stringResource(R.string.bar_of, st.bar, st.totalBars), style = BrasscribeNumericStyle.copy(fontWeight = FontWeight.SemiBold))
                    BeatCounter(st.beat, st.beatsInBar)
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                PracticeChip(stringResource(R.string.speed_chip, st.speed), st.speed != 100, onSpeed, icon = R.drawable.ic_bc_speed, role = Role.Button)
                PracticeChip(st.loop?.let { stringResource(R.string.loop_chip_on, it.first, it.last) } ?: stringResource(R.string.loop),
                    st.loop != null, onLoop, icon = R.drawable.ic_bc_loop, role = Role.Button)
                PracticeChip(stringResource(R.string.count_in), st.countIn, { controller.setCountIn(!st.countIn) }, icon = R.drawable.ic_bc_count_in)
                PracticeChip(stringResource(R.string.metronome), st.metronome, { controller.setMetronome(!st.metronome) }, icon = R.drawable.ic_bc_metronome)
                PracticeChip(stringResource(R.string.mute_my_part), myPart in st.muted, { controller.setMuted(myPart, myPart !in st.muted) }, icon = R.drawable.ic_bc_play_along)
            }
        }
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
private fun PartsSheet(st: ScoreUiState, controller: ScoreController, onDismiss: () -> Unit) {
    val c = BrasscribeTheme.colors
    BottomSheet(onDismiss) {
        SubHeading(stringResource(R.string.parts))
        Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            SecondaryButton(stringResource(R.string.show_all_parts), { controller.showParts(st.parts.indices.toSet()); onDismiss() }, Modifier.weight(1f))
            SecondaryButton(stringResource(R.string.show_one_part), { controller.showParts(setOf(defaultPart(st.parts))); onDismiss() }, Modifier.weight(1f))
        }
        RowGroup {
            st.parts.forEachIndexed { i, name ->
                if (i > 0) RowDivider()
                val shown = i in st.shown
                Column(Modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s2),
                    verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.Button) { controller.showParts(setOf(i)); onDismiss() },
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.width(4.dp).heightIn(min = 24.dp).background(if (shown) c.text else c.surfaceRaised))
                        Spacer(Modifier.size(BrasscribeSpace.s2))
                        Text(name, style = MaterialTheme.typography.titleMedium.copy(fontWeight = if (shown) FontWeight.Bold else FontWeight.Normal))
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                        PracticeChip(stringResource(R.string.mute), i in st.muted, { controller.setMuted(i, i !in st.muted) }, icon = R.drawable.ic_bc_mute,
                            accessibleName = stringResource(R.string.mute_part, name))
                        PracticeChip(stringResource(R.string.only_this), i in st.soloed, { controller.setSolo(i, i !in st.soloed) }, icon = R.drawable.ic_bc_solo,
                            accessibleName = stringResource(R.string.solo_part, name))
                    }
                }
            }
        }
    }
}
