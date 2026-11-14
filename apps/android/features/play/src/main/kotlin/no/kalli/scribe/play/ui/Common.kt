package no.kalli.scribe.play.ui

import no.kalli.scribe.play.R

import no.kalli.scribe.design.R as DesignR

import androidx.annotation.DrawableRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.calculateEndPadding
import androidx.compose.foundation.layout.calculateStartPadding
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.Composable
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.layout.layoutId
import androidx.compose.ui.unit.Constraints
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.windowInsetsBottomHeight
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import no.kalli.scribe.play.ui.theme.productColors
import no.kalli.scribe.design.ScribeButtonShape
import no.kalli.scribe.design.ScribeSize
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.Status

/** Phone side margin (system.md §2: 16 dp) and the height of the one primary button (52 dp). */
val ScreenMargin = ScribeSpace.s4
val PrimaryHeight = 52.dp

/** A screen title in the display face (Instrument Serif, 36 sp): the only place the serif appears. */
@Composable
fun ScreenTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.displaySmall, modifier = modifier.semantics { heading() })
}

/** The sentence under a screen title. */
@Composable
fun Lead(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.bodyLarge, color = ScribeTheme.colors.textMuted, modifier = modifier)
}

/** A heading inside a screen, in Roboto. */
@Composable
fun SubHeading(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = modifier.semantics { heading() })
}

/** The small capitals label above a group ("YOUR SCORES", "FORMATS"). */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        style = MaterialTheme.typography.labelMedium.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.SemiBold),
        color = ScribeTheme.colors.textMuted,
        modifier = modifier.padding(top = ScribeSpace.s2).semantics { heading() },
    )
}

/**
 * The status line: visible text that is also a polite live region, so changes (progress, "Repeating
 * bars 12 to 13", errors) reach screen-reader users without moving their focus (WCAG 4.1.3).
 */
@Composable
fun StatusLine(status: Status?, modifier: Modifier = Modifier) {
    // A snackbar, not a line of the page (review 2, P2-5): only messages said on this screen show,
    // for a few seconds; the live region still reads each one once.
    val since = remember { System.nanoTime() }
    var visible by remember { mutableStateOf<Status?>(null) }
    LaunchedEffect(status?.serial) {
        if (status == null || status.text.isEmpty() || status.serial < since) return@LaunchedEffect
        visible = status
        kotlinx.coroutines.delay(STATUS_MS)
        if (visible == status) visible = null
    }
    val s = visible ?: return
    if (s.quiet) {
        // Heard, not seen: a polite live region with nothing drawn.
        androidx.compose.foundation.layout.Box(modifier.size(1.dp).semantics { liveRegion = LiveRegionMode.Polite; contentDescription = s.text })
        return
    }
    val c = ScribeTheme.colors
    Surface(
        modifier.fillMaxWidth(), shape = MaterialTheme.shapes.medium, color = c.text, contentColor = c.bg,
    ) {
        Text(
            s.text,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s3).semantics { liveRegion = LiveRegionMode.Polite },
        )
    }
}

/** How long a status message stays on screen. */
const val STATUS_MS = 8_000L

/** 150 % text and up: segmented controls stack, cards put their button under the text. */
@Composable
fun largeText(): Boolean = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f

@Composable
fun BcIcon(@DrawableRes id: Int, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = Color.Unspecified) {
    Icon(painterResource(id), contentDescription, modifier.size(ScribeSize.iconLarge),
        tint = if (tint == Color.Unspecified) androidx.compose.material3.LocalContentColor.current else tint)
}

@Composable
private fun ButtonContent(text: String, @DrawableRes icon: Int?) {
    if (icon != null) {
        BcIcon(icon, null)
        Spacer(Modifier.size(ScribeSpace.s2))
    }
    Text(text, textAlign = TextAlign.Center, style = MaterialTheme.typography.labelLarge)
}

/** The one primary button per screen: ink fill (paper in dark), 12 dp corners, 52 dp tall, full width. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, @DrawableRes icon: Int? = null) {
    Button(onClick, modifier.fillMaxWidth().heightIn(min = PrimaryHeight), enabled = enabled, shape = ScribeButtonShape) {
        ButtonContent(text, icon)
    }
}

/** The second-most-likely action: a tonal (warm grey) fill. */
@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, @DrawableRes icon: Int? = null, fill: Boolean = true) {
    FilledTonalButton(onClick, (if (fill) modifier.fillMaxWidth() else modifier).heightIn(min = 48.dp), enabled = enabled, shape = ScribeButtonShape) {
        ButtonContent(text, icon)
    }
}

