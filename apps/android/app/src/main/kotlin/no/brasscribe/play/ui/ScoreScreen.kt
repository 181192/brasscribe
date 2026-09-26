package no.brasscribe.play.ui

import android.app.Activity
import android.content.ContextWrapper
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.audio.RealisticSynth
import no.brasscribe.play.score.ScoreController
import no.brasscribe.play.score.ScoreUiState
import no.brasscribe.play.ui.theme.LocalPlayTokens

/** Index of the part a player most likely wants first: the solo cornet, else the first part. */
fun defaultPart(parts: List<String>): Int =
    parts.indexOfFirst { it.trim().equals("Solo Cornet", ignoreCase = true) }.takeIf { it >= 0 } ?: 0

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ScoreScreen(vm: PlayViewModel) {
    val context = LocalContext.current
    val res = androidx.compose.ui.platform.LocalResources.current
    val result by vm.result.collectAsState()
    val status by vm.status.collectAsState()
    val options by vm.output.collectAsState()
    val r = result ?: return
    val reducedMotion = remember {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    }
    val controller = remember(r) {
        val c = vm.container
        ScoreController(context, reducedMotion, c.core, c.bandSoundMap, c.bandSoundFont(),
            r.compositionJson ?: runCatching { c.core.encodeComposition(r.composition) }.getOrNull()).also { vm.scoreController = it }
    }
    val st by controller.state.collectAsState()
    var textView by rememberSaveable { mutableStateOf(false) }
    var showParts by remember { mutableStateOf(false) }
    // Playing live: the score alone, no system bars, screen awake. Rotation recreates the activity,
    // so this has to survive it.
    var performance by rememberSaveable { mutableStateOf(false) }
    val t = LocalPlayTokens.current
    PerformanceWindow(performance)
    BackHandler(enabled = performance) { performance = false }

    LaunchedEffect(controller, t) {
        controller.setNotationColors(t.bg.toArgb(), t.ink.toArgb(), t.staff.toArgb(), t.cursor.toArgb())
    }
    LaunchedEffect(controller) {
        // One part first (the full 18-stave score is one tap away in Parts); a key shift re-renders once.
        controller.load(r.musicXml.toByteArray()) { names -> setOf(defaultPart(names)) }
        (options.keyShift - r.appliedTranspose).takeIf { it != 0 }?.let { controller.setKeyShift(it) }
    }
    DisposableEffect(controller) { onDispose { controller.release() } }

    val partName = st.parts.getOrNull(st.shown.minOrNull() ?: 0).orEmpty()
    val shownText = if (st.shown.size == 1) partName else stringResource(R.string.show_all_parts)
    val stateText = stringResource(if (st.playing) R.string.player_playing else R.string.player_paused)
    val summary = stringResource(R.string.score_summary, st.title.ifBlank { r.composition.title }, shownText, st.bar, st.totalBars)
    val nextBar = stringResource(R.string.action_next_bar)
    val prevBar = stringResource(R.string.action_prev_bar)
    val nextPart = stringResource(R.string.action_next_part)
    val prevPart = stringResource(R.string.action_prev_part)
    val playBar = stringResource(R.string.action_play_bar)

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
        topBar = {
            if (!performance) {
                TopAppBar(
                    title = { Text(stringResource(R.string.score_title)) },
                    navigationIcon = { IconButton(onClick = { vm.back() }) { Icon(BackArrow, stringResource(R.string.back)) } },
                    actions = { TextButton(onClick = { vm.navigate(Screen.EXPORT) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.export)) } },
                )
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(if (performance) PaddingValues(0.dp) else padding)) {
            if (!performance) {
                StatusLine(status, Modifier.padding(horizontal = 16.dp))
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                    SegmentedButton(selected = !textView, onClick = { textView = false }, shape = SegmentedButtonDefaults.itemShape(0, 2)) { Text(stringResource(R.string.notation_view)) }
                    SegmentedButton(selected = textView, onClick = { textView = true }, shape = SegmentedButtonDefaults.itemShape(1, 2)) { Text(stringResource(R.string.text_view)) }
                }
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
                    st.error?.let { Text(stringResource(R.string.score_error, it), color = t.error, modifier = Modifier.align(Alignment.Center).padding(16.dp)) }
                    if (performance) {
                        PerformanceBar(controller, st, Modifier.align(Alignment.BottomCenter)) { performance = false }
                    }
                }
            }
            if (!performance) {
                Column(
                    Modifier.weight(0.9f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    TransportRow(controller, st.playing, st.bar, st.totalBars)
                    SpeedControl(st.speed) { controller.setSpeed(it) }
                    LoopControl(st.totalBars, st.loop, onSet = { a, b ->
                        controller.setLoop(a..b); vm.say(R.string.loop_set_announce, a, b)
                    }, onClear = { controller.setLoop(null); vm.say(R.string.loop_cleared) }, invalid = { vm.say(R.string.loop_invalid, st.totalBars) })
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        ToggleRow(stringResource(R.string.count_in), st.countIn) { controller.setCountIn(it) }
                        ToggleRow(stringResource(R.string.metronome), st.metronome) { controller.setMetronome(it) }
                        ToggleRow(stringResource(R.string.concert_pitch), st.concertPitch) { controller.setConcertPitch(it) }
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { showParts = true }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.parts)) }
                        OutlinedButton(onClick = { controller.setZoom(st.zoom - 10) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.zoom_out)) }
                        Text(stringResource(R.string.zoom_value, st.zoom))
                        OutlinedButton(onClick = { controller.setZoom(st.zoom + 10) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.zoom_in)) }
                        OutlinedButton(
                            onClick = { textView = false; performance = true },
                            modifier = Modifier.heightIn(min = 48.dp).semantics { testTag = "performance" },
                        ) { Text(stringResource(R.string.performance_enter)) }
                    }
                    SoundChoice(st.realistic, st.soundPackParts, st.humanized, st.bandSoundFont) { on -> controller.setRealistic(on) }
                }
            }
        }
    }

    if (showParts) PartsDialog(st.parts, st.shown, st.muted, st.soloed, controller) { showParts = false }
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

