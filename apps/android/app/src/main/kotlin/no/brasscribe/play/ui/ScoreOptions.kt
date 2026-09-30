package no.brasscribe.play.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.ScoreEntry

/** The "more" icon on a score row: Edit title, Open on the music stand, Check the notes, Delete. */
@Composable
fun ScoreOptionsButton(vm: PlayViewModel, entry: ScoreEntry) {
    var menu by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf(false) }
    var draft by remember { mutableStateOf(entry.title) }
    val c = BrasscribeTheme.colors

    Box {
        IconButton({ menu = true }, Modifier.size(48.dp)) {
            BcIcon(R.drawable.ic_bc_more, stringResource(R.string.score_options, entry.title), tint = c.textMuted)
        }
        DropdownMenu(menu, { menu = false }) {
            DropdownMenuItem(
                text = { Text(stringResource(R.string.edit_title)) },
                leadingIcon = { BcIcon(R.drawable.ic_bc_text_size, null) },
                onClick = { menu = false; draft = entry.title; renaming = true },
            )
            DropdownMenuItem(
                text = { Text(stringResource(R.string.stand_open_from_library)) },
                leadingIcon = { BcIcon(R.drawable.ic_stand_music_stand, null) },
                onClick = { menu = false; vm.openEntry(entry, stand = true) },
                modifier = Modifier.semantics { testTag = "open-on-stand" },
            )
            DropdownMenuItem(
                text = { Text(stringResource(R.string.check_notes)) },
                leadingIcon = { BcIcon(R.drawable.ic_bc_next_uncertain, null) },
                onClick = { menu = false; vm.openEntry(entry, review = true) },
            )
            DropdownMenuItem(
                text = { Text(stringResource(R.string.delete), color = c.veryUncertain) },
                leadingIcon = { BcIcon(R.drawable.ic_bc_delete, null, tint = c.veryUncertain) },
                onClick = { menu = false; deleting = true },
            )
        }
    }

    if (renaming) {
        AlertDialog(
            onDismissRequest = { renaming = false },
            title = { Text(stringResource(R.string.edit_title)) },
            text = {
                OutlinedTextField(draft, { draft = it }, label = { Text(stringResource(R.string.score_title)) }, singleLine = true)
            },
            confirmButton = {
                TextButton({ vm.renameEntry(entry, draft); renaming = false }, enabled = draft.isNotBlank()) { Text(stringResource(R.string.save)) }
            },
            dismissButton = { TextButton({ renaming = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
    if (deleting) {
        AlertDialog(
            onDismissRequest = { deleting = false },
            title = { Text(stringResource(R.string.delete_score_title, entry.title)) },
            text = { Text(stringResource(if (entry.onComputer) R.string.delete_score_computer else R.string.delete_score_phone)) },
            confirmButton = {
                TextButton({ vm.deleteEntry(entry); deleting = false }) { Text(stringResource(R.string.delete), color = c.veryUncertain) }
            },
            dismissButton = { TextButton({ deleting = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
fun scoreSubtitle(entry: ScoreEntry): String {
    val profile = when (entry.profile) {
        "solo" -> stringResource(R.string.profile_solo)
        "brass-band" -> stringResource(R.string.profile_brass_band)
        "orchestra-with-soloist" -> stringResource(R.string.profile_orchestra)
        "pop-rock" -> stringResource(R.string.profile_pop)
        else -> entry.profile
    }
    val date = android.text.format.DateUtils.getRelativeTimeSpanString(entry.updated, System.currentTimeMillis(),
        android.text.format.DateUtils.DAY_IN_MILLIS).toString()
    // "Full band · 132 bars · Today · 83 to check" for the phone's scores (review 3).
    val container = androidx.compose.ui.platform.LocalContext.current.let { (it.applicationContext as no.brasscribe.play.PlayApplication).container }
    val saved = entry.saved
    // Worked out off the main thread: reading, decoding and grouping a full band takes a moment per score.
    val facts by androidx.compose.runtime.produceState<ScoreFacts?>(null, saved?.id, saved?.updated) {
        saved ?: return@produceState
        value = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            container.scoreLibrary.content(saved.id)?.let { factsOf(saved, it, container.core) }
        }
    }
    // The label comes from the lineup the score was arranged for; the part count only tells a band from a solo.
    val band = facts?.let { f ->
        when (f.lineup) {
            no.brasscribe.play.Lineup.QUARTET -> stringResource(R.string.lineup_quartet)
            no.brasscribe.play.Lineup.MINIMAL -> stringResource(R.string.lineup_minimal)
            no.brasscribe.play.Lineup.FULL -> stringResource(R.string.home_full_band)
            null -> if (f.parts > 1) stringResource(R.string.home_full_band) else stringResource(R.string.lineup_solo)
        }
    } ?: profile
    val bars = facts?.bars?.takeIf { it > 0 }?.let { androidx.compose.ui.res.pluralStringResource(R.plurals.home_bars, it, it) }
    val left = facts?.left?.takeIf { it > 0 }?.let { androidx.compose.ui.res.pluralStringResource(R.plurals.home_to_check, it, it) }
    val draft = if (entry.saved?.draft == true) stringResource(R.string.draft_label) else null
    return listOfNotNull(band, draft, bars, date, left, if (entry.onComputer) stringResource(R.string.on_your_computer) else null).joinToString(" · ")
}

/** Parts, bars, review items left and the recorded lineup of a saved score. */
private data class ScoreFacts(val parts: Int, val bars: Int, val left: Int?, val lineup: no.brasscribe.play.Lineup?)

private fun factsOf(saved: no.brasscribe.play.SavedScore, content: no.brasscribe.play.SavedScoreContent, core: no.brasscribe.play.model.CoreBridge): ScoreFacts {
    run {
        val parts = no.brasscribe.play.model.MusicXmlParts.names(content.musicXml)
        val bars = Regex("""<part\s+id="[^"]+"\s*>(.*?)</part>""", RegexOption.DOT_MATCHES_ALL).find(content.musicXml)
            ?.groupValues?.get(1)?.let { Regex("<measure\\b").findAll(it).count() } ?: 0
        val checked = saved.checked.mapNotNull { k -> k.substringBefore(':').let { v -> k.substringAfter(':').toIntOrNull()?.let { v to it } } }
            .groupBy({ it.first }, { it.second }).mapValues { it.value.toSet() }
        val composition = content.compositionJson?.let { j -> runCatching { core.decodeComposition(j) }.getOrNull() }
        val left = composition?.let { runCatching { itemsToCheck(it, checked, core) }.getOrNull() }
        val lineup = no.brasscribe.play.Lineup.recorded(composition) ?: no.brasscribe.play.Lineup.ofParts(parts)
        return ScoreFacts(parts.size, bars, left, lineup)
    }
}
