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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
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
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
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
import java.util.Locale

fun currentLang(): Lang = if (Locale.getDefault().language in setOf("nb", "no", "nn")) Lang.NB else Lang.EN

/** Name and instrument for a Composition voice: the melody reads as the B-flat solo cornet part. */
fun partViewFor(c: Composition, voiceId: String, checked: Set<Int>, core: no.brasscribe.play.model.CoreBridge = no.brasscribe.play.model.KotlinCoreBridge): PartView {
    val v = c.voice(voiceId) ?: c.voices.first()
    val names = mapOf(
        "solo" to ("Solo Cornet" to "Solokornett"), "bass" to ("Bass" to "Bass"), "strings" to ("Strings" to "Strykere"),
        "brass" to ("Brass" to "Messing"), "drums" to ("Drums" to "Trommer"),
    )
    val (en, nb) = names[v.id] ?: (v.id.replaceFirstChar { it.uppercase() } to v.id)
    val instrument = if (v.role == VoiceRole.MELODY) Instrument.CORNET else Instrument.CONCERT
    return PartView(c, v, instrument, en, nb, checked, core)
}

/** Screen-reader text of every event, each spoken in the context of the one before (spec §4). */
fun announcements(view: PartView, lang: Lang, bridge: no.brasscribe.play.model.CoreBridge): List<String> =
    view.events.mapIndexed { i, e ->
        val prev = view.events.getOrNull(i - 1)
        bridge.announce(e.stop, TsContext(part = if (prev == null) null else view.partName, bar = prev?.bar), TsSettings(), lang)
    }

