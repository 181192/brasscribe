package no.brasscribe.play.ui

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.SeatChoice
import no.brasscribe.play.SeatPickerMode
import no.brasscribe.play.model.Seat

/** One instrument tile: the core's instrument id, its name, an optional second line, and both as spoken. */
private data class InstrumentTile(val id: String, @StringRes val name: Int, @StringRes val sub: Int? = null,
                                  @StringRes val spokenName: Int? = null, @StringRes val spokenSub: Int? = null)

/** The tiles in the mockup's order (design/mockups/my-instrument-first-run.html). */
private val TILES = listOf(
    InstrumentTile("bb-cornet", R.string.inst_cornet),
    InstrumentTile("eb-soprano-cornet", R.string.inst_soprano, R.string.inst_soprano_sub, spokenSub = R.string.inst_soprano_sub_spoken),
    InstrumentTile("flugelhorn", R.string.inst_flugelhorn),
    InstrumentTile("eb-tenor-horn", R.string.inst_tenor_horn, R.string.inst_tenor_horn_sub, spokenSub = R.string.inst_tenor_horn_sub_spoken),
    InstrumentTile("baritone", R.string.inst_baritone),
    InstrumentTile("euphonium", R.string.inst_euphonium),
    InstrumentTile("tenor-trombone", R.string.inst_trombone),
    InstrumentTile("bass-trombone", R.string.inst_bass_trombone),
    InstrumentTile("eb-bass", R.string.inst_eb_bass, spokenName = R.string.inst_eb_bass_spoken),
    InstrumentTile("bb-bass", R.string.inst_bb_bass, spokenName = R.string.inst_bb_bass_spoken),
    InstrumentTile("drum-kit", R.string.inst_percussion),
)

/** "Treble clef in B♭", "Treble clef in E♭" or "Bass clef, as it sounds", for a seat's reading. */
@StringRes
fun readsLabel(reads: String, seat: Seat, settings: Boolean = false): Int = when {
    reads == "bass" -> if (settings) R.string.settings_reads_bass else R.string.seat_reads_bass
    Math.floorMod(seat.chromatic, 12) == 3 -> if (settings) R.string.settings_reads_treble_eflat else R.string.seat_reads_treble_eflat
    else -> if (settings) R.string.settings_reads_treble_bflat else R.string.seat_reads_treble_bflat
}

/** Settings' value: "1st Baritone · treble clef in B♭", "I conduct or listen" or "Not set". */
@Composable
fun seatValue(choice: SeatChoice, seats: List<Seat>): String = when (choice) {
    SeatChoice.NotSet -> stringResource(R.string.settings_seat_not_set)
    SeatChoice.Conductor -> stringResource(R.string.seat_none)
    is SeatChoice.Player -> {
        val seat = seats.firstOrNull { it.id == choice.seat }
        when {
            seat == null -> stringResource(R.string.settings_seat_not_set)
            seat.reads.size > 1 -> stringResource(R.string.settings_seat_value, PartNames.display(seat.name),
                stringResource(readsLabel(choice.reads ?: seat.reads.first(), seat, settings = true)))
            else -> PartNames.display(seat.name)
        }
    }
}

/**
 * "What do you play?" (my-instrument §3.1): the instrument as one radio group of tiles (two columns, one
 * at large text), then Which part? with nothing chosen, then You read for the low brass with the band's
 * default chosen. Nothing is applied until Continue (WCAG 3.2.2); Continue says why it is inactive.
 * The first run, Settings and "Who played this?" all open it; [PlayViewModel.seatPicker] says which.
 */
