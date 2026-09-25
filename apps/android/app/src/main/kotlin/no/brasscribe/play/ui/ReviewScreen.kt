package no.brasscribe.play.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.Instrument
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.PartEvent
import no.brasscribe.play.model.PartView
import no.brasscribe.play.model.TsContext
import no.brasscribe.play.model.TsSettings
import no.brasscribe.play.model.Uncertainty
import no.brasscribe.play.model.VoiceRole
import no.brasscribe.play.ui.theme.LocalPlayTokens
import java.util.Locale

fun currentLang(): Lang = if (Locale.getDefault().language in setOf("nb", "no", "nn")) Lang.NB else Lang.EN

/** Name and instrument for a Composition voice: the melody reads as the B-flat solo cornet part. */
fun partViewFor(c: Composition, voiceId: String, checked: Set<Int>): PartView {
    val v = c.voice(voiceId) ?: c.voices.first()
    val names = mapOf(
        "solo" to ("Solo Cornet" to "Solokornett"), "bass" to ("Bass" to "Bass"), "strings" to ("Strings" to "Strykere"),
        "brass" to ("Brass" to "Messing"), "drums" to ("Drums" to "Trommer"),
    )
    val (en, nb) = names[v.id] ?: (v.id.replaceFirstChar { it.uppercase() } to v.id)
    val instrument = if (v.role == VoiceRole.MELODY) Instrument.CORNET else Instrument.CONCERT
    return PartView(c, v, instrument, en, nb, checked)
}

