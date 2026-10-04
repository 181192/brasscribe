package no.brasscribe.play.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
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
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.platform.testTag as tagged
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.Lineup
import no.brasscribe.play.fullBandMade
import no.brasscribe.play.madeFor
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.NoteEvidence
import no.brasscribe.play.noteAt
import no.brasscribe.play.arrangementString
import kotlin.math.roundToInt
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.Instrument
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.reading
import no.brasscribe.play.model.PartEvent
import no.brasscribe.play.model.PartView
import no.brasscribe.play.model.TsContext
import no.brasscribe.play.model.TsSettings
import no.brasscribe.play.model.Uncertainty
import no.brasscribe.play.model.VoiceRole
import java.util.Locale

fun currentLang(): Lang = if (Locale.getDefault().language in setOf("nb", "no", "nn")) Lang.NB else Lang.EN

/** The recording's layers by name (not band parts): what Review calls the voices other than the tune. */
private val LAYER_NAMES = mapOf(
    "bass" to ("Bass" to "Bass"), "strings" to ("Strings" to "Strykere"),
    "brass" to ("Brass" to "Messing"), "drums" to ("Drums" to "Trommer"),
)

/**
 * The part that carries the recorded tune and its instrument: the seat's part when the arrangement put
 * the tune there (a solo take with a seat always does), else Solo Cornet in B♭. A bass-clef reader sees
 * it at concert pitch.
 */
fun melodyPart(c: Composition, core: no.brasscribe.play.model.CoreBridge): Pair<String, Instrument> {
    val seatId = c.arrangementString("seat")
    val seat = seatId?.let { id -> core.seats().firstOrNull { it.id == id } }
    if (seat == null || c.arrangementString("lead") != "seat") return no.brasscribe.play.PlayViewModel.SOLO_PART_NAME to Instrument.CORNET
    val soloTake = c.voices.count { it.notes.isNotEmpty() } <= 1
    val part = if (soloTake) seat.name else core.seatPart((Lineup.recorded(c) ?: Lineup.FULL.madeFor(c.fullBandMade)).core, seat.id)?.part ?: seat.name
    val chromatic = if (seat.reading(c.arrangementString("reads")) == "bass") 0 else no.brasscribe.play.YourParts.chromatic(part, core.seats()) ?: seat.chromatic
    val instrument = if (chromatic == 0) Instrument.CONCERT else Instrument.entries.firstOrNull { it.chromatic == chromatic } ?: Instrument.CORNET
    return part to instrument
}

