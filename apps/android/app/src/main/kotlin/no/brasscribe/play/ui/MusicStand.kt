package no.brasscribe.play.ui

import android.app.Activity
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.database.ContentObserver
import android.provider.Settings
import android.view.OrientationEventListener
import android.view.accessibility.AccessibilityManager
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.nativeKeyCode
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.LocalViewConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.delay
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.R
import no.brasscribe.play.score.ScoreController
import no.brasscribe.play.score.ScoreUiState
import no.brasscribe.play.score.StandPages
import kotlin.math.roundToInt

/** Where the stand was opened from: that opener gets the focus back on leaving (design/music-stand.md §6). */
enum class StandOrigin { BUTTON, LIBRARY, TURN }

/**
 * The music stand (design/music-stand.md): the score alone, in pages, with a persistent band at the top
 * (the position as plain text and ✕ Leave) and a control layer that hides itself. What survives a
 * rotation is saved (the activity handles its own configuration changes, so this is for process death).
 */
@Stable
class MusicStandState(
    open: Boolean = false,
    origin: StandOrigin = StandOrigin.BUTTON,
    topBar: Int = 1,
    layer: Boolean = true,
    locked: Boolean = false,
    onlyMine: Boolean = true,
    before: List<Int> = emptyList(),
) {
    var open by mutableStateOf(open)
    var origin by mutableStateOf(origin)
    /** The bar at the top of the page: the stand keeps its place as a bar, so a new layout finds it again. */
    var topBar by mutableIntStateOf(topBar)
    /** The control layer is on screen (hidden means gone from the screen, the semantics and the focus order). */
    var layer by mutableStateOf(layer)
    var locked by mutableStateOf(locked)
    var onlyMine by mutableStateOf(onlyMine)
    /** The parts shown before the stand opened: Only my part off, and leaving, go back to them. */
    var before by mutableStateOf(before)

    var pages by mutableStateOf<StandPages?>(null)
    /** Height of the notation window and of the part of it the control layer covers, in pixels. */
    var viewport by mutableFloatStateOf(0f)
    var obscured by mutableFloatStateOf(0f)
    var focusInLayer by mutableStateOf(false)
    /** Focus on Only my part or Lock rotation in the band (a phone on its side): part of the layer too. */
    var focusInBand by mutableStateOf(false)
    val layerFocused get() = focusInLayer || focusInBand
    /** Every touch restarts the auto-hide timer. */
    var touches by mutableIntStateOf(0)
    var hint by mutableStateOf(false)
    /** The last range that was repeated, for the Repeat toggle. */
    var lastLoop by mutableStateOf<IntRange?>(null)

    val page: Int get() = pages?.pageOf(topBar) ?: 0
    val pageCount: Int get() = pages?.count?.coerceAtLeast(1) ?: 1

    companion object {
        val Saver = listSaver<MusicStandState, Any>(
            save = { listOf(it.open, it.origin.name, it.topBar, it.layer, it.locked, it.onlyMine, ArrayList(it.before)) },
            restore = {
                @Suppress("UNCHECKED_CAST")
                MusicStandState(it[0] as Boolean, StandOrigin.valueOf(it[1] as String), it[2] as Int, it[3] as Boolean,
                    it[4] as Boolean, it[5] as Boolean, it[6] as List<Int>)
            },
        )
    }
}

@Composable
fun rememberMusicStand(): MusicStandState = rememberSaveable(saver = MusicStandState.Saver) { MusicStandState() }

/** The phone or tablet shape the stand lays itself out for (the §3 and §4.1 tables). */
data class StandShape(val tablet: Boolean, val landscape: Boolean, val barsPerSystem: Int) {
    val phoneLandscape get() = !tablet && landscape
    val lockAvailable get() = !tablet
}

@Composable
fun standShape(): StandShape {
    val cfg = LocalConfiguration.current
    val portrait = cfg.orientation != Configuration.ORIENTATION_LANDSCAPE
    return StandShape(!MusicStandRules.lockAvailable(cfg.smallestScreenWidthDp), !portrait,
        MusicStandRules.barsPerSystem(cfg.smallestScreenWidthDp, portrait))
}

fun android.content.Context.findActivity(): Activity? =
    generateSequence(this) { (it as? ContextWrapper)?.baseContext }.filterIsInstance<Activity>().firstOrNull()

