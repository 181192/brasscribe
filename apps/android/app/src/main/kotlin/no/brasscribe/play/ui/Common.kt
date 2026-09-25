package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import no.brasscribe.play.R
import no.brasscribe.play.Status
import no.brasscribe.play.ui.theme.LocalPlayTokens

/** A screen heading: exposed as a heading so TalkBack's heading navigation finds it. */
@Composable
fun Heading(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.headlineSmall, modifier = modifier.semantics { heading() })
}

@Composable
fun SubHeading(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = modifier.semantics { heading() })
}

/**
 * The status line: visible text that is also a polite live region, so changes (progress, "Loop set",
 * errors) reach screen-reader users without moving their focus (WCAG 4.1.3).
 */
@Composable
fun StatusLine(status: Status?, modifier: Modifier = Modifier) {
    val t = LocalPlayTokens.current
    // An empty live region would be an unlabeled focusable item; the line appears with its first message.
    if (status == null || status.text.isEmpty()) return
    Text(
        status.text,
        color = t.text,
        style = MaterialTheme.typography.bodyMedium,
        modifier = modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite },
    )
}

@Composable
fun BigButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, primary: Boolean = true) {
    val m = modifier.fillMaxWidth().heightIn(min = 56.dp)
    if (primary) Button(onClick = onClick, enabled = enabled, modifier = m) { Text(text, textAlign = TextAlign.Center) }
    else OutlinedButton(onClick = onClick, enabled = enabled, modifier = m) { Text(text, textAlign = TextAlign.Center) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayScaffold(
    title: String,
    onBack: (() -> Unit)?,
    status: Status?,
    scroll: Boolean = true,
    actions: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    if (onBack != null) IconButton(onClick = onBack) { Icon(BackArrow, contentDescription = stringResource(R.string.back)) }
                },
                actions = { actions() },
            )
        },
    ) { padding ->
        val base = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp)
        Column(
            modifier = if (scroll) base.verticalScroll(rememberScrollState()) else base,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            StatusLine(status)
            content()
        }
    }
}

/** A plain back arrow, drawn here to avoid pulling in an icon library. */
val BackArrow: ImageVector = ImageVector.Builder("back", 24.dp, 24.dp, 24f, 24f).apply {
    path(fill = SolidColor(Color.Black)) {
        moveTo(20f, 11f); horizontalLineTo(7.83f); lineTo(13.42f, 5.41f); lineTo(12f, 4f); lineTo(4f, 12f)
        lineTo(12f, 20f); lineTo(13.41f, 18.59f); lineTo(7.83f, 13f); horizontalLineTo(20f); close()
    }
}.build()