/** Outline buttons: Cancel on progress screens, the alternatives in a card. */
@Composable
fun OutlineButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, @DrawableRes icon: Int? = null, fill: Boolean = true) {
    OutlinedButton(
        onClick, (if (fill) modifier.fillMaxWidth() else modifier).heightIn(min = 48.dp), enabled = enabled, shape = ScribeButtonShape,
        border = BorderStroke(1.dp, ScribeTheme.colors.borderStrong),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = ScribeTheme.colors.text),
    ) { ButtonContent(text, icon) }
}

/** Plain text buttons (Skip, Change, Done in a bar, a dialog's answers), 48 dp tall. [destructive]: one that deletes or throws away, in the error colour. */
@Composable
fun PlainButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, destructive: Boolean = false) {
    TextButton(onClick, modifier.heightIn(min = 48.dp), enabled = enabled, shape = ScribeButtonShape,
        colors = ButtonDefaults.textButtonColors(contentColor = if (destructive) ScribeTheme.colors.error else ScribeTheme.colors.text)) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

/** A group of list rows: a raised surface with a hairline border and 16 dp corners. */
@Composable
fun RowGroup(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        color = ScribeTheme.colors.surfaceRaised,
        border = BorderStroke(1.dp, ScribeTheme.colors.border),
    ) { Column(content = content) }
}

@Composable
fun RowDivider() = HorizontalDivider(color = ScribeTheme.colors.border)

/** The 40 dp icon well in front of a list row. */
@Composable
fun IconWell(@DrawableRes icon: Int, size: Dp = 40.dp, tint: Color = Color.Unspecified) {
    Box(
        Modifier.size(size).background(ScribeTheme.colors.secondary, MaterialTheme.shapes.small),
        contentAlignment = Alignment.Center,
    ) { BcIcon(icon, null, tint = tint) }
}

/**
 * One list row: optional icon well, title, one subtitle line, and a chevron when it navigates.
 * At least 60 dp tall; the whole row is the target.
 */
@Composable
fun ListRow(
    title: String,
    onClick: (() -> Unit)?,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    @DrawableRes icon: Int? = null,
    chevron: Boolean = onClick != null,
    enabled: Boolean = true,
    trailing: (@Composable RowScope.() -> Unit)? = null,
    role: Role = Role.Button,
) {
    val c = ScribeTheme.colors
    Row(
        modifier.fillMaxWidth().heightIn(min = 60.dp)
            .then(if (onClick != null) Modifier.clickable(enabled = enabled, role = role, onClick = onClick) else Modifier)
            .padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s3),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
    ) {
        if (icon != null) IconWell(icon)
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = if (enabled) c.text else c.textMuted)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        trailing?.invoke(this)
        if (chevron) BcIcon(DesignR.drawable.ic_bc_open, null, tint = c.textMuted)
    }
}

/** A quiet note in a warm-grey box: where the work happens, what a region means. */
@Composable
fun InfoNote(text: String, modifier: Modifier = Modifier, @DrawableRes icon: Int = DesignR.drawable.ic_bc_info, boxed: Boolean = true) {
    val c = ScribeTheme.colors
    Row(
        modifier.fillMaxWidth()
            .then(if (boxed) Modifier.background(c.surface, MaterialTheme.shapes.medium).border(1.dp, c.border, MaterialTheme.shapes.medium) else Modifier)
            .padding(if (boxed) ScribeSpace.s4 else ScribeSpace.s0),
        horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s3),
    ) {
        BcIcon(icon, null, tint = if (boxed) c.text else c.textMuted)
        Text(text, style = MaterialTheme.typography.bodyMedium, color = if (boxed) c.text else c.textMuted)
    }
}

/**
 * One line above the player when the band sounds are not installed: what to do next, and where
 * they were looked for under the tech-person details.
 */
@Composable
fun BandSoundsMissing(expected: String, modifier: Modifier = Modifier) {
    var details by remember { mutableStateOf(false) }
    val c = ScribeTheme.colors
    Column(modifier.fillMaxWidth().padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s2)) {
        InfoNote(stringResource(R.string.band_sounds_missing), boxed = false)
        if (expected.isNotBlank()) {
            PlainButton(stringResource(if (details) R.string.details_hide else R.string.details_show), { details = !details })
            if (details) Text(expected, style = MaterialTheme.typography.bodySmall, color = c.textMuted)
        }
    }
}