/** Name and instrument for a Composition voice: the melody reads as the part that carries the tune. */
fun partViewFor(c: Composition, voiceId: String, checked: Set<Int>, core: no.brasscribe.play.model.CoreBridge = no.brasscribe.play.model.KotlinCoreBridge): PartView {
    val v = c.voice(voiceId) ?: c.voices.first()
    if (v.role == VoiceRole.MELODY) {
        val (part, instrument) = melodyPart(c, core)
        return PartView(c, v, instrument, part, core.partNameNb(part), checked, core)
    }
    val (en, nb) = LAYER_NAMES[v.id] ?: (v.id.replaceFirstChar { it.uppercase() } to v.id)
    return PartView(c, v, Instrument.CONCERT, en, nb, checked, core)
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
    val changes by vm.reviewChanges.collectAsState()
    val r = result ?: return
    val c = BrasscribeTheme.colors
    // Review checks a transcription; an opened score has nothing to check against.
    val composition = r.composition ?: return
    val voices = composition.voices.filter { it.notes.isNotEmpty() }
    // No note to check: such a result opens on the problem screen, never here.
    val firstVoice = voices.firstOrNull() ?: return
    // "Yours": the layer your part follows (the tune, the bass line, ...), or none when your part is arranged.
    val mine = yoursInReview(vm, r, composition)
    val melodyVoice = voices.firstOrNull { it.role == VoiceRole.MELODY }?.id
    var voiceId by rememberSaveable { mutableStateOf(mine.voice ?: melodyVoice ?: firstVoice.id) }
    val checked = checkedMap[voiceId].orEmpty()
    val lang = currentLang()
    val view = remember(r, voiceId, checked) { partViewFor(composition, voiceId, checked, vm.container.core) }
    val spoken = remember(view, lang) { announcements(view, lang, vm.container.core) }
    val notes = view.events.filter { it.note != null }
    // What to check: the engine's review groups when it made them (one item per group, Keep keeps the
    // whole group), else every marked note on its own.
    val grouped = composition.review?.filter { it.voice == voiceId }?.takeIf { it.isNotEmpty() }
    val allItems = remember(view, grouped) { reviewGroups(composition, voiceId, view) }
    // Triage: the very unsure first, then in bar order; skipped items go to the back of the queue.
    var skipped by rememberSaveable(voiceId) { mutableStateOf(listOf<Int>()) }
    val items = allItems.filter { g -> g.members.any { it.index !in checked } }
        .sortedWith(compareBy({ skipped.indexOf(it.head.index) }, { if (it.very) 0 else 1 }, { it.head.index }))
    val groupOf = items.associateBy { it.head.index }
    val todo = items.map { it.head }
    val veryCount = items.count { it.very }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val focus = remember(view) { HashMap<Int, FocusRequester>() }
    val bars = view.bars
    val partName = if (lang == Lang.NB) view.partNameNb else view.partName
    // The note being checked: the head of the queue, or the one picked from "Still to check".
    var picked by rememberSaveable(voiceId) { mutableStateOf<Int?>(null) }
    val current = todo.firstOrNull { it.index == picked } ?: todo.firstOrNull()
    var confirmLater by remember { mutableStateOf(false) }
    // Keep, Skip or picking another note moves to another bar: what was playing stops.
    LaunchedEffect(current?.index) { vm.stopListening(announce = false) }
    var changing by remember { mutableStateOf(false) }
    // After Save the card keeps TalkBack's and the keyboard's focus (not the next note).
    val cardFocus = remember { FocusRequester() }
    var focusCard by remember { mutableStateOf(false) }
    LaunchedEffect(focusCard) {
        if (!focusCard) return@LaunchedEffect
        delay(300)
        runCatching { cardFocus.requestFocus() }
        focusCard = false
    }

    fun advance(from: Int, announce: Boolean = true) {
        picked = null
        if (announce) skipped = skipped - from + from
        val next = todo.firstOrNull { it.index != from }
        if (!announce) return
        if (next == null) vm.say(R.string.review_no_uncertain) else vm.status.value = no.brasscribe.play.Status(spoken[next.index])
    }
    // Keep says "Kept. N left" (markChecked); the next note is the card, so it is not read over that.
    fun keep(e: PartEvent) {
        val members = groupOf[e.index]?.members?.map { it.index } ?: listOf(e.index)
        vm.markCheckedAll(voiceId, members, todo.count { it.index != e.index })
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
        title = null, onBack = vm::back, backLabel = composition.title.ifBlank { null }?.let(PartNames::shortTitle) ?: stringResource(R.string.home), status = status, scroll = false,
        actions = { if (current != null) PlainButton(stringResource(R.string.review_finish_later, todo.size), { confirmLater = true }) },
        bottom = {
            if (current != null) {
                PrimaryButton(stringResource(R.string.review_keep_next), { keep(current) }, icon = R.drawable.ic_bc_mark_checked)
                // While a third of the notes carry a "?" (review 3, P1-A), a whole bar can be kept at once.
                val restOfBar = items.filter { it.head.bar == current.bar }
                val skipButton = @Composable { m: Modifier -> SecondaryButton(stringResource(R.string.review_skip), { advance(current.index) }, m, icon = R.drawable.ic_bc_skip) }
                if (restOfBar.size > 1) Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                    skipButton(Modifier.weight(1f))
                    OutlineButton(pluralStringResource(R.plurals.review_keep_bar, restOfBar.size, restOfBar.size), {
                        vm.markCheckedAll(voiceId, restOfBar.flatMap { g -> g.members.map { it.index } }, todo.size - restOfBar.size)
                        picked = null
                    }, Modifier.weight(1.4f))
                } else skipButton(Modifier)
            } else PrimaryButton(stringResource(R.string.review_continue), ::finish)
        },
    ) {
        LazyColumn(state = listState, modifier = Modifier.fillMaxSize().semantics { testTag = "review-list" },
            verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                    ScreenTitle(when {
                        todo.isEmpty() -> stringResource(R.string.review_all_checked)
                        grouped != null -> pluralStringResource(R.plurals.review_title_places, todo.size, todo.size)
                        else -> pluralStringResource(R.plurals.review_title, todo.size, todo.size)
                    })
                    val own = mine.voice ?: melodyVoice.takeIf { !mine.arranged }
                    if (mine.arranged && mine.part != null) ArrangedNotice(mine.part, empty = mine.source == no.brasscribe.play.model.PartSource.EMPTY,
                        checkOthers = { voices.firstOrNull { it.id != voiceId }?.let { voiceId = it.id } ?: vm.navigate(Screen.OUTPUT) },
                        showMine = { vm.showScore() })
                    if (voiceId == own && mine.source != null) {
                        SourceLabel(mine.source)
                        mine.writtenFor?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = c.textMuted) }
                    }
                    if (todo.isNotEmpty() && voiceId == own) {
                        Text(stringResource(R.string.review_your_part_first), style = MaterialTheme.typography.titleMedium)
                        Lead(pluralStringResource(if (grouped != null) R.plurals.review_your_part_places else R.plurals.review_your_part_count,
                            todo.size, todo.size, partName) + " " + when {
                            // Many marks: most are right, so say where to start (review 3, P1-A).
                            // Mostly very unsure: don't call them "probably right".
                            veryCount * 2 > todo.size -> pluralStringResource(R.plurals.review_start_very, veryCount, veryCount)
                            todo.size > MANY_MARKS && veryCount > 0 -> pluralStringResource(R.plurals.review_most_right_start_very, veryCount, veryCount)
                            todo.size > MANY_MARKS -> stringResource(R.string.review_most_right)
                            veryCount > 0 -> pluralStringResource(R.plurals.review_very_first, veryCount, veryCount)
                            else -> ""
                        })
                    } else Lead(stringResource(R.string.review_lead))
                    Legend()
                    if (voices.size > 1) PartChips(voices, voiceId, composition, checkedMap, vm, lang, mine) { voiceId = it }
                }
            }
            item {
                if (current != null) {
                    val note = current.note
                    val evidence = note?.let { r.evidence?.noteAt(voiceId, it.start, it.pitch) }
                    val fifths = view.instrument.writtenFifths(composition.keys.firstOrNull()?.fifths ?: 0)
                    val written = current.stop.event.written
                    val label: (Int) -> String = { concert ->
                        // The note itself keeps its written spelling; other pitches are spelled by the key.
                        if (note != null && concert == note.pitch && written != null) no.brasscribe.play.model.Announcer.pitchLabel(written, lang)
                        else no.brasscribe.play.model.Announcer.pitchLabel(
                            no.brasscribe.play.model.SpelledPitch.spell(view.instrument.writtenMidi(concert), fifths), lang)
                    }
                    val group = groupOf[current.index]
                    val span = group?.bars ?: (current.bar..current.bar)
                    val cardTitle = (if (span.first == span.last) stringResource(R.string.review_card_title, current.bar, partName)
                        else stringResource(R.string.review_card_title_bars, span.first, span.last, partName)) +
                        (group?.members?.size?.takeIf { it > 1 }?.let { " · " + pluralStringResource(R.plurals.review_group_notes, it, it) } ?: "")
                    val changeKey = note?.let { vm.changeKey(voiceId, it.start) }
                    val was = changeKey?.let { changes[it] }
                    NoteCard(
                        current, partName, todo.indexOf(current) + 1, todo.size, spoken[current.index], lang, playingBar == current.bar,
                        title = cardTitle, very = group?.very,
                        changed = if (note != null && was != null) stringResource(R.string.review_changed_from, label(note.pitch), label(was)) else null,
                        undo = {
                            if (note != null && was != null) vm.undoReviewChange(voiceId, note.start, note.pitch) { done ->
                                if (!done) return@undoReviewChange
                                picked = current.index
                                vm.say(R.string.review_change_undone, label(was))
                                focusCard = true
                            }
                        },
                        focus = cardFocus,
                        listen = { vm.listenToBar(current.bar) }, stop = vm::stopListening,
                        keep = { keep(current) }, next = { advance(current.index) },
                        changeNote = { changing = true },
                        neighbours = bars.firstOrNull { it.number == current.bar }?.events.orEmpty(), checked = checked,
                        snippet = {
                            // The bar on a staff: the arranged part when this is the solo, else the layer on its own.
                            val xml = remember(r.musicXml, voiceId) {
                                val names = no.brasscribe.play.model.MusicXmlParts.names(r.musicXml)
                                // The part the tune is written on: the lineup's lead, or the seat's part when the tune went there.
                                val lead = no.brasscribe.play.YourParts.leadPart(composition, names, vm.container.core::seatPart)
                                val solo = lead?.let { l -> names.indexOfFirst { it.replace('\u00A0', ' ').trim().equals(l, true) } } ?: -1
                                if (voiceId == composition.voices.firstOrNull { it.role == VoiceRole.MELODY }?.id && solo >= 0)
                                    no.brasscribe.play.model.MusicXmlParts.single(r.musicXml, solo)
                                else vm.container.core.toMusicXml(composition, listOf(no.brasscribe.play.model.PartSpec(voiceId, partName, view.instrument)))
                            }
                            val map = remember(composition) { no.brasscribe.play.model.TickMap(composition) }
                            val offset = note?.let { (it.start - map.barStart(current.bar)).toDouble() / composition.ticksPerBeat } ?: 0.0
                            BarSnippetView(xml, current.bar, offset, span.last - span.first + 1)
                        },
                        evidence = evidence, pitchLabel = label,
                    )
                    if (changing && note != null) ChangeNoteSheet(
                        written = note.pitch, evidence = evidence, pitchLabel = label,
                        dismiss = { vm.stopListening(announce = false); changing = false },
                        previewing = playingBar == current.bar,
                        preview = { shift -> vm.previewNote(current.bar, voiceId, note.start, note.pitch, shift) },
                        stopPreview = vm::stopListening,
                        // Save writes the note and stays on it, still open: listen, change again or undo, then Keep.
                        save = { shift ->
                            changing = false
                            val before = was ?: note.pitch
                            val now = note.pitch + shift
                            val at = current.index
                            vm.changeReviewNote(voiceId, note.start, note.pitch, shift) { done ->
                                if (!done) return@changeReviewNote
                                picked = at
                                if (now == before) vm.say(R.string.review_change_undone, label(before))
                                else vm.say(R.string.review_changed_from, label(now), label(before))
                                focusCard = true
                            }
                        },
                    )
                }
            }
            item {
                val rest = todo.filter { it != current }
                if (rest.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    SectionLabel(stringResource(R.string.review_still_to_check))
                    RowGroup {
                        rest.take(4).forEachIndexed { i, e ->
                            if (i > 0) RowDivider()
                            ListRow(
                                stringResource(R.string.bar_heading, e.bar), { picked = e.index },
                                subtitle = noteLine(e, lang),
                                chevron = false,
                                trailing = { UncertainMark(groupOf[e.index]?.very ?: (e.uncertainty == Uncertainty.VERY_UNCERTAIN)) },
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
                                listen = { vm.listenToBar(e.bar) }, playing = playingBar == e.bar,
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

/**
 * The part to check: the player's part first (the melody), then the accompaniment layers folded
 * under one chip, each with how many notes are left. The chips wrap; nothing scrolls sideways.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PartChips(
    voices: List<no.brasscribe.play.model.Voice>, voiceId: String, composition: Composition, checkedMap: Map<String, Set<Int>>,
    vm: PlayViewModel, lang: Lang, mine: ReviewYours, choose: (String) -> Unit,
) {
    val left = remember(composition, checkedMap) {
        voices.associate { v ->
            val done = checkedMap[v.id].orEmpty()
            v.id to reviewGroups(composition, v.id, partViewFor(composition, v.id, done, vm.container.core)).count { g -> g.members.any { it.index !in done } }
        }
    }
    // Your own voice first; with your part arranged there is none, and the notice above says why.
    val own = when {
        mine.voice != null -> voices.filter { it.id == mine.voice }
        mine.arranged -> emptyList()
        else -> voices.filter { it.role == VoiceRole.MELODY }
    }
    val accompaniment = voices - own.toSet()
    var open by rememberSaveable { mutableStateOf(voiceId in accompaniment.map { it.id }) }
    val name = { v: no.brasscribe.play.model.Voice -> partViewFor(composition, v.id, emptySet(), vm.container.core).let { if (lang == Lang.NB) it.partNameNb else it.partName } }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        val yoursLabel = mine.part?.let { stringResource(R.string.stand_part_yours, PartNames.display(it, lang)) }
        own.forEach { v -> PracticeChip("${yoursLabel ?: name(v)} (${left[v.id] ?: 0})", v.id == voiceId, { choose(v.id) }, role = Role.RadioButton) }
        val n = accompaniment.sumOf { left[it.id] ?: 0 }
        if (accompaniment.isNotEmpty() && (n > 0 || voiceId in accompaniment.map { it.id })) {
            PracticeChip(stringResource(R.string.review_accompaniment, n), open, { open = !open }, role = Role.Button,
                trailingIcon = R.drawable.ic_bc_choose)
            if (open) accompaniment.forEach { v -> PracticeChip("${name(v)} (${left[v.id] ?: 0})", v.id == voiceId, { choose(v.id) }, role = Role.RadioButton) }
        }
    }
}

/** One thing to check: the group's first marked note ([head]), every note in it, and its bars. */
data class ReviewGroup(val head: PartEvent, val members: List<PartEvent>, val very: Boolean, val bars: IntRange)

/**
 * The review items of one voice: the engine's groups (`Composition.review`) when it made them, else
 * every marked note on its own.
 */
fun reviewGroups(composition: Composition, voiceId: String, view: PartView): List<ReviewGroup> {
    val notes = view.events.filter { it.note != null }
    // With the engine's groups, only the parts it grouped have anything to check (the coloured notes).
    if (composition.review != null && composition.review!!.none { it.voice == voiceId }) return emptyList()
    val grouped = composition.review?.filter { it.voice == voiceId }?.takeIf { it.isNotEmpty() }
    return grouped?.mapNotNull { g ->
        val members = notes.filter { e -> e.note!!.start.let { it >= g.start && it < g.end } }
        val head = members.firstOrNull { it.uncertainty != Uncertainty.CONFIDENT } ?: members.firstOrNull() ?: return@mapNotNull null
        ReviewGroup(head, members, g.very, head.bar..(members.maxOf { it.bar }))
    } ?: notes.filter { it.uncertainty != Uncertainty.CONFIDENT }
        .map { ReviewGroup(it, listOf(it), it.uncertainty == Uncertainty.VERY_UNCERTAIN, it.bar..it.bar) }
}

/** Review items not yet kept, over every voice: the "N to check" of Home and the score. */
fun itemsToCheck(composition: Composition, checked: Map<String, Set<Int>>, core: no.brasscribe.play.model.CoreBridge): Int =
    composition.voices.filter { it.notes.isNotEmpty() }.sumOf { v ->
        val done = checked[v.id].orEmpty()
        reviewGroups(composition, v.id, partViewFor(composition, v.id, done, core)).count { g -> g.members.any { it.index !in done } }
    }

/** Above this many marks the lead says most notes are probably right. */
private const val MANY_MARKS = 50

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
 * note in words with its level and what else it could be, how sure Brasscribe is and what each
 * transcriber heard, then Listen and Change note…. Keep and Skip sit in the bottom bar; TalkBack also
 * gets them as custom actions here.
 */
@Composable
private fun NoteCard(
    e: PartEvent, partName: String, position: Int, total: Int, spoken: String, lang: Lang, playing: Boolean,
    title: String, very: Boolean?,
    changed: String?, undo: () -> Unit, focus: FocusRequester,
    listen: () -> Unit, stop: () -> Unit, keep: () -> Unit, next: () -> Unit,
    changeNote: () -> Unit,
    neighbours: List<PartEvent>, checked: Set<Int>, snippet: @Composable () -> Unit = {},
    evidence: NoteEvidence?, pitchLabel: (Int) -> String,
) {
    val c = BrasscribeTheme.colors
    // While the bar plays, the same button (and TalkBack action) is Stop.
    val listenLabel = stringResource(if (playing) R.string.listen_stop else R.string.action_listen_bar)
    val checkLabel = stringResource(R.string.action_mark_checked)
    val nextLabel = stringResource(R.string.review_next_uncertain)
    val undoLabel = stringResource(R.string.review_undo_change)
    val level = stringResource(if (very ?: (e.uncertainty == Uncertainty.VERY_UNCERTAIN)) R.string.level_very_uncertain else R.string.level_uncertain)
    val alternative = evidence?.alternativeShift?.let { pitchLabel(evidence.pitch + it) }
    val levelSentence = if (alternative != null) stringResource(R.string.review_could_also_be, level, withArticle(alternative, lang))
        else stringResource(R.string.review_listen_side_by_side, level)
    Surface(shape = MaterialTheme.shapes.large, color = c.surfaceRaised, border = androidx.compose.foundation.BorderStroke(1.dp, c.border)) {
        Column(Modifier.fillMaxWidth().padding(BrasscribeSpace.s4), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            Column(
                Modifier.fillMaxWidth().focusRequester(focus).focusable().semantics(mergeDescendants = true) {
                    contentDescription = listOfNotNull(spoken, changed, levelSentence).joinToString(". ")
                    customActions = listOfNotNull(
                        CustomAccessibilityAction(listenLabel) { if (playing) stop() else listen(); true },
                        CustomAccessibilityAction(checkLabel) { keep(); true },
                        CustomAccessibilityAction(nextLabel) { next(); true },
                        changed?.let { CustomAccessibilityAction(undoLabel) { undo(); true } },
                    )
                },
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    Text(stringResource(R.string.review_position, position, total), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
                }
                snippet()
                Text(noteLine(e, lang), style = MaterialTheme.typography.titleMedium)
                // After Save: what the note is now and what Brasscribe wrote. It keeps its "?" until Keep.
                if (changed != null) Text(changed, style = MaterialTheme.typography.titleMedium, modifier = Modifier.tagged("note-changed"))
                Text(levelSentence, style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
            }
            if (evidence != null) EvidencePanel(evidence, pitchLabel)
            ListenButton(playing, listen, stop)
            OutlineButton(stringResource(R.string.change_note), changeNote, icon = R.drawable.ic_bc_transpose)
            if (changed != null) PlainButton(undoLabel, undo, Modifier.fillMaxWidth().tagged("undo-change"))
        }
    }
}

/** "an A", "a B" in English; Norwegian names the note bare. */
private fun withArticle(name: String, lang: Lang): String =
    if (lang == Lang.NB) name else (if (name.firstOrNull()?.uppercaseChar() in setOf('A', 'E', 'F')) "an " else "a ") + name

/** How sure Brasscribe is, and what each transcriber heard at this note. */
@Composable
private fun EvidencePanel(evidence: NoteEvidence, pitchLabel: (Int) -> String) {
    val c = BrasscribeTheme.colors
    val howSure = stringResource(R.string.evidence_how_sure)
    val percent = stringResource(R.string.evidence_percent, (evidence.confidence * 100).roundToInt())
    Column(
        Modifier.fillMaxWidth().background(c.surface, MaterialTheme.shapes.medium).border(1.dp, c.border, MaterialTheme.shapes.medium)
            .padding(BrasscribeSpace.s4),
        verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
    ) {
        Row(Modifier.semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
            Text(howSure, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            Text(percent, style = no.brasscribe.design.BrasscribeNumericStyle.copy(fontSize = MaterialTheme.typography.titleSmall.fontSize))
        }
        LinearProgressIndicator(
            progress = { evidence.confidence.toFloat().coerceIn(0f, 1f) },
            color = c.text, trackColor = c.border,
            modifier = Modifier.fillMaxWidth().semantics {
                contentDescription = howSure
                stateDescription = percent
                progressBarRangeInfo = ProgressBarRangeInfo(evidence.confidence.toFloat().coerceIn(0f, 1f), 0f..1f)
            },
        )
        if (evidence.models.isNotEmpty()) {
            HorizontalDivider(color = c.border)
            Text(stringResource(R.string.evidence_heard), style = MaterialTheme.typography.titleSmall)
            evidence.models.forEach { m ->
                val heard = when {
                    m.pitch == null -> stringResource(R.string.evidence_no_note)
                    m.agrees -> stringResource(R.string.evidence_same, pitchLabel(m.pitch!!))
                    else -> pitchLabel(m.pitch!!)
                }
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 32.dp).semantics(mergeDescendants = true) {},
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
                ) {
                    BcIcon(if (m.agrees) R.drawable.ic_bc_done else R.drawable.ic_bc_info, null, Modifier.size(20.dp), tint = c.textMuted)
                    Text(m.name, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                    Text(heard, style = MaterialTheme.typography.bodyMedium,
                        fontWeight = if (m.agrees) FontWeight.Normal else FontWeight.SemiBold)
                }
            }
        }
    }
}

/**
 * "Change note…": move the written note by semitones or take what a transcriber heard, then Save.
 * Saving writes the score and stays on the note, which is checked only by Keep, as on every platform.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun ChangeNoteSheet(
    written: Int, evidence: NoteEvidence?, pitchLabel: (Int) -> String, dismiss: () -> Unit, save: (Int) -> Unit,
    previewing: Boolean, preview: (Int) -> Unit, stopPreview: () -> Unit,
) {
    var shift by remember(written) { mutableIntStateOf(0) }
    val c = BrasscribeTheme.colors
    // Fully open, and scrollable, so Save is reachable at large text sizes.
    PlaySheet(dismiss, c.bg) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = ScreenMargin).padding(bottom = BrasscribeSpace.s6),
            verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s4),
        ) {
            ScreenTitle(stringResource(R.string.change_note_title))
            Text(
                pitchLabel(written + shift),
                style = MaterialTheme.typography.displaySmall,
                modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite },
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                OutlineButton(stringResource(R.string.pitch_down), { shift -= 1 }, Modifier.weight(1f), enabled = written + shift > 0)
                OutlineButton(stringResource(R.string.pitch_up), { shift += 1 }, Modifier.weight(1f), enabled = written + shift < 127)
            }
            // An octave either way: the other common mishearing of a brass note.
            Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                OutlineButton(stringResource(R.string.octave_down), { shift -= 12 }, Modifier.weight(1f), enabled = written + shift > 11)
                OutlineButton(stringResource(R.string.octave_up), { shift += 12 }, Modifier.weight(1f), enabled = written + shift < 116)
            }
            val heard = evidence?.models.orEmpty().mapNotNull { m -> m.pitch?.let { m.name to it } }
            if (heard.isNotEmpty()) {
                SectionLabel(stringResource(R.string.evidence_heard))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                    heard.forEach { (name, pitch) ->
                        PracticeChip("$name: ${pitchLabel(pitch)}", written + shift == pitch, { shift = pitch - written }, role = Role.RadioButton)
                    }
                }
            }
            // Hear the bar with this pitch before saving: rendered on the phone, nothing is written yet.
            ListenButton(previewing, { preview(shift) }, stopPreview, listenText = stringResource(R.string.change_note_preview), tag = "preview-note")
            PrimaryButton(stringResource(R.string.save), { save(shift) }, enabled = shift != 0)
            PlainButton(stringResource(R.string.cancel), dismiss, Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun EventChip(
    e: PartEvent, spoken: String, checked: Boolean, focus: FocusRequester,
    listen: () -> Unit, check: () -> Unit, next: () -> Unit, label: String, playing: Boolean = false,
) {
    val t = BrasscribeTheme.colors
    val listenLabel = stringResource(if (playing) R.string.listen_stop else R.string.action_listen_bar)
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

/** One bar of the part on a staff, the note ringed (alphaTab, no player). */
@Composable
private fun BarSnippetView(musicXml: String, bar: Int, offsetQuarters: Double, barCount: Int = 1) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val c = BrasscribeTheme.colors
    val snippet = remember { no.brasscribe.play.score.BarSnippet(context) }
    androidx.compose.runtime.LaunchedEffect(c) {
        snippet.setPalette(no.brasscribe.play.score.ScorePalette(c.surfaceRaised.toArgb(), c.ink.toArgb(), c.staff.toArgb(), c.cursor.toArgb(),
            c.uncertain.toArgb(), c.veryUncertain.toArgb(), c.loopTint.toArgb(), c.isHighContrast, c.adlibTint.toArgb(),
            c.selectionTint.toArgb(), c.selectionEdge.toArgb()))
    }
    var height by remember { mutableStateOf(128f) }
    androidx.compose.runtime.DisposableEffect(snippet) {
        // alphaTab's credit line overlaps the system's bottom edge by ~1.5 dp; the dynamics end ~5 dp above it.
        snippet.onStaffBottom = { bottom -> snippet.view.post { height = bottom - 3f } }
        onDispose { snippet.onStaffBottom = {} }
    }
    androidx.compose.runtime.LaunchedEffect(musicXml, bar, offsetQuarters, barCount) { snippet.show(musicXml, bar, offsetQuarters, barCount) }
    Box(Modifier.fillMaxWidth().height(height.dp).clipToBounds().clearAndSetSemantics {}) {
        androidx.compose.ui.viewinterop.AndroidView(factory = { snippet.view }, modifier = Modifier.matchParentSize())
        // Drags on the staff scroll the page: this layer takes the touches before alphaTab's own scroll views.
        Box(Modifier.matchParentSize().pointerInput(Unit) {})
    }
}

/**
 * "Listen to this bar", which turns into "Stop" while the bar plays: one button, same place and size,
 * only the words and the icon change. Both labels are laid out (the other one invisible), so large text
 * that wraps the longer one does not change the height. Enter and Space both press it.
 */
@Composable
fun ListenButton(
    playing: Boolean, listen: () -> Unit, stop: () -> Unit, modifier: Modifier = Modifier,
    listenText: String = stringResource(R.string.action_listen_bar), tag: String = "listen-bar",
) {
    val stopText = stringResource(R.string.listen_stop)
    androidx.compose.material3.FilledTonalButton(
        if (playing) stop else listen,
        modifier.fillMaxWidth().heightIn(min = 48.dp).tagged(tag)
            // Compose buttons take Enter; Space is added so a keyboard user can start and stop with either.
            .onPreviewKeyEvent { e ->
                if (e.key != androidx.compose.ui.input.key.Key.Spacebar) return@onPreviewKeyEvent false
                if (e.type == androidx.compose.ui.input.key.KeyEventType.KeyUp) { if (playing) stop() else listen() }
                true
            },
        shape = no.brasscribe.design.BrasscribeButtonShape,
    ) {
        androidx.compose.foundation.layout.Box(contentAlignment = Alignment.Center) {
            ListenLabel(listenText, R.drawable.ic_bc_listen_bar, Modifier.alpha(if (playing) 0f else 1f).then(if (playing) Modifier.clearAndSetSemantics { } else Modifier))
            ListenLabel(stopText, R.drawable.ic_bc_stop, Modifier.alpha(if (playing) 1f else 0f).then(if (playing) Modifier else Modifier.clearAndSetSemantics { }))
        }
    }
}

@Composable
private fun ListenLabel(text: String, icon: Int, modifier: Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        BcIcon(icon, null)
        androidx.compose.foundation.layout.Spacer(Modifier.size(BrasscribeSpace.s2))
        Text(text, textAlign = androidx.compose.ui.text.style.TextAlign.Center, style = MaterialTheme.typography.labelLarge)
    }
}