/** Screen awake and no system bars while the stand is open; both come back on the way out. */
@Composable
fun StandWindow(enabled: Boolean) {
    val view = LocalView.current
    DisposableEffect(enabled) {
        val window = view.context.findActivity()?.window
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

/**
 * TalkBack, any speaking service or Switch Access (§4.2 and §8): the controls then never hide by
 * themselves. Tests set [override] in place of a real screen reader.
 */
@Composable
fun rememberAssistive(override: Boolean?): Boolean {
    val context = LocalContext.current
    val state = produceState(initialValue = override ?: false, override) {
        if (override != null) { value = override; return@produceState }
        val am = context.getSystemService(AccessibilityManager::class.java) ?: return@produceState
        fun read() = MusicStandRules.assistive(am.isTouchExplorationEnabled,
            am.getEnabledAccessibilityServiceList(android.accessibilityservice.AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
                .map { (it.id ?: "") to it.feedbackType })
        value = read()
        val touch = AccessibilityManager.TouchExplorationStateChangeListener { value = read() }
        val any = AccessibilityManager.AccessibilityStateChangeListener { value = read() }
        am.addTouchExplorationStateChangeListener(touch)
        am.addAccessibilityStateChangeListener(any)
        awaitDispose {
            am.removeTouchExplorationStateChangeListener(touch)
            am.removeAccessibilityStateChangeListener(any)
        }
    }
    return state.value
}

/** Whether the system's auto-rotate is off (then Android offers its own rotate button, which the stand hides). */
@Composable
fun rememberAutoRotateOff(enabled: Boolean): Boolean {
    val context = LocalContext.current
    val state = produceState(false, enabled) {
        if (!enabled) { value = false; return@produceState }
        val cr = context.contentResolver
        fun read() = Settings.System.getInt(cr, Settings.System.ACCELEROMETER_ROTATION, 1) == 0
        value = read()
        val observer = object : ContentObserver(android.os.Handler(android.os.Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) { value = read() }
        }
        cr.registerContentObserver(Settings.System.getUriFor(Settings.System.ACCELEROMETER_ROTATION), false, observer)
        awaitDispose { cr.unregisterContentObserver(observer) }
    }
    return state.value
}

/**
 * How the phone is held, from the sensor (a Configuration.ORIENTATION_* value), or null while it lies
 * flat or sits between two ways up. Only the stand listens, and only while it is open.
 */
@Composable
fun rememberHeldOrientation(enabled: Boolean): Int? {
    val context = LocalContext.current
    val state = produceState<Int?>(null, enabled) {
        if (!enabled) { value = null; return@produceState }
        val listener = object : OrientationEventListener(context) {
            override fun onOrientationChanged(degrees: Int) {
                if (degrees == ORIENTATION_UNKNOWN) return
                val d = Math.floorMod(degrees, 360)
                // Near one of the four ways up only: no flicker between two of them.
                value = when {
                    d <= 30 || d >= 330 || d in 150..210 -> Configuration.ORIENTATION_PORTRAIT
                    d in 60..120 || d in 240..300 -> Configuration.ORIENTATION_LANDSCAPE
                    else -> value
                }
            }
        }
        if (listener.canDetectOrientation()) listener.enable()
        awaitDispose { listener.disable() }
    }
    return state.value
}

/** The words of the position band: the part ("Solo Cornet (you)") and where the music is. */
data class StandPosition(val part: String, val place: String, val line: String)

@Composable
fun standPosition(st: ScoreUiState, yours: Int?, title: String, ms: MusicStandState, shape: StandShape): StandPosition {
    val single = st.shown.singleOrNull()
    val part = when {
        single != null && single == yours -> stringResource(R.string.stand_part_yours, PartNames.display(st.parts.getOrNull(single).orEmpty()))
        single != null -> PartNames.display(st.parts.getOrNull(single).orEmpty())
        else -> stringResource(R.string.show_all_parts)
    }
    val page = ms.page + 1
    val count = ms.pageCount
    return StandPosition(
        part,
        stringResource(R.string.stand_position, st.bar, page, count),
        if (shape.tablet) stringResource(R.string.stand_position_tablet, title, part, st.bar, page, count)
        else stringResource(R.string.stand_position_line, part, st.bar, page, count),
    )
}

/**
 * The persistent band at the top (§4.1): the position as plain text, which is a status and takes no
 * focus, and ✕ Leave, the only thing here that looks like a button. On a phone on its side, Only my
 * part and Lock rotation sit between the two while the layer shows.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MusicStandBand(
    position: StandPosition, shape: StandShape, ms: MusicStandState, onlyMine: Boolean,
    onOnlyMine: () -> Unit, onLock: () -> Unit, onLeave: () -> Unit,
) {
    val c = BrasscribeTheme.colors
    Row(
        Modifier.fillMaxWidth().background(c.bg)
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
            .padding(horizontal = ScreenMargin, vertical = BrasscribeSpace.s2),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
    ) {
        if (shape.landscape) {
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(color = c.text, fontWeight = FontWeight.SemiBold)) {
                        append(if (shape.tablet) position.line.substringBefore(position.part) + position.part else position.part)
                    }
                    withStyle(SpanStyle(color = c.textMuted)) { append(position.line.substringAfter(position.part)) }
                },
                style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f).semantics { testTag = "stand-position" },
                maxLines = 2, overflow = TextOverflow.Ellipsis,
            )
            if (ms.layer && shape.phoneLandscape) Row(
                Modifier.onFocusChanged { ms.focusInBand = it.hasFocus },
                horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
            ) {
                if (onlyMine) OnlyMineToggle(ms.onlyMine, onOnlyMine)
                LockToggle(ms.locked, onLock)
            }
        } else {
            Column(Modifier.weight(1f).semantics(mergeDescendants = true) { testTag = "stand-position" }) {
                Text(position.part, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold), color = c.text)
                Text(position.place, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            }
        }
        LeaveButton(onLeave)
    }
}

/** ✕ Leave: always there. Its accessible name contains the visible word (WCAG 2.5.3). */
@Composable
private fun LeaveButton(onLeave: () -> Unit) {
    val c = BrasscribeTheme.colors
    val name = stringResource(R.string.stand_leave_name)
    val pill = RoundedCornerShape(percent = 50)
    Surface(
        shape = pill, color = c.surfaceRaised, contentColor = c.text,
        border = BorderStroke(1.dp, c.borderStrong), shadowElevation = if (c.isHighContrast) 0.dp else 1.dp,
        modifier = Modifier.heightIn(min = 48.dp).semantics { testTag = "performance-exit" },
    ) {
        Row(
            Modifier.clearAndSetSemantics { contentDescription = name; role = Role.Button; onClick { onLeave(); true } }
                .clickable(onClick = onLeave).heightIn(min = 48.dp).padding(horizontal = BrasscribeSpace.s4),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
        ) {
            BcIcon(R.drawable.ic_bc_close, null, Modifier.size(20.dp))
            Text(stringResource(R.string.stand_leave), style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun OnlyMineToggle(on: Boolean, onToggle: () -> Unit) =
    PracticeChip(stringResource(R.string.stand_only_mine), on, onToggle, Modifier.semantics { testTag = "stand-only-mine" }, icon = R.drawable.ic_bc_play_along)

@Composable
private fun LockToggle(locked: Boolean, onToggle: () -> Unit) =
    PracticeChip(stringResource(if (locked) R.string.stand_lock_on else R.string.stand_lock), locked, onToggle,
        Modifier.semantics { testTag = "stand-lock" }, icon = R.drawable.ic_stand_rotation_lock)

/**
 * Everything over the notation: the surface that takes taps and swipes (and is the score for TalkBack,
 * with Next and Previous page as custom actions), the paper below the page's last whole system, the
 * page-turn fade, the first-time hint, Turn the music, and the control layer.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun BoxScope.MusicStandOverlay(
    controller: ScoreController, st: ScoreUiState, ms: MusicStandState, shape: StandShape,
    scoreFocus: FocusRequester, summary: String, assistive: Boolean, reducedMotion: Boolean, onlyMine: Boolean,
    turnPill: Boolean, onTurnMusic: () -> Unit,
    onPage: (Int) -> Unit, onBar: (Int) -> Unit, onTap: () -> Unit,
    onSpeed: (Int) -> Unit, onRepeat: () -> Unit, onOnlyMine: () -> Unit, onLock: () -> Unit,
) {
    val c = BrasscribeTheme.colors
    val density = LocalDensity.current
    val slop = LocalViewConfiguration.current.touchSlop
    val edge = with(density) { MusicStandRules.EDGE_DP.dp.toPx() }
    val minSwipe = with(density) { 48.dp.toPx() }
    val nextPage = stringResource(R.string.stand_next_page)
    val prevPage = stringResource(R.string.stand_prev_page)
    val nextBar = stringResource(R.string.action_next_bar)
    val prevBar = stringResource(R.string.action_prev_bar)
    val playBar = stringResource(R.string.action_play_bar)
    val stateText = stringResource(if (st.playing) R.string.player_playing else R.string.player_paused)

    // The window onto the page (§4.3): the current system never sits under the layer.
    val pages = ms.pages
    val veil = remember { Animatable(0f) }
    var shownPage by remember { mutableIntStateOf(-1) }
    val page = ms.page
    val top = pages?.windowTop(page, st.bar, if (ms.layer) ms.obscured else 0f) ?: 0f
    LaunchedEffect(pages, page, top) {
        pages ?: return@LaunchedEffect
        // A page turn cross-fades over 200 ms through the paper; with reduced motion it is instant.
        if (shownPage >= 0 && shownPage != page && !reducedMotion) {
            veil.animateTo(1f, tween(100))
            controller.scrollStandTo(top.roundToInt())
            veil.animateTo(0f, tween(100))
        } else {
            veil.snapTo(0f)
            controller.scrollStandTo(top.roundToInt())
        }
        shownPage = page
    }
    // Below the page's last whole system: paper, not half of the next one.
    val bottom = pages?.pageBottom(page, top) ?: ms.viewport
    if (pages != null && bottom < ms.viewport) {
        Box(Modifier.fillMaxWidth().height(with(density) { (ms.viewport - bottom).toDp() }).align(Alignment.BottomCenter).background(c.bg))
    }
    if (veil.value > 0f) Box(Modifier.matchParentSize().alpha(veil.value).background(c.bg))

    // The score: one element for TalkBack, the tap and swipe surface for touch, the focus for keys.
    Box(
        Modifier.matchParentSize()
            .semantics {
                testTag = "stand-score"
                contentDescription = summary
                stateDescription = stateText
                customActions = listOf(
                    CustomAccessibilityAction(nextPage) { onPage(page + 1); true },
                    CustomAccessibilityAction(prevPage) { onPage(page - 1); true },
                    CustomAccessibilityAction(nextBar) { onBar(1); true },
                    CustomAccessibilityAction(prevBar) { onBar(-1); true },
                    CustomAccessibilityAction(playBar) { controller.playBar(st.bar); true },
                )
            }
            .focusRequester(scoreFocus)
            .focusable()
            .pointerInput(slop, edge) {
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    var last = down.position
                    var moved = false
                    while (true) {
                        val e = awaitPointerEvent()
                        val ch = e.changes.firstOrNull { it.id == down.id } ?: break
                        last = ch.position
                        if ((last - down.position).getDistance() > slop) moved = true
                        ch.consume()
                        if (!ch.pressed) break
                    }
                    val d = last - down.position
                    // A tap acts on pointer-up (2.5.2); it never moves the cursor in the stand.
                    if (!moved) onTap()
                    else when (MusicStandRules.swipe(down.position.x, d.x, d.y, size.width.toFloat(), edge, minSwipe)) {
                        1 -> onPage(page + 1)
                        -1 -> onPage(page - 1)
                    }
                }
            },
    )

    if (ms.hint && !ms.layer) Surface(
        Modifier.align(Alignment.BottomCenter)
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom))
            .padding(bottom = BrasscribeSpace.s8, start = ScreenMargin, end = ScreenMargin),
        shape = MaterialTheme.shapes.medium, color = c.text, contentColor = c.bg,
    ) {
        Text(stringResource(R.string.stand_hint), style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3))
    }

    if (turnPill) TurnMusicPill(onTurnMusic, Modifier.align(Alignment.BottomCenter)
        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom))
        .offset { IntOffset(0, -(if (ms.layer) ms.obscured.roundToInt() else 0)) }
        .padding(bottom = BrasscribeSpace.s6))

    if (ms.layer) StandLayer(
        controller, st, ms, shape, onlyMine, onPage, onBar, onSpeed, onRepeat, onOnlyMine, onLock,
        Modifier.align(Alignment.BottomCenter).onGloballyPositioned { ms.obscured = (ms.viewport - it.positionInParent().y).coerceAtLeast(0f) },
    )
}

/** Turn the music (§4.4): the stand's own rotate button while it hides the system's. */
@Composable
private fun TurnMusicPill(onClick: () -> Unit, modifier: Modifier) {
    val c = BrasscribeTheme.colors
    val name = stringResource(R.string.stand_turn_name)
    Surface(
        modifier.heightIn(min = 48.dp).semantics { testTag = "stand-turn" },
        shape = RoundedCornerShape(percent = 50), color = c.surfaceRaised, contentColor = c.text,
        border = BorderStroke(1.dp, c.borderStrong), shadowElevation = if (c.isHighContrast) 0.dp else 1.dp,
    ) {
        Row(
            Modifier.clearAndSetSemantics { contentDescription = name; role = Role.Button; onClick { onClick(); true } }
                .clickable(onClick = onClick).heightIn(min = 48.dp).padding(horizontal = BrasscribeSpace.s5),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
        ) {
            BcIcon(R.drawable.ic_stand_rotate, null, Modifier.size(20.dp))
            Text(stringResource(R.string.stand_turn), style = MaterialTheme.typography.labelLarge)
        }
    }
}

/**
 * The control layer (§4.1): a card at the bottom. Upright on a phone it has three rows (the transport,
 * Speed and Repeat, then Only my part and Lock rotation); on its side and on a tablet one row that
 * wraps (the text size never clips it).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StandLayer(
    controller: ScoreController, st: ScoreUiState, ms: MusicStandState, shape: StandShape, onlyMine: Boolean,
    onPage: (Int) -> Unit, onBar: (Int) -> Unit, onSpeed: (Int) -> Unit, onRepeat: () -> Unit,
    onOnlyMine: () -> Unit, onLock: () -> Unit, modifier: Modifier,
) {
    val c = BrasscribeTheme.colors
    val page = ms.page
    Surface(
        modifier.windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
            .padding(horizontal = if (shape.tablet) BrasscribeSpace.s6 else BrasscribeSpace.s3, vertical = BrasscribeSpace.s3)
            .then(if (shape.tablet) Modifier.widthIn(max = 900.dp) else Modifier.fillMaxWidth())
            .onFocusChanged { ms.focusInLayer = it.hasFocus }
            .semantics { testTag = "stand-layer" }
            // A touch on the card is not a tap on the music, and it keeps the layer up a while longer.
            .pointerInput(Unit) { awaitEachGesture { awaitFirstDown(requireUnconsumed = false); ms.touches++ } },
        shape = MaterialTheme.shapes.large, color = c.surfaceRaised, contentColor = c.text,
        border = BorderStroke(1.dp, if (c.isHighContrast) c.borderStrong else c.border),
        shadowElevation = if (c.isHighContrast) 0.dp else 2.dp,
    ) {
        val transport = @Composable {
            PageButton(R.drawable.ic_stand_page_prev, stringResource(R.string.stand_prev_page), page > 0, "stand-prev-page") { onPage(page - 1) }
            IconButton({ onBar(-1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_previous_bar, stringResource(R.string.action_prev_bar)) }
            FilledIconButton(
                controller::togglePlay, Modifier.size(56.dp).semantics { testTag = "play" }, shape = CircleShape,
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.primary, contentColor = c.onPrimary),
            ) { BcIcon(if (st.playing) R.drawable.ic_bc_pause else R.drawable.ic_bc_play, stringResource(if (st.playing) R.string.pause else R.string.play)) }
            IconButton({ onBar(1) }, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_next_bar, stringResource(R.string.action_next_bar)) }
            PageButton(R.drawable.ic_stand_page_next, stringResource(R.string.stand_next_page), page + 1 < ms.pageCount, "stand-next-page") { onPage(page + 1) }
        }
        val repeat = @Composable {
            PracticeChip(
                st.loop?.let { stringResource(R.string.stand_repeat_on, it.first, it.last) } ?: stringResource(R.string.stand_repeat),
                st.loop != null, onRepeat, Modifier.semantics { testTag = "stand-repeat" }, icon = R.drawable.ic_bc_loop,
                role = if (st.loop != null || ms.lastLoop != null) Role.Switch else Role.Button,
            )
        }
        val gap = Arrangement.spacedBy(BrasscribeSpace.s3)
        if (!shape.landscape) Column(Modifier.padding(BrasscribeSpace.s3), verticalArrangement = gap) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically) { transport() }
            FlowRow(horizontalArrangement = gap, verticalArrangement = gap) {
                SpeedStepper(st.speed, onSpeed)
                repeat()
            }
            if (onlyMine || shape.lockAvailable) FlowRow(horizontalArrangement = gap, verticalArrangement = gap) {
                if (onlyMine) OnlyMineToggle(ms.onlyMine, onOnlyMine)
                if (shape.lockAvailable) LockToggle(ms.locked, onLock)
            }
        } else FlowRow(
            Modifier.padding(BrasscribeSpace.s3), horizontalArrangement = gap, verticalArrangement = gap,
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalAlignment = Alignment.CenterVertically) { transport() }
            Spacer(Modifier.size(BrasscribeSpace.s2))
            SpeedStepper(st.speed, onSpeed)
            repeat()
            if (shape.tablet && onlyMine) OnlyMineToggle(ms.onlyMine, onOnlyMine)
        }
    }
}

/** ‹ and › page buttons: a tonal well, so they read differently from the bar buttons. */
@Composable
private fun PageButton(icon: Int, label: String, enabled: Boolean, tag: String, onClick: () -> Unit) {
    val c = BrasscribeTheme.colors
    androidx.compose.material3.FilledTonalIconButton(
        onClick, Modifier.size(48.dp).semantics { testTag = tag }, enabled = enabled,
        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = c.secondary, contentColor = c.text,
            disabledContainerColor = c.secondary.copy(alpha = 0.5f), disabledContentColor = c.textMuted),
    ) { BcIcon(icon, label) }
}

/** − Speed 75% +: two steppers around the value (2.5.7), 5 % a step, 25 % to 150 %. No slider on the stand. */
@Composable
private fun SpeedStepper(speed: Int, onSpeed: (Int) -> Unit) {
    val c = BrasscribeTheme.colors
    Row(
        Modifier.heightIn(min = 48.dp).border(1.dp, c.borderStrong, BrasscribeButtonShape).background(c.surfaceRaised, BrasscribeButtonShape),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton({ onSpeed(speed - MusicStandRules.SPEED_STEP) }, Modifier.size(48.dp).semantics { testTag = "stand-slower" }, enabled = speed > 25) {
            BcIcon(R.drawable.ic_stand_minus, stringResource(R.string.stand_slower))
        }
        Text(stringResource(R.string.speed_chip, speed), style = MaterialTheme.typography.labelLarge, color = c.text,
            modifier = Modifier.padding(horizontal = BrasscribeSpace.s1))
        IconButton({ onSpeed(speed + MusicStandRules.SPEED_STEP) }, Modifier.size(48.dp).semantics { testTag = "stand-faster" }, enabled = speed < 150) {
            BcIcon(R.drawable.ic_stand_plus, stringResource(R.string.stand_faster))
        }
    }
}

/** Handles a key on the stand (§7); true when it was the stand's. */
fun standKey(e: androidx.compose.ui.input.key.KeyEvent, focusInLayer: Boolean, run: (StandCommand) -> Unit): Boolean {
    val n = e.nativeKeyEvent
    val cmd = MusicStandRules.command(e.key.nativeKeyCode, n.isCtrlPressed, n.isAltPressed, n.isShiftPressed) ?: return false
    // Space on a focused button presses that button; Tab still moves the focus.
    if (cmd == StandCommand.PLAY_PAUSE && focusInLayer && e.key.nativeKeyCode == android.view.KeyEvent.KEYCODE_SPACE) return false
    if (cmd == StandCommand.SHOW_CONTROLS) { if (e.type == KeyEventType.KeyDown) run(cmd); return false }
    if (e.type == KeyEventType.KeyDown) run(cmd)
    return true
}

/** A keyboard is in use (Tab, arrows): the layer then never hides by itself. */
@Composable
fun keyboardInUse(): Boolean = LocalInputModeManager.current.inputMode == InputMode.Keyboard

/** Locks the orientation the phone has now, or gives the choice back to the system. */
fun lockRotation(activity: Activity?, lock: Boolean, to: Int = ActivityInfo.SCREEN_ORIENTATION_LOCKED) {
    activity?.requestedOrientation = if (lock) to else ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
}

/** Hides the control layer after [MusicStandRules.HIDE_AFTER_MS] when it may hide by itself. */
@Composable
fun StandAutoHide(ms: MusicStandState, playing: Boolean, assistive: Boolean, keyboard: Boolean, keepVisible: Boolean, hide: () -> Unit) {
    LaunchedEffect(ms.open, ms.layer, playing, assistive, ms.layerFocused, keyboard, keepVisible, ms.touches) {
        if (!ms.open) return@LaunchedEffect
        // With a screen reader, switch access or the setting, the controls come back and stay.
        if (assistive || keepVisible) { ms.layer = true; return@LaunchedEffect }
        if (ms.layer && MusicStandRules.autoHides(playing, assistive, ms.layerFocused, keyboard, keepVisible)) {
            delay(MusicStandRules.HIDE_AFTER_MS)
            hide()
        }
    }
}