/** Note length in the band room's words (en-GB minim, crotchet; nb halvnote, firedelsnote). */
@Composable
fun durationWord(type: String?, dots: Int): String {
    val base = stringResource(
        when (type) {
            "whole" -> R.string.dur_whole; "half" -> R.string.dur_half; "quarter" -> R.string.dur_quarter
            "eighth" -> R.string.dur_eighth; "16th" -> R.string.dur_16th; "32nd" -> R.string.dur_32nd
            else -> R.string.dur_note
        },
    )
    return if (dots > 0) stringResource(R.string.dur_dotted, base) else base
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReviewScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val result by vm.result.collectAsState()
    val checkedMap by vm.checked.collectAsState()
    val playingBar by vm.clipPlaying.collectAsState()
    val r = result ?: return
    val c = BrasscribeTheme.colors
    // Review checks a transcription; an opened score has nothing to check against.
    val composition = r.composition ?: return
    val voices = composition.voices.filter { it.notes.isNotEmpty() }
    var voiceId by rememberSaveable { mutableStateOf(voices.firstOrNull { it.role == VoiceRole.MELODY }?.id ?: voices.first().id) }
    val checked = checkedMap[voiceId].orEmpty()
    val lang = currentLang()
    val view = remember(r, voiceId, checked) { partViewFor(composition, voiceId, checked, vm.container.core) }
    val spoken = remember(view, lang) { announcements(view, lang, vm.container.core) }
    val notes = view.events.filter { it.note != null }
    val todo = notes.filter { it.uncertainty != Uncertainty.CONFIDENT && it.index !in checked }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val focus = remember(view) { HashMap<Int, FocusRequester>() }
    val bars = view.bars
    val partName = if (lang == Lang.NB) view.partNameNb else view.partName
    // The note being checked: the first unchecked uncertain one at or after the last position.
    var at by rememberSaveable(voiceId) { mutableIntStateOf(-1) }
    val current = todo.firstOrNull { it.index > at } ?: todo.firstOrNull()
    var confirmLater by remember { mutableStateOf(false) }

    fun advance(from: Int, announce: Boolean = true) {
        at = from
        val next = todo.firstOrNull { it.index > from && it.index != from } ?: todo.firstOrNull { it.index != from }
        if (!announce) return
        if (next == null) vm.say(R.string.review_no_uncertain) else vm.status.value = no.brasscribe.play.Status(spoken[next.index])
    }
    // Keep says "Kept. N left" (markChecked); the next note is the card, so it is not read over that.
    fun keep(e: PartEvent) {
        vm.markChecked(voiceId, e.index, todo.count { it.index != e.index })
        advance(e.index, announce = false)
    }
    fun nextUncertain(after: Int) {
        val next = todo.firstOrNull { it.index > after } ?: todo.firstOrNull()
        if (next == null) { vm.say(R.string.review_no_uncertain); return }
        val barIdx = bars.indexOfFirst { b -> b.events.any { it.index == next.index } }
        scope.launch {
            listState.animateScrollToItem(barIdx + HEADER_ITEMS)
            delay(150)
            focus[next.index]?.let { runCatching { it.requestFocus() } }
            vm.status.value = no.brasscribe.play.Status(spoken[next.index])
        }
    }
    fun finish() { vm.stopListening(); vm.navigate(Screen.OUTPUT) }

    PlayScaffold(
        title = null, onBack = vm::back, backLabel = composition.title.ifBlank { null } ?: stringResource(R.string.home), status = status, scroll = false,
        actions = { if (current != null) PlainButton(stringResource(R.string.review_finish_later, todo.size), { confirmLater = true }) },
        bottom = {
            if (current != null) {
                PrimaryButton(stringResource(R.string.review_keep_next), { keep(current) }, icon = R.drawable.ic_bc_mark_checked)
                SecondaryButton(stringResource(R.string.review_skip), { advance(current.index) }, icon = R.drawable.ic_bc_skip)
            } else PrimaryButton(stringResource(R.string.review_continue), ::finish)
        },
    ) {
        LazyColumn(state = listState, modifier = Modifier.fillMaxSize().semantics { testTag = "review-list" },
            verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                    ScreenTitle(if (todo.isEmpty()) stringResource(R.string.review_all_checked) else pluralStringResource(R.plurals.review_title, todo.size, todo.size))
                    Lead(stringResource(R.string.review_lead))
                    Legend()
                    if (voices.size > 1) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                        voices.forEach { v ->
                            val name = partViewFor(composition, v.id, emptySet(), vm.container.core).let { if (lang == Lang.NB) it.partNameNb else it.partName }
                            PracticeChip(name, v.id == voiceId, { voiceId = v.id }, role = Role.RadioButton)
                        }
                    }
                }
            }
            item {
                if (current != null) NoteCard(
                    current, partName, todo.indexOf(current) + 1, todo.size, spoken[current.index], lang, playingBar == current.bar,
                    listen = { vm.listenToBar(current.bar) }, stop = vm::stopListening,
                    keep = { keep(current) }, next = { advance(current.index) },
                    neighbours = bars.firstOrNull { it.number == current.bar }?.events.orEmpty(), checked = checked,
                )
            }
            item {
                val rest = todo.filter { it != current }
                if (rest.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    SectionLabel(stringResource(R.string.review_still_to_check))
                    RowGroup {
                        rest.take(4).forEachIndexed { i, e ->
                            if (i > 0) RowDivider()
                            ListRow(
                                stringResource(R.string.bar_heading, e.bar), { at = e.index - 1 },
                                subtitle = noteLine(e, lang),
                                chevron = false,
                                trailing = { UncertainMark(e.uncertainty == Uncertainty.VERY_UNCERTAIN) },
                            )
                        }
                        if (rest.size > 4) {
                            RowDivider()
                            ListRow(stringResource(R.string.review_more, rest.size - 4), { nextUncertain(current?.index ?: -1) }, chevron = false)
                        }
                    }
                }
            }
            item { SectionLabel(stringResource(R.string.review_all_notes, partName)) }
            itemsIndexed(bars, key = { _, b -> b.number }) { _, bar ->
                val rest = bar.events.singleOrNull()?.takeIf { it.note == null }
                Column(Modifier.fillMaxWidth().padding(vertical = BrasscribeSpace.s1)) {
                    Text(
                        if (rest != null && rest.stop.event.bars > 1) stringResource(R.string.bar_rest_heading, bar.number, bar.number + rest.stop.event.bars - 1)
                        else stringResource(R.string.bar_heading, bar.number),
                        style = MaterialTheme.typography.titleSmall, color = c.textMuted,
                        modifier = Modifier.semantics { heading() },
                    )
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
                        bar.events.forEach { e ->
                            val fr = remember(focus, e.index) { focus.getOrPut(e.index) { FocusRequester() } }
                            EventChip(
                                e, spoken[e.index], e.index in checked, fr,
                                listen = { vm.listenToBar(e.bar) },
                                check = { vm.markChecked(voiceId, e.index, todo.count { it.index != e.index }) },
                                next = { nextUncertain(e.index) },
                                label = e.stop.event.written?.let { no.brasscribe.play.model.Announcer.pitchLabel(it, lang) } ?: "–",
                            )
                        }
                    }
                }
            }
        }
    }

    if (confirmLater) {
        AlertDialog(
            onDismissRequest = { confirmLater = false },
            title = { Text(stringResource(R.string.review_finish_later_title)) },
            text = { Text(pluralStringResource(R.plurals.review_finish_later_text, todo.size, todo.size)) },
            confirmButton = {
                Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                    PrimaryButton(stringResource(R.string.review_finish_later_confirm), { confirmLater = false; finish() })
                    SecondaryButton(stringResource(R.string.review_keep_checking), { confirmLater = false })
                }
            },
        )
    }
}

