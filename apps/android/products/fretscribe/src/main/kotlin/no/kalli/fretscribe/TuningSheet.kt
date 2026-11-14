package no.kalli.fretscribe

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.coerceAtLeast
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.engine.TabOptions
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.ui.PlainButton
import no.kalli.scribe.play.ui.PlaySheet
import no.kalli.scribe.play.ui.PrimaryButton
import no.kalli.scribe.tab.Instrument

/**
 * Tuning and capo (design/brands/fretscribe/system.md §4): the tunings of the tab's instrument and, for an instrument
 * a capo is used on, the fret it is at. Another tuning writes the same notes where they are played in it. A capo that
 * was moved asks once what is kept: **the sound** (the same notes, at new frets) or **the shapes** (the same frets,
 * so the song sounds higher or lower). The tab is written again on this phone ([TabRewrite]) and saved with the song;
 * [change] is given the new page. What else can be changed about a song (the octave, what was recorded) is the
 * computer's to write: Check the song.
 */
@Composable
internal fun TuningSheet(sheet: TabSheet, title: String, change: (String) -> Unit, checkTheSong: () -> Unit, close: () -> Unit) {
    val c = ScribeTheme.colors
    val kind = sheet.kind ?: run { close(); return }
    val scope = rememberCoroutineScope()
    val was = sheet.tuning.takeIf { it in kind.tunings } ?: kind.defaultTuning
    var tuning by rememberSaveable { mutableStateOf(was) }
    var capo by rememberSaveable { mutableIntStateOf(sheet.capo) }
    var keepShapes by rememberSaveable { mutableStateOf(false) }
    var writing by rememberSaveable { mutableStateOf(false) }
    var failed by rememberSaveable { mutableStateOf(false) }
    val takesCapo = Instrument.of(kind)?.takesCapo == true || sheet.capo > 0
    val changed = tuning != was || capo != sheet.capo

    fun write() {
        if (writing) return
        writing = true
        failed = false
        scope.launch {
            val page = try {
                withContext(Dispatchers.Default) {
                    // The shapes are kept by a capo alone: in another tuning the same frets are other notes.
                    TabRewrite.rewrite(title, sheet.musicXml, sheet.index, kind, tuning, capo, sheet.layout, keepShapes && capo != sheet.capo && tuning == was)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.w(PlayViewModel.TAG, "the tab could not be written again", e)
                null
            }
            writing = false
            if (page == null) failed = true else { change(page); close() }
        }
    }

    PlaySheet(onDismiss = close, containerColor = c.bg) {
        // A guitar's tunings and its capo are taller than a small screen: the sheet stops under the status bar (taller than
        // that it would go up under it, its handle with it), and scrolls.
        val bars = WindowInsets.systemBars.asPaddingValues().let { it.calculateTopPadding() + it.calculateBottomPadding() }
        Column(Modifier.fillMaxWidth().heightIn(max = (LocalConfiguration.current.screenHeightDp.dp - 48.dp - bars).coerceAtLeast(160.dp))
            .verticalScroll(rememberScrollState()).padding(horizontal = ScribeSpace.s4).testTag("fs-tuning"),
            verticalArrangement = Arrangement.spacedBy(ScribeSpace.s2)) {
            Text(stringResource(R.string.fs_tuning_title), style = MaterialTheme.typography.titleLarge, color = c.text, modifier = Modifier.semantics { heading() })
            if (kind.tunings.size > 1) {
                Text(stringResource(R.string.fs_check_tuning), style = MaterialTheme.typography.titleMedium, color = c.text, modifier = Modifier.semantics { heading() })
                Column(Modifier.selectableGroup()) {
                    kind.tunings.forEach { id ->
                        val on = id == tuning
                        val spoken = tuningName(id, spoken = true, kind = kind)
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                .selectable(selected = on, enabled = !writing, role = Role.RadioButton) { tuning = id }
                                .semantics { contentDescription = spoken }
                                .testTag("fs-tuning-$id").padding(horizontal = ScribeSpace.s2, vertical = ScribeSpace.s1),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
                        ) {
                            RadioButton(selected = on, onClick = null, colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
                            Text(tuningName(id, kind = kind), Modifier.weight(1f).clearAndSetSemantics { }, style = MaterialTheme.typography.bodyLarge, color = c.text)
                        }
                    }
                }
            }
            if (takesCapo) {
                HorizontalDivider(thickness = 1.dp, color = c.border)
                val says = if (capo > 0) stringResource(R.string.fs_tuning_capo_at, capo) else stringResource(R.string.fs_tuning_capo_none)
                val lower = stringResource(R.string.fs_tuning_capo_lower)
                val higher = stringResource(R.string.fs_tuning_capo_higher)
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.fs_tuning_capo), Modifier.weight(1f).semantics { heading() }, style = MaterialTheme.typography.titleMedium, color = c.text)
                    IconButton({ capo-- }, Modifier.size(48.dp).testTag("fs-tuning-capo-down").semantics { contentDescription = lower }, enabled = capo > 0 && !writing) {
                        Text("−", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.clearAndSetSemantics { })
                    }
                    Text(says, style = MaterialTheme.typography.bodyLarge, color = c.text, textAlign = TextAlign.Center,
                        modifier = Modifier.widthIn(min = 72.dp).testTag("fs-tuning-capo").semantics { liveRegion = LiveRegionMode.Polite })
                    IconButton({ capo++ }, Modifier.size(48.dp).testTag("fs-tuning-capo-up").semantics { contentDescription = higher }, enabled = capo < TabOptions.MAX_CAPO && !writing) {
                        Text("+", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.clearAndSetSemantics { })
                    }
                }
                // What is kept when the capo is moved: asked once it has been, and only when the tuning stays. (It is there
                // from the start, off: a sheet that grows while it is open is pushed up under the top of the screen.)
                val asks = capo != sheet.capo && tuning == was
                Column(Modifier.selectableGroup().testTag("fs-tuning-keep")) {
                    listOf(false to (R.string.fs_tuning_keep_sound to R.string.fs_tuning_keep_sound_tip), true to (R.string.fs_tuning_keep_shapes to R.string.fs_tuning_keep_shapes_tip)).forEach { (shapes, words) ->
                        val on = asks && keepShapes == shapes
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 56.dp)
                                .selectable(selected = on, enabled = asks && !writing, role = Role.RadioButton) { keepShapes = shapes }
                                .testTag(if (shapes) "fs-tuning-keep-shapes" else "fs-tuning-keep-sound").padding(horizontal = ScribeSpace.s2, vertical = ScribeSpace.s1),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s4),
                        ) {
                            RadioButton(selected = on, onClick = null, enabled = asks, colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
                            Column(Modifier.weight(1f)) {
                                Text(stringResource(words.first), style = MaterialTheme.typography.bodyLarge, color = if (asks) c.text else c.text.copy(alpha = 0.38f))
                                Text(stringResource(words.second), style = MaterialTheme.typography.bodyMedium, color = if (asks) c.textMuted else c.textMuted.copy(alpha = 0.38f))
                            }
                        }
                    }
                }
            }
            // What is being done, and what went wrong, are said once.
            Column(Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite }) {
                if (writing) {
                    Text(stringResource(R.string.fs_tuning_writing), style = MaterialTheme.typography.bodyMedium, color = c.text)
                    LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = ScribeSpace.s1), color = c.brand, trackColor = c.border)
                }
                if (failed) Text(stringResource(R.string.fs_tuning_failed), style = MaterialTheme.typography.bodyMedium, color = c.text, modifier = Modifier.testTag("fs-tuning-failed"))
            }
            PrimaryButton(stringResource(R.string.fs_tuning_write), ::write, Modifier.testTag("fs-tuning-write"), enabled = changed && !writing)
            Text(stringResource(R.string.fs_tuning_on_phone), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s2, Alignment.End)) {
                PlainButton(stringResource(R.string.fs_check_title), { close(); checkTheSong() }, Modifier.testTag("fs-tuning-check"))
                PlainButton(stringResource(R.string.cancel), close, Modifier.testTag("fs-tuning-cancel"))
            }
        }
    }
}
