package no.brasscribe.play.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.TranscriptionResult
import no.brasscribe.play.model.PitchMode

/** One row of the per-part talking score: a bar heading or one event line of that bar. */
private data class Row(val bar: Int, val barIndex: Int, val text: String, val heading: Boolean)

/**
 * The talking score of the part shown in the score view, from the Rust core's talking score of the
 * arranged MusicXML (spec §6: a heading per bar, one line per event, written pitch of that part).
 * Falls back to the Composition-based list when the core cannot read the score.
 */
@Composable
fun PartTalkingScore(vm: PlayViewModel, r: TranscriptionResult, part: Int, concert: Boolean, playBar: (Int) -> Unit) {
    val lang = currentLang()
    val doc = remember(r.musicXml) { runCatching { vm.container.core.talkingScore(r.musicXml, r.compositionJson ?: vm.container.core.encodeComposition(r.composition)) }.getOrNull() } 
    if (doc == null) { TalkingScoreList(vm, r); return }
    DisposableEffect(doc) { onDispose { doc.close() } }
    val bars = remember(doc, part, lang, concert) {
        runCatching { doc.partLines(part.coerceIn(0, doc.partNames.size - 1), lang, if (concert) PitchMode.CONCERT else PitchMode.WRITTEN) }.getOrDefault(emptyList())
    }
    val rows = remember(bars) {
        bars.flatMapIndexed { i, b ->
            val number = Regex("""\d+""").find(b.heading)?.value?.toInt() ?: (i + 1)
            listOf(Row(number, i, b.heading, true)) + b.lines.map { Row(number, i, it, false) }
        }
    }
    val state = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val nextBar = stringResource(R.string.action_next_bar)
    val prevBar = stringResource(R.string.action_prev_bar)
    val readBar = stringResource(R.string.action_read_bar)
    val playBarLabel = stringResource(R.string.action_play_bar)

    fun jump(from: Int, delta: Int) {
        val target = rows.indexOfFirst { it.heading && it.barIndex == rows[from].barIndex + delta }
        if (target < 0) return
        scope.launch { state.animateScrollToItem(target) }
        vm.status.value = no.brasscribe.play.Status(rows[target].text)
    }

    LazyColumn(state = state, modifier = Modifier.fillMaxSize().semantics { testTag = "talking-score" }) {
        itemsIndexed(rows) { i, row ->
            Text(
                row.text,
                style = if (row.heading) MaterialTheme.typography.titleSmall else MaterialTheme.typography.bodyLarge,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { playBar(row.bar) }
                    .padding(horizontal = 16.dp, vertical = 4.dp)
                    .clearAndSetSemantics {
                        contentDescription = row.text
                        if (row.heading) heading()
                        customActions = listOf(
                            CustomAccessibilityAction(nextBar) { jump(i, 1); true },
                            CustomAccessibilityAction(prevBar) { jump(i, -1); true },
                            CustomAccessibilityAction(readBar) {
                                vm.status.value = no.brasscribe.play.Status(bars[row.barIndex].lines.joinToString(", ")); true
                            },
                            CustomAccessibilityAction(playBarLabel) { playBar(row.bar); true },
                        )
                    },
            )
        }
    }
}