@Composable
fun WhatDoYouPlayScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val c = BrasscribeTheme.colors
    val seats = vm.container.seats
    val mode = vm.seatPicker
    val start = remember { vm.seatPickerStart() }
    val startSeat = seats.firstOrNull { it.id == start.seatId }
    var instrument by rememberSaveable { mutableStateOf(startSeat?.instrument) }
    var seatId by rememberSaveable { mutableStateOf(startSeat?.id) }
    var reads by rememberSaveable { mutableStateOf(start.readsOrNull ?: startSeat?.reads?.firstOrNull()) }
    val parts = seats.filter { it.instrument == instrument }
    val seat = seats.firstOrNull { it.id == seatId }
    val large = largeText()

    fun pickInstrument(id: String) {
        if (id == instrument) return
        instrument = id
        val offered = seats.filter { it.instrument == id }
        // A new instrument clears the part: a 3rd cornet player is never quietly filed as Solo Cornet.
        seatId = offered.singleOrNull()?.id
        reads = offered.firstOrNull()?.reads?.firstOrNull()
    }

    // The reason Continue waits, and "I conduct or listen". On a phone on its side only Continue is docked,
    // so the instruments keep the screen; these two scroll with them instead.
    val short = androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp < 480
    val Extras = @Composable {
        if (seat == null) Text(
            stringResource(if (instrument == null) R.string.seat_continue_hint else R.string.seat_part_hint),
            style = MaterialTheme.typography.bodyMedium, color = c.textMuted,
            modifier = Modifier.fillMaxWidth().testTag("seat-hint"),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        PlainButton(stringResource(R.string.seat_none), { vm.chooseSeat(SeatChoice.Conductor) },
            Modifier.fillMaxWidth().testTag("seat-none"))
    }
    PlayScaffold(
        title = null,
        onBack = if (mode == SeatPickerMode.FIRST_RUN) null else ({ vm.back() }),
        backLabel = stringResource(if (mode == SeatPickerMode.SETTINGS) R.string.settings else R.string.back),
        status = status,
        actions = { if (mode == SeatPickerMode.FIRST_RUN) PlainButton(stringResource(R.string.seat_skip), vm::skipSeat, Modifier.testTag("seat-skip")) },
        bottom = {
            PrimaryButton(stringResource(R.string.continue_label), {
                seat?.let { s -> vm.chooseSeat(SeatChoice.Player(s.id, reads?.takeIf { s.reads.size > 1 })) }
            }, enabled = seat != null, modifier = Modifier.testTag("seat-continue"))
            if (!short) Extras()
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            ScreenTitle(stringResource(if (mode == SeatPickerMode.WHO_PLAYED) R.string.who_played else R.string.seat_title))
            if (mode != SeatPickerMode.WHO_PLAYED) Lead(stringResource(R.string.seat_body))
        }
        val groupLabel = stringResource(R.string.seat_instrument)
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            Text(groupLabel, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.semantics { heading() })
            val tiles = TILES.filter { t -> seats.any { it.instrument == t.id } }
            Column(Modifier.selectableGroup().semantics { contentDescription = groupLabel },
                verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                tiles.chunked(if (large) 1 else 2).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
                        row.forEach { t -> Tile(t, t.id == instrument, Modifier.weight(1f)) { pickInstrument(t.id) } }
                        if (row.size == 1 && !large) Spacer(Modifier.weight(1f))
                    }
                }
            }
        }
        if (parts.size > 1) Choices(
            stringResource(R.string.seat_which_part), parts.map { it.id to PartNames.display(it.name) }, seatId, large, "seat-part",
        ) { seatId = it }
        val offered = (seat ?: parts.firstOrNull())?.reads.orEmpty()
        val readsSeat = seat ?: parts.firstOrNull()
        if (offered.size > 1 && readsSeat != null) Choices(
            stringResource(R.string.seat_reads), offered.map { it to stringResource(readsLabel(it, readsSeat)) }, reads, large, "seat-reads",
        ) { reads = it }
        if (short) Extras()
    }
}

/** An instrument tile: at least 56 dp, a hairline border, or a 2 dp ink ring and a check when chosen. */
@Composable
private fun Tile(t: InstrumentTile, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val c = BrasscribeTheme.colors
    val name = stringResource(t.name)
    val sub = t.sub?.let { stringResource(it) }
    // The accessible name holds the visible words, with ♭ read as "flat" (2.5.3).
    val spoken = listOfNotNull(stringResource(t.spokenName ?: t.name), (t.spokenSub ?: t.sub)?.let { stringResource(it) }).joinToString(" ")
    Row(
        modifier.heightIn(min = 56.dp)
            .background(c.surfaceRaised, MaterialTheme.shapes.medium)
            .border(if (selected) 2.dp else 1.dp, if (selected) c.text else c.borderStrong, MaterialTheme.shapes.medium)
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .semantics(mergeDescendants = true) { contentDescription = spoken }
            .testTag("instrument-${t.id}")
            .padding(horizontal = BrasscribeSpace.s3, vertical = BrasscribeSpace.s2),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).clearAndSetSemantics { }) {
            Text(name, style = MaterialTheme.typography.titleMedium, color = c.text)
            if (sub != null) Text(sub, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        if (selected) BcIcon(R.drawable.ic_bc_done, null, Modifier.size(20.dp))
    }
}

/**
 * A labelled radio group: segments in one row, or a vertical list at large text (§3.9 reflow). The
 * chosen one has the tonal fill, an ink edge and a check, as every toggle does.
 */
@Composable
private fun Choices(label: String, options: List<Pair<String, String>>, selected: String?, large: Boolean, tag: String, onPick: (String) -> Unit) {
    val c = BrasscribeTheme.colors
    Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        Text(label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, modifier = Modifier.semantics { heading() })
        val item = @Composable { id: String, text: String, m: Modifier ->
            val on = id == selected
            Row(
                m.heightIn(min = 48.dp)
                    .background(if (on) c.secondary else c.surfaceRaised, BrasscribeButtonShape)
                    .border(if (on) 1.5.dp else 1.dp, if (on) c.text else c.borderStrong, BrasscribeButtonShape)
                    .selectable(selected = on, role = Role.RadioButton) { onPick(id) }
                    .testTag("$tag-$id")
                    .padding(horizontal = BrasscribeSpace.s3, vertical = BrasscribeSpace.s2),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = if (large) Arrangement.Start else Arrangement.Center,
            ) {
                if (large) {
                    RadioButton(selected = on, onClick = null, colors = RadioButtonDefaults.colors(selectedColor = c.text, unselectedColor = c.borderStrong))
                    Spacer(Modifier.size(BrasscribeSpace.s2))
                } else if (on) {
                    BcIcon(R.drawable.ic_bc_done, null, Modifier.size(18.dp))
                    Spacer(Modifier.size(BrasscribeSpace.s1))
                }
                Text(text, style = MaterialTheme.typography.labelLarge, color = if (on) c.text else c.textMuted,
                    fontWeight = if (on) FontWeight.SemiBold else FontWeight.Medium)
            }
        }
        if (large) Column(Modifier.selectableGroup().semantics { contentDescription = label }, verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            options.forEach { (id, text) -> item(id, text, Modifier.fillMaxWidth()) }
        } else Row(Modifier.selectableGroup().semantics { contentDescription = label }, horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            options.forEach { (id, text) -> item(id, text, Modifier.weight(1f)) }
        }
    }
}

