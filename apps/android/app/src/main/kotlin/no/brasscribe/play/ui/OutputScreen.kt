package no.brasscribe.play.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.update
import no.brasscribe.design.BrasscribeButtonShape
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.Difficulty
import no.brasscribe.play.Lineup
import no.brasscribe.play.fullBandMade
import no.brasscribe.play.isSoloTake
import no.brasscribe.play.madeFor
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.reading

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

/**
 * How should the score be? (mockups/png/choose-output-*): Which band?, How hard? with its tip, and
 * Key, then Show the score. Full band, Small band and Quartet map to the arranger's lineups; the
 * three difficulty segments to faithful, standard and easier. The quartet needs a take with harmony,
 * so it is unavailable for a solo take.
 */
@Composable
fun OutputScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val options by vm.output.collectAsState()
    val result by vm.result.collectAsState()
    val busy by vm.busy.collectAsState()
    val c = BrasscribeTheme.colors
    val lang = currentLang()
    // Band and difficulty are arranged by the Rust core (on-device results) or by Brasscribe on the
    // computer (a new run with the choices); without either only the key remains.
    val r = result
    val canArrange = r != null && ((r.onDevice && vm.container.core.name.startsWith("rust")) || (!r.onDevice && r.audioId != null))
    val lineups = listOf(Lineup.FULL, Lineup.MINIMAL, Lineup.QUARTET)
    // A solo take has no harmony for four parts: the quartet card says so and stays reachable.
    val soloTake = r?.isSoloTake == true
    val needsGroup = stringResource(R.string.lineup_quartet_needs_group)
    // A Brass band or Pop or rock take is made for the small band: Full brass band says so and can't be picked.
    val fullBand = r?.fullBandMade != false
    val notYet = stringResource(R.string.lineup_full_not_yet)
    val key = r?.composition?.keys?.firstOrNull()
    // Who the score is for: the take's player (pre-filled from Settings), and their part in each lineup.
    val seats = vm.container.seats
    val seat = seats.firstOrNull { it.id == options.seat }
    val yourPartIn = { l: Lineup -> seat?.let { s -> vm.container.core.seatPart(l.core, s.id)?.part } }
    val onePart = soloTake && seat != null
    val yourName = seat?.let { PartNames.display(it.name) }

    PlayScaffold(
        title = null, onBack = vm::back, backLabel = r?.composition?.title?.ifBlank { null }?.let(PartNames::shortTitle) ?: stringResource(R.string.back), status = status,
        bottom = {
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
            PrimaryButton(stringResource(R.string.output_apply), { vm.applyOutput { vm.navigate(Screen.SCORE) } }, enabled = !busy)
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            ScreenTitle(stringResource(R.string.output_title))
            Lead(stringResource(R.string.output_lead))
        }
        // A solo take: whoever played it. Changing it writes for another instrument, on Show the score.
        if (soloTake && seats.isNotEmpty() && canArrange) {
            SubHeading(stringResource(R.string.who_played))
            RowGroup {
                ListRow(yourName ?: stringResource(R.string.settings_seat_not_set), { vm.openSeatPicker(no.brasscribe.play.SeatPickerMode.WHO_PLAYED) },
                    androidx.compose.ui.Modifier.semantics { testTag = "who-played" },
                    subtitle = seat?.takeIf { it.reads.size > 1 }?.let { s -> stringResource(readsLabel(options.reads ?: s.reads.first(), s)) },
                    icon = R.drawable.ic_bc_parts)
            }
        }
        if (onePart) InfoNote(stringResource(R.string.solo_one_part), boxed = false)
        else {
            SubHeading(stringResource(R.string.lineup))
            ChoiceGroup(lineups.size) {
                lineups.forEachIndexed { i, l ->
                    val unavailable = l == Lineup.FULL && !fullBand
                    val reason = needsGroup.takeIf { l == Lineup.QUARTET && soloTake } ?: notYet.takeIf { unavailable }
                    // "Small band · 8 players · your part: Euphonium": known before Show the score, for a lineup that is made.
                    val desc = yourPartIn(l)?.takeIf { !unavailable }?.let { stringResource(R.string.lineup_your_part, stringResource(l.desc), PartNames.display(it)) } ?: stringResource(l.desc)
                    ChoiceCard(stringResource(l.label), desc, options.lineup == l, !unavailable && (canArrange || l == Lineup.FULL.madeFor(fullBand)), i, reason) {
                        vm.output.update { it.copy(lineup = l, lead = it.lead.takeIf { l != Lineup.QUARTET }) }
                    }
                }
            }
        }
        // A soloist recording: the tune on the lineup's lead as usual, or on the player's part (band lineups only).
        val yourBandPart = yourPartIn(options.lineup)
        if (!soloTake && canArrange && seat != null && seat.tune && options.lineup != Lineup.QUARTET && yourBandPart != null &&
            yourBandPart != options.lineup.lead && r?.profile in setOf(no.brasscribe.play.engine.Profile.ORCHESTRA_WITH_SOLOIST, no.brasscribe.play.engine.Profile.BRASS_BAND)) {
            SubHeading(stringResource(R.string.who_plays_tune))
            ChoiceGroup(2) {
                ChoiceCard(stringResource(R.string.tune_lineup, PartNames.display(options.lineup.lead)), null, options.lead != "seat", true, 0) {
                    vm.output.update { it.copy(lead = null) }
                }
                ChoiceCard(stringResource(R.string.tune_seat, PartNames.display(yourBandPart)), null, options.lead == "seat", true, 1) {
                    vm.output.update { it.copy(lead = "seat") }
                }
            }
        }
        SubHeading(stringResource(R.string.difficulty))
        val levels = listOf(Difficulty.EASIER, Difficulty.STANDARD, Difficulty.FAITHFUL)
        if (largeText()) ChoiceGroup(levels.size) {
            levels.forEachIndexed { i, d ->
                ChoiceCard(stringResource(d.label), null, options.difficulty == d, canArrange || d == Difficulty.FAITHFUL, i) {
                    vm.output.update { it.copy(difficulty = d) }
                }
            }
        } else SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            levels.forEachIndexed { i, d ->
                SegmentedButton(
                    selected = options.difficulty == d, onClick = { vm.output.update { it.copy(difficulty = d) } },
                    shape = SegmentedButtonDefaults.itemShape(i, levels.size), enabled = canArrange || d == Difficulty.FAITHFUL,
                    colors = SegmentedButtonDefaults.colors(
                        activeContainerColor = c.surfaceRaised, activeContentColor = c.text, activeBorderColor = c.borderStrong,
                        inactiveContainerColor = c.secondary, inactiveContentColor = c.textMuted, inactiveBorderColor = c.border,
                    ),
                    icon = {},
                    modifier = Modifier.heightIn(min = 48.dp),
                ) { Text(stringResource(d.label), maxLines = 2) }
            }
        }
        InfoNote(stringResource(if (canArrange) R.string.difficulty_tip else R.string.difficulty_unsupported), boxed = false)
        SubHeading(stringResource(R.string.key_label))
        val shiftText = if (options.keyShift == 0) stringResource(R.string.key_as_recorded)
        else stringResource(R.string.key_shifted, (if (options.keyShift > 0) "+" else "−") +
            pluralStringResource(R.plurals.key_shift, kotlin.math.abs(options.keyShift), kotlin.math.abs(options.keyShift)))
        // Both keys: the concert key and the one B-flat players read on their parts (review 2, P2-3).
        Column(
            Modifier.fillMaxWidth().heightIn(min = 56.dp).border(1.dp, c.borderStrong, BrasscribeButtonShape)
                .padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3)
                .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
            verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s1),
        ) {
            if (key != null) {
                val minor = key.mode == "minor"
                Text(stringResource(R.string.key_concert, keyName(key.fifths, minor, options.keyShift, lang)), style = MaterialTheme.typography.titleMedium)
                // With a seat: the key on the player's own part (or as it sounds in bass clef); else B♭ players' key.
                val part = if (onePart) seat?.name else yourPartIn(options.lineup)
                val chromatic = part?.let { no.brasscribe.play.YourParts.chromatic(it, seats) }
                when {
                    seat != null && seat.reading(options.reads) == "bass" -> Text(stringResource(R.string.key_as_it_sounds, keyName(key.fifths, minor, options.keyShift, lang)), style = MaterialTheme.typography.bodyLarge)
                    chromatic != null && chromatic != 0 -> Text(stringResource(R.string.key_on_your_part, keyName(key.fifths, minor, options.keyShift - chromatic, lang)), style = MaterialTheme.typography.bodyLarge)
                    seat == null -> Text(stringResource(R.string.key_for_bflat, keyName(key.fifths, minor, options.keyShift + 2, lang)), style = MaterialTheme.typography.bodyLarge)
                }
            }
            Text(shiftText, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
        val semitone = stringResource(R.string.key_semitone_hint)
        Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
            SecondaryButton(stringResource(R.string.key_lower), { vm.output.update { it.copy(keyShift = (it.keyShift - 1).coerceAtLeast(-6)) } },
                Modifier.weight(1f).semantics { stateDescription = semitone }, enabled = options.keyShift > -6)
            SecondaryButton(stringResource(R.string.key_higher), { vm.output.update { it.copy(keyShift = (it.keyShift + 1).coerceAtMost(6)) } },
                Modifier.weight(1f).semantics { stateDescription = semitone }, enabled = options.keyShift < 6)
        }
    }
}
