package no.kalli.scribe.play.ui

import no.kalli.scribe.play.R
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
import no.kalli.scribe.play.ui.theme.productColors
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.Lineup
import no.kalli.scribe.play.fullBandMade
import no.kalli.scribe.play.madeFor
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.engine.NoteEvidence
import no.kalli.scribe.play.noteAt
import no.kalli.scribe.play.arrangementString
import kotlin.math.roundToInt
import no.kalli.scribe.model.Composition
import no.kalli.scribe.model.Instrument
import no.kalli.scribe.model.Lang
import no.kalli.scribe.model.reading
import no.kalli.scribe.model.PICKUP_BAR
import no.kalli.scribe.model.PartEvent
import no.kalli.scribe.model.PartView
import no.kalli.scribe.model.TsContext
import no.kalli.scribe.model.TsSettings
import no.kalli.scribe.model.Uncertainty
import no.kalli.scribe.model.VoiceRole
import java.util.Locale

fun currentLang(): Lang = if (Locale.getDefault().language in setOf("nb", "no", "nn")) Lang.NB else Lang.EN

/** The recording's layers by name (not band parts): what Review calls the voices other than the tune. */
private val LAYER_NAMES = mapOf(
    "bass" to ("Bass" to "Bass"), "strings" to ("Strings" to "Strykere"),
    "hits" to ("Chord hits" to "Akkordslag"), "drums" to ("Drums" to "Trommer"),
)

/**
 * The part that carries the recorded tune and its instrument: the seat's part when the arrangement put
 * the tune there (a solo take with a seat always does), else Solo Cornet in B♭. A bass-clef reader sees
 * it at concert pitch.
 */
fun melodyPart(c: Composition, core: no.kalli.scribe.model.CoreBridge): Pair<String, Instrument> {
    val seatId = c.arrangementString("seat")
    val seat = seatId?.let { id -> core.seats().firstOrNull { it.id == id } }
    if (seat == null || c.arrangementString("lead") != "seat") return no.kalli.scribe.play.PlayViewModel.SOLO_PART_NAME to Instrument.CORNET
    val soloTake = c.voices.count { it.notes.isNotEmpty() } <= 1
    val part = if (soloTake) seat.name else core.seatPart((Lineup.recorded(c) ?: Lineup.FULL.madeFor(c.fullBandMade)).core, seat.id)?.part ?: seat.name
    val chromatic = if (seat.reading(c.arrangementString("reads")) == "bass") 0 else no.kalli.scribe.play.YourParts.chromatic(part, core.seats()) ?: seat.chromatic
    val instrument = if (chromatic == 0) Instrument.CONCERT else Instrument.entries.firstOrNull { it.chromatic == chromatic } ?: Instrument.CORNET
    return part to instrument
}

/** Name and instrument for a Composition voice: the melody reads as the part that carries the tune. */
fun partViewFor(c: Composition, voiceId: String, checked: Set<Int>, core: no.kalli.scribe.model.CoreBridge = no.kalli.scribe.model.KotlinCoreBridge): PartView {
    val v = c.voice(voiceId) ?: c.voices.first()
    if (v.role == VoiceRole.MELODY) {
        val (part, instrument) = melodyPart(c, core)
        return PartView(c, v, instrument, part, core.partNameNb(part), checked, core)
    }
    val (en, nb) = LAYER_NAMES[v.id] ?: (v.id.replaceFirstChar { it.uppercase() } to v.id)
    return PartView(c, v, Instrument.CONCERT, en, nb, checked, core)
}

/** Screen-reader text of every event, each spoken in the context of the one before (spec §4). */
fun announcements(view: PartView, lang: Lang, bridge: no.kalli.scribe.model.CoreBridge): List<String> =
    view.events.mapIndexed { i, e ->
        val prev = view.events.getOrNull(i - 1)
        bridge.announce(e.stop, TsContext(part = if (prev == null) null else view.partName, bar = prev?.bar), TsSettings(), lang)
    }

/** One thing to check: the group's first marked note ([head]), every note in it, and its bars. */
data class ReviewGroup(val head: PartEvent, val members: List<PartEvent>, val very: Boolean, val bars: IntRange)

/**
 * The item of [items] with a note in [bar] nearest [quarters] quarter notes into it: the "?" tapped on the score. Null
 * when nothing in that bar is still to check.
 */
fun itemAt(items: List<ReviewGroup>, composition: Composition, bar: Int, quarters: Double): ReviewGroup? {
    val map = no.kalli.scribe.model.TickMap(composition)
    fun distance(e: PartEvent): Double =
        e.note?.let { kotlin.math.abs((it.start - map.barStart(bar)).toDouble() / composition.ticksPerBeat - quarters) } ?: Double.MAX_VALUE
    return items.mapNotNull { g -> g.members.filter { it.bar == bar }.minOfOrNull(::distance)?.let { g to it } }.minByOrNull { it.second }?.first
}

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
fun itemsToCheck(composition: Composition, checked: Map<String, Set<Int>>, core: no.kalli.scribe.model.CoreBridge): Int =
    composition.voices.filter { it.notes.isNotEmpty() }.sumOf { v ->
        val done = checked[v.id].orEmpty()
        reviewGroups(composition, v.id, partViewFor(composition, v.id, done, core)).count { g -> g.members.any { it.index !in done } }
    }

/** Tonic names by pitch class, flats first as brass bands read them; nb has B for B♭ and H for B. */
private val TONIC_EN = listOf("C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")
private val TONIC_NB = listOf("C", "Dess", "D", "Ess", "E", "F", "Fiss", "G", "Ass", "A", "B", "H")

/** "D major" for a key signature (fifths) and mode, moved by [shift] semitones. */
@Composable
fun keyName(fifths: Int, minor: Boolean, shift: Int, lang: Lang): String {
    val majorPc = Math.floorMod(fifths * 7, 12)
    val pc = Math.floorMod(majorPc + (if (minor) 9 else 0) + shift, 12)
    val tonic = (if (lang == Lang.NB) TONIC_NB else TONIC_EN)[pc]
    val name = if (lang == Lang.NB && minor) tonic.lowercase() else tonic
    return stringResource(if (minor) R.string.key_minor else R.string.key_major, name)
}