/** The items above the bar list in the review LazyColumn (header, note card, still to check, label). */
private const val HEADER_ITEMS = 4

/** "Written G4, minim" for a note event. */
@Composable
private fun noteLine(e: PartEvent, lang: Lang): String {
    val ev = e.stop.event
    val pitch = ev.written?.let { no.brasscribe.play.model.Announcer.pitchLabel(it, lang) } ?: "–"
    return stringResource(R.string.review_note_line, pitch, durationWord(ev.type, ev.dots))
}

/**
 * The note being checked: bar and part, its place in the queue, the bar's notes with the marks, the
 * note in words with its level, and Listen. Keep and Skip sit in the bottom bar; TalkBack also gets
 * them as custom actions here.
 */
@Composable
private fun NoteCard(
    e: PartEvent, partName: String, position: Int, total: Int, spoken: String, lang: Lang, playing: Boolean,
    listen: () -> Unit, stop: () -> Unit, keep: () -> Unit, next: () -> Unit,
    neighbours: List<PartEvent>, checked: Set<Int>,
) {
    val c = BrasscribeTheme.colors
    val listenLabel = stringResource(R.string.action_listen_bar)
    val checkLabel = stringResource(R.string.action_mark_checked)
    val nextLabel = stringResource(R.string.review_next_uncertain)
    val level = stringResource(if (e.uncertainty == Uncertainty.VERY_UNCERTAIN) R.string.level_very_uncertain else R.string.level_uncertain)
    Surface(shape = MaterialTheme.shapes.large, color = c.surfaceRaised, border = androidx.compose.foundation.BorderStroke(1.dp, c.border)) {
        Column(Modifier.fillMaxWidth().padding(BrasscribeSpace.s4), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            Column(
                Modifier.fillMaxWidth().semantics(mergeDescendants = true) {
                    contentDescription = spoken
                    customActions = listOf(
                        CustomAccessibilityAction(listenLabel) { listen(); true },
                        CustomAccessibilityAction(checkLabel) { keep(); true },
                        CustomAccessibilityAction(nextLabel) { next(); true },
                    )
                },
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.review_card_title, e.bar, partName), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    Text(stringResource(R.string.review_position, position, total), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalAlignment = Alignment.Bottom) {
                    neighbours.filter { it.note != null }.take(8).forEach { n ->
                        val mine = n.index == e.index
                        NoteGlyph(n.uncertainty, n.index in checked,
                            Modifier.then(if (mine) Modifier.border(2.dp, c.text, MaterialTheme.shapes.small).padding(2.dp) else Modifier), size = 30.dp)
                    }
                }
                Text(
                    stringResource(R.string.review_note_and_level, noteLine(e, lang), level),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
            if (playing) OutlineButton(stringResource(R.string.stop_listening), stop, icon = R.drawable.ic_bc_stop)
            else SecondaryButton(stringResource(R.string.listen), listen, icon = R.drawable.ic_bc_listen_bar)
        }
    }
}

@Composable
private fun EventChip(
    e: PartEvent, spoken: String, checked: Boolean, focus: FocusRequester,
    listen: () -> Unit, check: () -> Unit, next: () -> Unit, label: String,
) {
    val t = BrasscribeTheme.colors
    val listenLabel = stringResource(R.string.action_listen_bar)
    val checkLabel = stringResource(R.string.action_mark_checked)
    val nextLabel = stringResource(R.string.review_next_uncertain)
    val uncertain = e.uncertainty != Uncertainty.CONFIDENT && !checked
    Surface(
        shape = MaterialTheme.shapes.small,
        color = t.surface, contentColor = t.text,
        modifier = Modifier
            .sizeIn(minWidth = 48.dp, minHeight = 48.dp)
            .focusRequester(focus)
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
        Column(Modifier.padding(BrasscribeSpace.s1).width(40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            if (e.note != null) NoteGlyph(e.uncertainty, checked, size = 24.dp)
            Text(label, style = MaterialTheme.typography.labelMedium)
        }
    }
}

/** The uncertainty legend: the same "?" glyphs as the score (system.md §5). */
@Composable
fun Legend(modifier: Modifier = Modifier) {
    val c = BrasscribeTheme.colors
    Row(
        modifier.semantics(mergeDescendants = true) {},
        horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4), verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
            UncertainMark(false, fontSize = androidx.compose.ui.unit.TextUnit(18f, androidx.compose.ui.unit.TextUnitType.Sp))
            Text(stringResource(R.string.legend_uncertain), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
            UncertainMark(true, fontSize = androidx.compose.ui.unit.TextUnit(18f, androidx.compose.ui.unit.TextUnitType.Sp))
            Text(stringResource(R.string.legend_very_uncertain), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
    }
}