/** Screen-reader text of every event, each spoken in the context of the one before (spec §4). */
fun announcements(view: PartView, lang: Lang, bridge: no.brasscribe.play.model.CoreBridge): List<String> =
    view.events.mapIndexed { i, e ->
        val prev = view.events.getOrNull(i - 1)
        bridge.announce(e.stop, TsContext(part = if (prev == null) null else view.partName, bar = prev?.bar), TsSettings(), lang)
    }

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReviewScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val result by vm.result.collectAsState()
    val checkedMap by vm.checked.collectAsState()
    val playingBar by vm.clipPlaying.collectAsState()
    val r = result ?: return
    val voices = r.composition.voices.filter { it.notes.isNotEmpty() }
    var voiceId by rememberSaveable { mutableStateOf(voices.firstOrNull { it.role == VoiceRole.MELODY }?.id ?: voices.first().id) }
    val checked = checkedMap[voiceId].orEmpty()
    val lang = currentLang()
    val view = remember(r, voiceId, checked) { partViewFor(r.composition, voiceId, checked) }
    val spoken = remember(view, lang) { announcements(view, lang, vm.container.core) }
    val notes = view.events.filter { it.note != null }
    val uncertain = notes.count { it.uncertainty == Uncertainty.UNCERTAIN && it.index !in checked }
    val very = notes.count { it.uncertainty == Uncertainty.VERY_UNCERTAIN && it.index !in checked }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val focus = remember(view) { HashMap<Int, FocusRequester>() }
    val bars = view.bars

    fun nextUncertain(after: Int) {
        val next = view.events.firstOrNull { it.index > after && it.note != null && it.uncertainty != Uncertainty.CONFIDENT && it.index !in checked }
            ?: view.events.firstOrNull { it.note != null && it.uncertainty != Uncertainty.CONFIDENT && it.index !in checked }
        if (next == null) { vm.say(R.string.review_no_uncertain); return }
        val barIdx = bars.indexOfFirst { b -> b.events.any { it.index == next.index } }
        scope.launch {
            listState.animateScrollToItem(barIdx + 1)
            delay(150)
            focus[next.index]?.let { runCatching { it.requestFocus() } }
            vm.status.value = no.brasscribe.play.Status(spoken[next.index])
        }
    }

    PlayScaffold(title = stringResource(R.string.review_title), onBack = vm::back, status = status, scroll = false) {
        LazyColumn(state = listState, modifier = Modifier.fillMaxSize().semantics { testTag = "review-list" }, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Heading(stringResource(R.string.review_title))
                    Text(stringResource(R.string.review_summary, notes.size, uncertain, very))
                    Legend()
                    SubHeading(stringResource(R.string.review_part))
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        voices.forEach { v ->
                            val name = partViewFor(r.composition, v.id, emptySet()).let { if (lang == Lang.NB) it.partNameNb else it.partName }
                            FilterChip(selected = v.id == voiceId, onClick = { voiceId = v.id }, label = { Text(name) })
                        }
                    }
                    BigButton(stringResource(R.string.review_next_uncertain), { nextUncertain(-1) }, enabled = uncertain + very > 0)
                    if (playingBar != null) BigButton(stringResource(R.string.stop_listening), vm::stopListening, primary = false)
                    BigButton(stringResource(R.string.review_continue), { vm.stopListening(); vm.navigate(Screen.OUTPUT) }, primary = false)
                }
            }
            itemsIndexed(bars, key = { _, b -> b.number }) { _, bar ->
                val rest = bar.events.singleOrNull()?.takeIf { it.note == null }
                Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text(
                        if (rest != null && rest.stop.event.bars > 1) stringResource(R.string.bar_rest_heading, bar.number, bar.number + rest.stop.event.bars - 1)
                        else stringResource(R.string.bar_heading, bar.number),
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.semantics { heading() },
                    )
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        bar.events.forEach { e ->
                            val fr = focus.getOrPut(e.index) { FocusRequester() }
                            EventChip(
                                e, spoken[e.index], e.index in checked, fr,
                                listen = { vm.listenToBar(e.bar) },
                                check = {
                                    val left = notes.count { it.uncertainty != Uncertainty.CONFIDENT && it.index !in checked && it.index != e.index }
                                    vm.markChecked(voiceId, e.index, left)
                                },
                                next = { nextUncertain(e.index) },
                                label = e.stop.event.written?.let { "${it.step}${alterSign(it.alter)}${it.octave}" } ?: "–",
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun alterSign(a: Int) = when (a) { 1 -> "♯"; -1 -> "♭"; 2 -> "𝄪"; -2 -> "𝄫"; else -> "" }

@Composable
private fun EventChip(
    e: PartEvent, spoken: String, checked: Boolean, focus: FocusRequester,
    listen: () -> Unit, check: () -> Unit, next: () -> Unit, label: String,
) {
    val t = LocalPlayTokens.current
    val listenLabel = stringResource(R.string.action_listen_bar)
    val checkLabel = stringResource(R.string.action_mark_checked)
    val nextLabel = stringResource(R.string.review_next_uncertain)
    val uncertain = e.uncertainty != Uncertainty.CONFIDENT && !checked
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = t.surface,
        modifier = Modifier
            .sizeIn(minWidth = 48.dp, minHeight = 48.dp)
            .focusRequester(focus)
            .then(if (uncertain) Modifier.border(2.dp, if (e.uncertainty == Uncertainty.VERY_UNCERTAIN) t.veryUncertain else t.uncertain, RoundedCornerShape(8.dp)) else Modifier)
            .clickable(onClickLabel = listenLabel, onClick = listen)
            .clearAndSetSemantics {
                contentDescription = spoken
                if (checked) stateDescription = checkLabel
                onClick(listenLabel) { listen(); true }
                customActions = buildList {
                    add(CustomAccessibilityAction(listenLabel) { listen(); true })
                    if (uncertain) add(CustomAccessibilityAction(checkLabel) { check(); true })
                    add(CustomAccessibilityAction(nextLabel) { next(); true })
                }
            },
    ) {
        Column(Modifier.padding(4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            if (e.note != null) NoteGlyph(e.uncertainty, checked)
            Text(label, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun Legend() {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        SubHeading(stringResource(R.string.legend_title))
        listOf(
            Triple(Uncertainty.CONFIDENT, false, R.string.legend_confident),
            Triple(Uncertainty.UNCERTAIN, false, R.string.legend_uncertain),
            Triple(Uncertainty.VERY_UNCERTAIN, false, R.string.legend_very_uncertain),
            Triple(Uncertainty.UNCERTAIN, true, R.string.legend_checked),
        ).forEach { (level, checked, text) ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.semantics(mergeDescendants = true) {}) {
                NoteGlyph(level, checked, size = 28.dp)
                Text(stringResource(text))
            }
        }
    }
}