/**
 * A non-urgent notice folded to one line (a phone on its side, where the score needs the height):
 * the whole line is a 48 dp button that opens the notice in full.
 */
@Composable
fun NoticeLine(text: String, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    val c = ScribeTheme.colors
    Row(
        modifier.fillMaxWidth().sizeIn(minHeight = 48.dp).clickable(role = Role.Button, onClick = onOpen),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s3),
    ) {
        BcIcon(DesignR.drawable.ic_bc_info, null, tint = c.textMuted)
        Text(text, style = MaterialTheme.typography.bodyMedium, color = c.textMuted, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        BcIcon(DesignR.drawable.ic_bc_open, null, tint = c.textMuted)
    }
}

/** The brand mark (a flat sign that flares like a bell), in brass. For brand moments only. */
@Composable
fun BrandMark(size: Dp = 56.dp, modifier: Modifier = Modifier) {
    // The monochrome launcher layer is the mark inside the 108-unit adaptive-icon canvas; crop its margin.
    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Icon(painterResource(DesignR.drawable.ic_launcher_monochrome), null, Modifier.size(size * 2.1f), tint = ScribeTheme.colors.brand)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayTopBar(title: String?, onBack: (() -> Unit)?, backLabel: String? = null, titleIsHeading: Boolean = false, actions: @Composable RowScope.() -> Unit = {}) {
    val c = ScribeTheme.colors
    // With large text the back label would collide with the title and the actions: keep the arrow.
    val backText = backLabel.takeIf { androidx.compose.ui.platform.LocalDensity.current.fontScale < 1.3f }
    CenterAlignedTopAppBar(
        // A screen whose content has no title of its own (the tab) takes the top bar's as its heading.
        title = { if (title != null) Text(title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = if (titleIsHeading) Modifier.semantics { heading() } else Modifier) },
        navigationIcon = {
            if (onBack != null) {
                if (backText != null) {
                    TextButton(onBack, Modifier.heightIn(min = 48.dp), colors = ButtonDefaults.textButtonColors(contentColor = c.text)) {
                        BcIcon(DesignR.drawable.ic_bc_back, null)
                        Spacer(Modifier.size(ScribeSpace.s1))
                        Text(backText, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.widthIn(max = 120.dp))
                    }
                } else IconButton(onBack, Modifier.size(48.dp)) { BcIcon(DesignR.drawable.ic_bc_back, stringResource(R.string.back)) }
            }
        },
        actions = actions,
        // On its side the bar is as low as its 48 dp buttons.
        expandedHeight = if (shortScreen()) 48.dp else TopAppBarDefaults.TopAppBarExpandedHeight,
        colors = TopAppBarDefaults.centerAlignedTopAppBarColors(containerColor = c.bg, scrolledContainerColor = c.bg),
    )
}

/**
 * Every flow screen: a top bar with the back button, a scrolling column at the 16 dp margin, and a
 * bottom slot for the one primary action, docked above the navigation bar (system.md §2). On a short
 * screen, actions that would take more than [BAND_SHARE] of the height are not docked: they come after
 * the content and scroll with it.
 *
 * The docked band is laid out after the content, in the body, not as the scaffold's bottom bar: the
 * keyboard's Tab follows the layout, and the screen's content comes before the button that acts on it
 * (WCAG 2.4.3). As the scaffold's bottom bar it came before the content.
 */
@Composable
fun PlayScaffold(
    title: String?,
    onBack: (() -> Unit)?,
    status: Status?,
    scroll: Boolean = true,
    backLabel: String? = null,
    actions: @Composable RowScope.() -> Unit = {},
    bottom: (@Composable ColumnScope.() -> Unit)? = null,
    /** How far something under way has come: over the actions like a status message, and like it no part of their measure. */
    progress: (@Composable ColumnScope.() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        containerColor = ScribeTheme.colors.bg,
        topBar = { PlayTopBar(title, onBack, backLabel, actions = actions) },
    ) { padding ->
        // Clear of the top bar and the system bars at the sides; the navigation bar's height is kept free below the band.
        val direction = LocalLayoutDirection.current
        val around = PaddingValues(top = padding.calculateTopPadding(),
            start = padding.calculateStartPadding(direction), end = padding.calculateEndPadding(direction))
        // Two parts scroll, one inside the other, and only one of them at a time: the content by itself over docked
        // actions, or the content and the actions as one where they are not docked. So the actions are composed in
        // one place whichever it is, and which it is can be decided while they are measured.
        val outer = rememberScrollState()
        val inner = rememberScrollState()
        Column(Modifier.fillMaxSize().padding(around).consumeWindowInsets(around)) {
            Layout(
                modifier = Modifier.weight(1f).fillMaxWidth().then(if (scroll) Modifier.verticalScroll(outer) else Modifier),
                content = {
                    Column(
                        Modifier.layoutId(Part.CONTENT).fillMaxWidth().then(if (scroll) Modifier.verticalScroll(inner) else Modifier).padding(horizontal = ScreenMargin),
                        verticalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
                    ) {
                        content()
                        Spacer(Modifier.size(ScribeSpace.s4))
                    }
                    // Docked actions sit on an opaque band with a hairline above it, so the content ends
                    // visibly at the band instead of looking cut off behind the button.
                    if (bottom != null) {
                        HorizontalDivider(Modifier.layoutId(Part.HAIRLINE), thickness = 1.dp, color = ScribeTheme.colors.border)
                        Column(
                            Modifier.layoutId(Part.ACTIONS).fillMaxWidth().background(ScribeTheme.colors.bg).padding(horizontal = ScreenMargin, vertical = ScribeSpace.s3),
                            verticalArrangement = Arrangement.spacedBy(ScribeSpace.s3), content = bottom,
                        )
                    }
                    Column(Modifier.layoutId(Part.STATUS).fillMaxWidth().background(ScribeTheme.colors.bg).padding(horizontal = ScreenMargin)) {
                        val over = Modifier.padding(top = if (bottom != null) ScribeSpace.s3 else ScribeSpace.s0)
                        StatusLine(status, over)
                        if (progress != null) Column(over, verticalArrangement = Arrangement.spacedBy(ScribeSpace.s3), content = progress)
                    }
                },
            ) { parts, constraints ->
                // The height the content and the actions share: under the top bar and above the navigation bar. (Where
                // the screen scrolls, the scrolling around this layout hands it on as the least height.)
                val view = constraints.minHeight
                val across = Constraints.fixedWidth(constraints.maxWidth)
                fun part(which: Part) = parts.firstOrNull { it.layoutId == which }?.measure(across)
                val hairline = part(Part.HAIRLINE)
                val actions = part(Part.ACTIONS)
                val status = part(Part.STATUS)
                val band = (hairline?.height ?: 0) + (actions?.height ?: 0)
                val message = status?.height ?: 0
                // The actions are measured first and the choice is made here, in the one pass: nothing moves after the
                // first frame. A message is not part of the measure, so one that comes and goes undocks nothing.
                val docked = !scroll || band <= view * BAND_SHARE
                val page = parts.first { it.layoutId == Part.CONTENT }.measure(
                    // Docked actions leave the content the rest of the height, and it scrolls there by itself; actions
                    // that are not docked come after the whole of it, and the two scroll as one.
                    // (Its own scrolling takes no endless height, so it is offered more than any page is long.)
                    if (docked) Constraints.fixed(constraints.maxWidth, (view - band - message).coerceAtLeast(0))
                    else Constraints.fitPrioritizingWidth(constraints.maxWidth, constraints.maxWidth, 0, PAGE_AT_MOST),
                )
                val gap = ScribeSpace.s3.roundToPx()
                layout(constraints.maxWidth, if (docked) view else maxOf(view, page.height + band)) {
                    page.place(0, 0)
                    if (docked) {
                        hairline?.place(0, view - band - message)
                        status?.place(0, view - band - message + (hairline?.height ?: 0))
                        actions?.place(0, view - actions.height)
                    } else {
                        hairline?.place(0, page.height)
                        actions?.place(0, page.height + (hairline?.height ?: 0))
                        // A message is docked all the same: it stays at the foot of what is in view while the rest scrolls.
                        status?.place(0, outer.value + view - message - gap)
                    }
                }
            }
            // Docked or not, nothing is drawn under the navigation bar.
            Spacer(Modifier.fillMaxWidth().windowInsetsBottomHeight(WindowInsets.navigationBars))
        }
    }
}

/** More pixels than a flow screen's content is high. */
private const val PAGE_AT_MOST = 200_000

private enum class Part { CONTENT, HAIRLINE, ACTIONS, STATUS }

/**
 * The most of the height under the top bar and above the navigation bar that docked actions may take: a third. Taller
 * ones scroll with the content. (One button stays docked on a phone on its side; with a line of text over it, it would not: such a line
 * belongs last in the content.)
 */
private const val BAND_SHARE = 1 / 3f

/** A phone on its side: so little height that every bar gives some of its own to the content. */
@Composable
fun shortScreen(): Boolean = androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp < 480

/** The uncertainty mark as text glyphs: "?" and a boxed "?" (visual-design-tokens.md §2), in the note colour. */
@Composable
fun UncertainMark(very: Boolean, modifier: Modifier = Modifier, fontSize: androidx.compose.ui.unit.TextUnit = 16.sp) {
    val c = ScribeTheme.colors
    val color = if (very) productColors.veryUncertain else c.uncertain
    val text = @Composable { Text("?", color = color, fontSize = fontSize, fontWeight = FontWeight.Bold, lineHeight = fontSize) }
    if (very) Box(modifier.border(1.5.dp, color, RoundedCornerShape(3.dp)).padding(horizontal = 4.dp, vertical = 1.dp)) { text() }
    else Box(modifier.padding(horizontal = 4.dp)) { text() }
}

/** A choice chip that is on: tonal fill, ink border and a tick. Ink fill stays for the primary. */
@Composable
fun PracticeChip(label: String, on: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, @DrawableRes icon: Int? = null, role: Role = Role.Switch, accessibleName: String? = null, @DrawableRes trailingIcon: Int? = null) {
    val c = ScribeTheme.colors
    Row(
        modifier.sizeIn(minHeight = 48.dp)
            .background(if (on) c.secondary else c.surfaceRaised, ScribeButtonShape)
            .border(if (on) 1.5.dp else 1.dp, if (on) c.text else c.borderStrong, ScribeButtonShape)
            .then(
                if (role == Role.Switch) Modifier.toggleable(value = on, role = Role.Switch, onValueChange = { onClick() })
                else Modifier.clickable(role = role, onClick = onClick),
            )
            .then(if (accessibleName != null) Modifier.semantics(mergeDescendants = true) { contentDescription = accessibleName } else Modifier)
            .padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (on && role == Role.Switch) BcIcon(DesignR.drawable.ic_bc_done, null, Modifier.size(18.dp))
        else if (icon != null) BcIcon(icon, null, Modifier.size(20.dp))
        Text(label, style = MaterialTheme.typography.labelLarge, color = c.text, maxLines = 1,
            modifier = if (accessibleName != null) Modifier.clearAndSetSemantics {} else Modifier)
        if (trailingIcon != null) BcIcon(trailingIcon, null, Modifier.size(20.dp))
    }
}

/**
 * Every bottom sheet in the app: fully open (a half-open sheet leaves its end below the screen at large
 * text), and its content kept clear of the navigation bar and gesture handle, at the bottom and, with
 * the bar on the side in landscape, at the sides. Insets the sheet already applied are consumed, so
 * nothing is padded twice.
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun PlaySheet(
    onDismiss: () -> Unit,
    containerColor: androidx.compose.ui.graphics.Color,
    dragHandle: Boolean = true,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    androidx.compose.material3.ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = containerColor,
        sheetState = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true),
        // The Material 3 handle is 32 dp wide; the sheet puts its dismiss/expand actions on the handle's own
        // bounds, so a 48 dp box around it makes that a full-size touch target (and passes ATF's check).
        dragHandle = if (dragHandle) ({
            androidx.compose.foundation.layout.Box(
                Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp),
                contentAlignment = androidx.compose.ui.Alignment.Center,
            ) { androidx.compose.material3.BottomSheetDefaults.DragHandle() }
        }) else null,
    ) {
        androidx.compose.foundation.layout.Column(
            Modifier.windowInsetsPadding(
                androidx.compose.foundation.layout.WindowInsets.safeDrawing.only(
                    androidx.compose.foundation.layout.WindowInsetsSides.Horizontal + androidx.compose.foundation.layout.WindowInsetsSides.Bottom,
                ),
            ),
            content = content,
        )
    }
}
