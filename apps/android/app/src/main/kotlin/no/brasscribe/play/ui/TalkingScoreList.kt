package no.brasscribe.play.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.semantics.traversalIndex
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.TranscriptionResult
import no.brasscribe.play.R
import no.brasscribe.play.model.TsContext
import no.brasscribe.play.model.TsSettings
import no.brasscribe.play.model.Verbosity
import no.brasscribe.play.model.VoiceRole

/**
 * The talking score: one list item per event of the melody part, in time order, each carrying its
 * announcement and custom actions for bar navigation, "Read bar" and "Play this bar" (spec §5).
 */
@Composable
fun TalkingScoreList(vm: PlayViewModel, r: TranscriptionResult) {
    val checkedMap by vm.checked.collectAsState()
    // Only reachable without the core; an opened score has no Composition to fall back to.
    val composition = r.composition ?: run {
        Text(stringResource(R.string.talking_score_unavailable))
        return
    }
    val voice = composition.voices.firstOrNull { it.role == VoiceRole.MELODY } ?: composition.voices.first()
    val lang = currentLang()
    val view = remember(r, checkedMap) { partViewFor(composition, voice.id, checkedMap[voice.id].orEmpty(), vm.container.core) }
    val spoken = remember(view, lang) { announcements(view, lang, vm.container.core) }
    val state = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val nextBar = stringResource(R.string.action_next_bar)
    val prevBar = stringResource(R.string.action_prev_bar)
    val readBar = stringResource(R.string.action_read_bar)
    val playBar = stringResource(R.string.action_play_bar)
    val events = view.events

    fun jumpToBar(from: Int, delta: Int) {
        val bar = events[from].bar
        val target = if (delta > 0) events.indexOfFirst { it.bar > bar } else events.indexOfLast { it.bar < bar }.let { i ->
            if (i < 0) -1 else events.indexOfFirst { it.bar == events[i].bar }
        }
        if (target < 0) return
        scope.launch { state.animateScrollToItem(target) }
        vm.status.value = no.brasscribe.play.Status(spoken[target])
    }

    fun readBarText(i: Int): String {
        val bar = events[i].bar
        return events.filter { it.bar == bar }.joinToString(", ") {
            vm.container.core.announce(it.stop, TsContext(view.partName, bar), TsSettings(verbosity = Verbosity.BRIEF), lang)
        }
    }

    LazyColumn(state = state, modifier = Modifier.fillMaxSize().semantics { testTag = "talking-score" }) {
        itemsIndexed(events, key = { _, e -> e.index }) { i, e ->
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { vm.listenToBar(e.bar) }.padding(horizontal = 16.dp, vertical = 4.dp)
                    .clearAndSetSemantics {
                        contentDescription = spoken[i]
                        traversalIndex = i.toFloat()
                        customActions = listOf(
                            CustomAccessibilityAction(nextBar) { jumpToBar(i, 1); true },
                            CustomAccessibilityAction(prevBar) { jumpToBar(i, -1); true },
                            CustomAccessibilityAction(readBar) { vm.status.value = no.brasscribe.play.Status(readBarText(i)); true },
                            CustomAccessibilityAction(playBar) { vm.listenToBar(e.bar); true },
                        )
                    },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(spoken[i])
            }
        }
    }
}