/**
 * Where a part came from (§3.6): an outline pill with an icon and the words, never a colour. It is a
 * button (48 dp) that opens one sentence of explanation.
 */
@Composable
fun SourceLabel(source: no.brasscribe.play.model.PartSource, modifier: Modifier = Modifier, compact: Boolean = false, onExplain: (() -> Unit)? = null) {
    val c = BrasscribeTheme.colors
    var open by rememberSaveable { mutableStateOf(false) }
    val (@StringRes text, @DrawableRes icon) = when (source) {
        no.brasscribe.play.model.PartSource.YOUR_RECORDING -> R.string.source_yours to R.drawable.ic_bc_record_mic
        no.brasscribe.play.model.PartSource.RECORDING -> R.string.source_recording to R.drawable.ic_bc_record_mic
        no.brasscribe.play.model.PartSource.ARRANGED -> R.string.source_arranged to R.drawable.ic_bc_parts
        no.brasscribe.play.model.PartSource.EMPTY -> R.string.source_empty to R.drawable.ic_bc_parts
    }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1)) {
        Row(
            Modifier.heightIn(min = 48.dp)
                .border(1.dp, c.borderStrong, androidx.compose.foundation.shape.RoundedCornerShape(percent = 50))
                .clickable(role = Role.Button) { if (onExplain != null) onExplain() else open = !open }
                .testTag("source-${source.id}")
                .padding(horizontal = if (compact) BrasscribeSpace.s3 else BrasscribeSpace.s4),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(if (compact) BrasscribeSpace.s1 else BrasscribeSpace.s2),
        ) {
            BcIcon(icon, null, Modifier.size(if (compact) 16.dp else 20.dp), tint = c.text)
            Text(stringResource(text), style = if (compact) MaterialTheme.typography.labelMedium else MaterialTheme.typography.labelLarge, color = c.text)
        }
        if (open) Text(
            stringResource(explainOf(source)),
            style = MaterialTheme.typography.bodyMedium, color = c.textMuted,
            modifier = Modifier.semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite },
        )
    }
}

/** "This small band has no 1st Baritone. Your part here is Euphonium…", one definite form per lineup. */
@Composable
fun mappedText(m: no.brasscribe.play.MappedSeat, reads: String?, seats: List<Seat>): String {
    val quartet = m.lineup == no.brasscribe.play.Lineup.QUARTET
    val seat = PartNames.display(m.seat.name)
    val part = m.part ?: return stringResource(if (quartet) R.string.mapped_none_quartet else R.string.mapped_none_minimal)
    val shown = PartNames.display(part)
    return if (m.sameKey || reads == "bass") stringResource(if (quartet) R.string.mapped_same_quartet else R.string.mapped_same_minimal, seat, shown)
    else stringResource(if (quartet) R.string.mapped_other_quartet else R.string.mapped_other_minimal, seat, shown,
        stringResource(keyOf(no.brasscribe.play.YourParts.chromatic(part, seats) ?: m.seat.chromatic)))
}

/** "B♭" or "E♭": the key a part is written in, from its transposition. */
@StringRes
fun keyOf(chromatic: Int): Int = if (Math.floorMod(chromatic, 12) == 3) R.string.key_eflat else R.string.key_bflat

/** The one-line form of [mappedText] for the score's banner: "The small band has no 1st Baritone — showing Euphonium". */
@Composable
fun mappedShort(m: no.brasscribe.play.MappedSeat): String {
    val quartet = m.lineup == no.brasscribe.play.Lineup.QUARTET
    val part = m.part ?: return stringResource(if (quartet) R.string.mapped_short_none_quartet else R.string.mapped_short_none_minimal)
    return stringResource(if (quartet) R.string.mapped_short_quartet else R.string.mapped_short_minimal, PartNames.display(m.seat.name), PartNames.display(part))
}

/** Where a part came from, in one sentence: what the source pill opens. */
@StringRes
fun explainOf(source: no.brasscribe.play.model.PartSource): Int = when (source) {
    no.brasscribe.play.model.PartSource.ARRANGED -> R.string.explain_arranged
    no.brasscribe.play.model.PartSource.EMPTY -> R.string.explain_empty
    else -> R.string.explain_recording
}