/** The only controls left on stage: play, the bar you are on, a bar either way, and the way out. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PerformanceBar(controller: ScoreController, st: ScoreUiState, modifier: Modifier = Modifier, onExit: () -> Unit) {
    val prevBar = stringResource(R.string.action_prev_bar)
    val nextBar = stringResource(R.string.action_next_bar)
    // Opaque: it sits on top of the notation, and it has to wrap on a narrow phone held upright.
    Surface(modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.surface, tonalElevation = 3.dp) {
        FlowRow(
            Modifier.fillMaxWidth().padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(onClick = controller::togglePlay, modifier = Modifier.heightIn(min = 56.dp).widthIn(min = 120.dp).semantics { testTag = "play" }) {
                Text(stringResource(if (st.playing) R.string.pause else R.string.play))
            }
            OutlinedButton(
                onClick = { controller.goToBar(st.bar - 1) },
                modifier = Modifier.heightIn(min = 56.dp).semantics { contentDescription = prevBar },
            ) { Text(stringResource(R.string.previous)) }
            Box(Modifier.heightIn(min = 56.dp), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.bar_heading, st.bar) + " / ${st.totalBars}", style = MaterialTheme.typography.titleMedium)
            }
            OutlinedButton(
                onClick = { controller.goToBar(st.bar + 1) },
                modifier = Modifier.heightIn(min = 56.dp).semantics { contentDescription = nextBar },
            ) { Text(stringResource(R.string.next)) }
            OutlinedButton(
                onClick = onExit,
                modifier = Modifier.heightIn(min = 56.dp).semantics { testTag = "performance-exit" },
            ) { Text(stringResource(R.string.performance_exit)) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TransportRow(controller: ScoreController, playing: Boolean, bar: Int, total: Int) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = controller::togglePlay, modifier = Modifier.heightIn(min = 56.dp).widthIn(min = 120.dp).semantics { testTag = "play" }) {
            Text(stringResource(if (playing) R.string.pause else R.string.play))
        }
        OutlinedButton(onClick = controller::stop, modifier = Modifier.heightIn(min = 56.dp)) { Text(stringResource(R.string.stop)) }
        Text(stringResource(R.string.bar_heading, bar) + " / $total", style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun SpeedControl(speed: Int, onChange: (Int) -> Unit) {
    val label = stringResource(R.string.speed)
    val value = stringResource(R.string.speed_value, speed)
    Column {
        Text("$label: $value")
        Slider(
            value = speed.toFloat(),
            onValueChange = { onChange((it / 5).toInt() * 5) },
            valueRange = 25f..150f,
            steps = 24,
            modifier = Modifier.fillMaxWidth().semantics { contentDescription = label; stateDescription = value },
        )
    }
}

@Composable
private fun LoopControl(total: Int, loop: IntRange?, onSet: (Int, Int) -> Unit, onClear: () -> Unit, invalid: () -> Unit) {
    var from by rememberSaveable { mutableStateOf(loop?.first?.toString() ?: "1") }
    var to by rememberSaveable { mutableStateOf(loop?.last?.toString() ?: "4") }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        SubHeading(stringResource(R.string.loop))
        // Bar numbers, not dragging, set the range (WCAG 2.5.7).
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(from, { from = it.filter(Char::isDigit).take(4) }, label = { Text(stringResource(R.string.loop_from)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.weight(1f))
            OutlinedTextField(to, { to = it.filter(Char::isDigit).take(4) }, label = { Text(stringResource(R.string.loop_to)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                val a = from.toIntOrNull(); val b = to.toIntOrNull()
                if (a == null || b == null || a < 1 || b > total || a > b) invalid() else onSet(a, b)
            }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.loop_set)) }
            if (loop != null) OutlinedButton(onClick = onClear, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.loop_clear)) }
        }
    }
}

/** A labelled switch whose whole row is one 48 dp toggle target. */
@Composable
fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.heightIn(min = 48.dp).toggleable(value = checked, role = Role.Switch, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Switch(checked = checked, onCheckedChange = null)
        Text(label)
    }
}

