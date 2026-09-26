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
import androidx.compose.ui.unit.dp
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.ScoreEntry

/** The "more" icon on a score row: Edit title, Check the notes, Delete. The same three on every platform. */
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
    return listOfNotNull(profile, date, if (entry.onComputer) stringResource(R.string.on_your_computer) else null).joinToString(" · ")
}
