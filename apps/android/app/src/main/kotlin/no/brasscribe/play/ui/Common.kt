package no.brasscribe.play.ui

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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeSize
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.R
import no.brasscribe.play.Status

/** Phone side margin (system.md §2: 16 dp) and the height of the one primary button (52 dp). */
val ScreenMargin = BrasscribeSpace.s4
val PrimaryHeight = 52.dp

/** A screen title in the display face (Instrument Serif, 36 sp): the only place the serif appears. */
@Composable
fun ScreenTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.displaySmall, modifier = modifier.semantics { heading() })
}

/** The sentence under a screen title. */
@Composable
fun Lead(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.bodyLarge, color = BrasscribeTheme.colors.textMuted, modifier = modifier)
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
        color = BrasscribeTheme.colors.textMuted,
        modifier = modifier.padding(top = BrasscribeSpace.s2).semantics { heading() },
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
    val c = BrasscribeTheme.colors
    Surface(
        modifier.fillMaxWidth(), shape = MaterialTheme.shapes.medium, color = c.text, contentColor = c.bg,
    ) {
        Text(
            s.text,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3).semantics { liveRegion = LiveRegionMode.Polite },
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
    Icon(painterResource(id), contentDescription, modifier.size(BrasscribeSize.iconLarge),
        tint = if (tint == Color.Unspecified) androidx.compose.material3.LocalContentColor.current else tint)
}

@Composable
private fun ButtonContent(text: String, @DrawableRes icon: Int?) {
    if (icon != null) {
        BcIcon(icon, null)
        Spacer(Modifier.size(BrasscribeSpace.s2))
    }
    Text(text, textAlign = TextAlign.Center, style = MaterialTheme.typography.labelLarge)
}

/** The one primary button per screen: ink fill (paper in dark), 12 dp corners, 52 dp tall, full width. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, @DrawableRes icon: Int? = null) {
    Button(onClick, modifier.fillMaxWidth().heightIn(min = PrimaryHeight), enabled = enabled, shape = BrasscribeButtonShape) {
        ButtonContent(text, icon)
    }
}

/** The second-most-likely action: a tonal (warm grey) fill. */
@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, @DrawableRes icon: Int? = null, fill: Boolean = true) {
    FilledTonalButton(onClick, (if (fill) modifier.fillMaxWidth() else modifier).heightIn(min = 48.dp), enabled = enabled, shape = BrasscribeButtonShape) {
        ButtonContent(text, icon)
    }
}

/** Outline buttons: Cancel on progress screens, the alternatives in a card. */
@Composable
fun OutlineButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, @DrawableRes icon: Int? = null, fill: Boolean = true) {
    OutlinedButton(
        onClick, (if (fill) modifier.fillMaxWidth() else modifier).heightIn(min = 48.dp), enabled = enabled, shape = BrasscribeButtonShape,
        border = BorderStroke(1.dp, BrasscribeTheme.colors.borderStrong),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = BrasscribeTheme.colors.text),
    ) { ButtonContent(text, icon) }
}

/** Plain text buttons (Skip, Change, Done in a bar), 48 dp tall. */
@Composable
fun PlainButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    TextButton(onClick, modifier.heightIn(min = 48.dp), enabled = enabled, shape = BrasscribeButtonShape,
        colors = ButtonDefaults.textButtonColors(contentColor = BrasscribeTheme.colors.text)) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

/** A group of list rows: a raised surface with a hairline border and 16 dp corners. */
@Composable
fun RowGroup(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        color = BrasscribeTheme.colors.surfaceRaised,
        border = BorderStroke(1.dp, BrasscribeTheme.colors.border),
    ) { Column(content = content) }
}

@Composable
fun RowDivider() = HorizontalDivider(color = BrasscribeTheme.colors.border)

/** The 40 dp icon well in front of a list row. */
@Composable
fun IconWell(@DrawableRes icon: Int, size: Dp = 40.dp, tint: Color = Color.Unspecified) {
    Box(
        Modifier.size(size).background(BrasscribeTheme.colors.secondary, MaterialTheme.shapes.small),
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
) {
    val c = BrasscribeTheme.colors
    Row(
        modifier.fillMaxWidth().heightIn(min = 60.dp)
            .then(if (onClick != null) Modifier.clickable(enabled = enabled, role = Role.Button, onClick = onClick) else Modifier)
            .padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4),
    ) {
        if (icon != null) IconWell(icon)
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = if (enabled) c.text else c.textMuted)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        trailing?.invoke(this)
        if (chevron) BcIcon(R.drawable.ic_bc_open, null, tint = c.textMuted)
    }
}

/** A quiet note in a warm-grey box: where the work happens, what a region means. */
@Composable
fun InfoNote(text: String, modifier: Modifier = Modifier, @DrawableRes icon: Int = R.drawable.ic_bc_info, boxed: Boolean = true) {
    val c = BrasscribeTheme.colors
    Row(
        modifier.fillMaxWidth()
            .then(if (boxed) Modifier.background(c.surface, MaterialTheme.shapes.medium).border(1.dp, c.border, MaterialTheme.shapes.medium) else Modifier)
            .padding(if (boxed) BrasscribeSpace.s4 else BrasscribeSpace.s0),
        horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
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
    val c = BrasscribeTheme.colors
    Column(modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s2)) {
        InfoNote(stringResource(R.string.band_sounds_missing), boxed = false)
        if (expected.isNotBlank()) {
            PlainButton(stringResource(if (details) R.string.details_hide else R.string.details_show), { details = !details })
            if (details) Text(expected, style = MaterialTheme.typography.bodySmall, color = c.textMuted)
        }
    }
}