@Composable
private fun SoundChoice(realistic: Boolean, packParts: Int, humanized: Boolean, bandSoundFont: Boolean, onChange: (Boolean) -> Boolean) {
    val available = RealisticSynth.available
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        SubHeading(stringResource(R.string.sound))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SegmentedButton(selected = !realistic, onClick = { onChange(false) }, shape = SegmentedButtonDefaults.itemShape(0, 2)) {
                Text(stringResource(R.string.sound_baseline))
            }
            SegmentedButton(selected = realistic, enabled = available, onClick = { onChange(true) }, shape = SegmentedButtonDefaults.itemShape(1, 2)) {
                Text(stringResource(R.string.sound_realistic))
            }
        }
        Text(
            when {
                !available -> stringResource(R.string.sound_realistic_unavailable)
                realistic && packParts > 0 -> androidx.compose.ui.res.pluralStringResource(R.plurals.sound_pack_parts, packParts, packParts)
                else -> stringResource(R.string.sound_realistic_test_tone)
            },
            style = MaterialTheme.typography.bodySmall,
        )
        if (realistic && humanized) Text(stringResource(R.string.sound_humanized), style = MaterialTheme.typography.bodySmall)
        if (!realistic && bandSoundFont) Text(stringResource(R.string.sound_band_soundfont), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun PartsDialog(parts: List<String>, shown: Set<Int>, muted: Set<Int>, soloed: Set<Int>, controller: ScoreController, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.close)) } },
        title = { Text(stringResource(R.string.parts)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { controller.showParts(parts.indices.toSet()) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.show_all_parts)) }
                    OutlinedButton(onClick = { controller.showParts(setOf(defaultPart(parts))) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.show_one_part)) }
                }
                parts.forEachIndexed { i, name ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(i in shown, role = Role.Checkbox) { on ->
                                controller.showParts(if (on) shown + i else shown - i)
                            },
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(checked = i in shown, onCheckedChange = null)
                            Text(name, Modifier.padding(start = 8.dp), style = MaterialTheme.typography.titleSmall)
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            ToggleRow(stringResource(R.string.mute_part, name), i in muted) { controller.setMuted(i, it) }
                            ToggleRow(stringResource(R.string.solo_part, name), i in soloed) { controller.setSolo(i, it) }
                        }
                    }
                }
            }
        },
    )
}
