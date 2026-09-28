package no.brasscribe.play.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.SeatChoice
import no.brasscribe.play.TranscriptionResult
import no.brasscribe.play.YourParts
import no.brasscribe.play.arrangementString
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.MusicXmlParts
import no.brasscribe.play.model.PartSource

/**
 * Review's "Yours": the player's part, where it came from, and the recording layer it follows. [voice]
 * is null when the part follows no layer; [arranged] then says so ("Your part is arranged").
 */
data class ReviewYours(
    val part: String?, val source: PartSource?, val voice: String?, val arranged: Boolean, val writtenFor: String? = null,
)

@Composable
fun yoursInReview(vm: PlayViewModel, r: TranscriptionResult, composition: Composition): ReviewYours {
    val core = vm.container.core
    val names = remember(r.musicXml) { MusicXmlParts.names(r.musicXml).map { it.replace('\u00A0', ' ').trim() } }
    val sources = remember(r) { vm.partSources(r) }
    // No answer yet: as before, the tune is yours and nothing is labelled.
    val override by vm.myPartOverride.collectAsState()
    if (vm.container.seat == SeatChoice.NotSet && override == null) return ReviewYours(null, null, null, false)
    val part = vm.yourPart(names, r).index?.let { names.getOrNull(it) } ?: return ReviewYours(null, null, null, false)
    val source = sources[part]
    val lead = YourParts.leadPart(composition, names, core::seatPart)
    val voice = YourParts.voiceOf(part, lead, source, composition)
    // "Written for Euphonium in B♭, treble clef": a take written for the player's own seat.
    val seat = composition.arrangementString("seat")?.let { id -> vm.container.seats.firstOrNull { it.id == id } }
    val written = if (source == PartSource.YOUR_RECORDING && seat != null) {
        if (composition.arrangementString("reads") == "bass") stringResource(R.string.written_for_bass, PartNames.display(seat.name))
        else stringResource(R.string.written_for_treble, PartNames.display(seat.name), stringResource(keyOf(seat.chromatic)))
    } else null
    return ReviewYours(part, source, voice, source == PartSource.ARRANGED, written)
}

/** In place of an empty Yours list: why there is nothing of yours to check, and where to go (§3.6). */
@Composable
fun ArrangedNotice(part: String, checkOthers: () -> Unit, showMine: () -> Unit) {
    val c = BrasscribeTheme.colors
    Column(
        Modifier.fillMaxWidth().background(c.surface, MaterialTheme.shapes.medium).border(1.dp, c.border, MaterialTheme.shapes.medium)
            .padding(BrasscribeSpace.s4).semantics { testTag = "review-arranged" },
        verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3),
    ) {
        SourceLabel(PartSource.ARRANGED)
        // Announced once, politely, when Review opens (4.1.3); nothing is drawn over the controls.
        Column(Modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
            Text(stringResource(R.string.review_arranged_title), style = MaterialTheme.typography.titleMedium, modifier = Modifier.semantics { heading() })
            Text(stringResource(R.string.review_arranged_body, PartNames.display(part)), style = MaterialTheme.typography.bodyMedium, color = c.text)
        }
        PrimaryButton(stringResource(R.string.review_check_others), checkOthers)
        SecondaryButton(stringResource(R.string.review_show_mine), showMine)
    }
}