/** The brand mark (a flat sign that flares like a bell), in brass. For brand moments only. */
@Composable
fun BrandMark(size: Dp = 56.dp, modifier: Modifier = Modifier) {
    // The monochrome launcher layer is the mark inside the 108-unit adaptive-icon canvas; crop its margin.
    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Icon(painterResource(R.drawable.ic_launcher_monochrome), null, Modifier.size(size * 2.1f), tint = BrasscribeTheme.colors.brass)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayTopBar(title: String?, onBack: (() -> Unit)?, backLabel: String? = null, actions: @Composable RowScope.() -> Unit = {}) {
    val c = BrasscribeTheme.colors
    // With large text the back label would collide with the title and the actions: keep the arrow.
    val backText = backLabel.takeIf { androidx.compose.ui.platform.LocalDensity.current.fontScale < 1.3f }
    CenterAlignedTopAppBar(
        title = { if (title != null) Text(title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis) },
        navigationIcon = {
            if (onBack != null) {
                if (backText != null) {
                    TextButton(onBack, Modifier.heightIn(min = 48.dp), colors = ButtonDefaults.textButtonColors(contentColor = c.text)) {
                        BcIcon(R.drawable.ic_bc_back, null)
                        Spacer(Modifier.size(BrasscribeSpace.s1))
                        Text(backText, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.widthIn(max = 120.dp))
                    }
                } else IconButton(onBack, Modifier.size(48.dp)) { BcIcon(R.drawable.ic_bc_back, stringResource(R.string.back)) }
            }
        },
        actions = actions,
        colors = TopAppBarDefaults.centerAlignedTopAppBarColors(containerColor = c.bg, scrolledContainerColor = c.bg),
    )
}

/**
 * Every flow screen: a top bar with the back button, a scrolling column at the 16 dp margin, and a
 * bottom slot for the one primary action, pinned above the navigation bar (system.md §2).
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
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        containerColor = BrasscribeTheme.colors.bg,
        topBar = { PlayTopBar(title, onBack, backLabel, actions) },
        bottomBar = {
            Column(
                Modifier.fillMaxWidth().background(BrasscribeTheme.colors.bg).navigationBarsPadding()
                    .padding(horizontal = ScreenMargin, vertical = if (bottom != null) BrasscribeSpace.s3 else BrasscribeSpace.s0),
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
            ) {
                StatusLine(status)
                bottom?.invoke(this)
            }
        },
    ) { padding ->
        val base = Modifier.fillMaxSize().padding(padding).padding(horizontal = ScreenMargin)
        Column(
            modifier = if (scroll) base.verticalScroll(rememberScrollState()) else base,
            verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4),
        ) {
            content()
            Spacer(Modifier.size(BrasscribeSpace.s4))
        }
    }
}

/** The uncertainty mark as text glyphs: "?" and a boxed "?" (visual-design-tokens.md §2), in the note colour. */
@Composable
fun UncertainMark(very: Boolean, modifier: Modifier = Modifier, fontSize: androidx.compose.ui.unit.TextUnit = 16.sp) {
    val c = BrasscribeTheme.colors
    val color = if (very) c.veryUncertain else c.uncertain
    val text = @Composable { Text("?", color = color, fontSize = fontSize, fontWeight = FontWeight.Bold, lineHeight = fontSize) }
    if (very) Box(modifier.border(1.5.dp, color, RoundedCornerShape(3.dp)).padding(horizontal = 4.dp, vertical = 1.dp)) { text() }
    else Box(modifier.padding(horizontal = 4.dp)) { text() }
}

/** A choice chip that is on: tonal fill, ink border and a tick. Ink fill stays for the primary. */
@Composable
fun PracticeChip(label: String, on: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, @DrawableRes icon: Int? = null, role: Role = Role.Switch, accessibleName: String? = null, @DrawableRes trailingIcon: Int? = null) {
    val c = BrasscribeTheme.colors
    Row(
        modifier.sizeIn(minHeight = 48.dp)
            .background(if (on) c.secondary else c.surfaceRaised, BrasscribeButtonShape)
            .border(if (on) 1.5.dp else 1.dp, if (on) c.text else c.borderStrong, BrasscribeButtonShape)
            .then(
                if (role == Role.Switch) Modifier.toggleable(value = on, role = Role.Switch, onValueChange = { onClick() })
                else Modifier.clickable(role = role, onClick = onClick),
            )
            .then(if (accessibleName != null) Modifier.semantics(mergeDescendants = true) { contentDescription = accessibleName } else Modifier)
            .padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (on && role == Role.Switch) BcIcon(R.drawable.ic_bc_done, null, Modifier.size(18.dp))
        else if (icon != null) BcIcon(icon, null, Modifier.size(20.dp))
        Text(label, style = MaterialTheme.typography.labelLarge, color = c.text, maxLines = 1,
            modifier = if (accessibleName != null) Modifier.clearAndSetSemantics {} else Modifier)
        if (trailingIcon != null) BcIcon(trailingIcon, null, Modifier.size(20.dp))
    }
}

