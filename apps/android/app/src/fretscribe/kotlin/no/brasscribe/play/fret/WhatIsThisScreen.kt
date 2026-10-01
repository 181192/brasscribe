package no.brasscribe.play.fret

import androidx.compose.foundation.focusable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.OnDeviceRouting
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.engine.Recording
import no.brasscribe.play.ui.ChoiceCard
import no.brasscribe.play.ui.ChoiceGroup
import no.brasscribe.play.ui.ConnectionStatusRow
import no.brasscribe.play.ui.Lead
import no.brasscribe.play.ui.ListRow
import no.brasscribe.play.ui.PlayScaffold
import no.brasscribe.play.ui.PrimaryButton
import no.brasscribe.play.ui.RowGroup
import no.brasscribe.play.ui.ScreenTitle
import no.brasscribe.play.ui.clock

private class Answer(val recording: Recording, val tag: String, val title: Int, val desc: Int)

private val CHOICES = listOf(
    Answer(Recording.INSTRUMENT, "instrument", R.string.fs_what_instrument, R.string.fs_what_instrument_desc),
    Answer(Recording.SONG, "song", R.string.fs_what_song, R.string.fs_what_song_desc),
)

/**
 * "What is this?" (design/fretscribe/flows.md §5): the bass alone, or a full song the bass is picked out
 * of. Nothing is chosen until the player chooses, and the answer stays with the recording. In this
 * version the computer writes down the notes for both, so the row under the choices says whether it is
 * there, with the way to connect it when it is not.
 */
@Composable
fun WhatIsThisScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val source by vm.source.collectAsState()
    val connection by vm.connection.state.collectAsState()
    val answer = SongAnswers.of(source)
    // The fixture engine of the UI tests is always there.
    val there = vm.container.usingFixture || OnDeviceRouting.computerThere(connection)
    val headingFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { headingFocus.requestFocus() } }

    PlayScaffold(
        title = source?.let { s -> if (s.durationS > 0) "${s.name} · ${clock(s.durationS)}" else s.name },
        onBack = vm::back, backLabel = stringResource(R.string.home), status = status,
        bottom = {
            // One line says what is still missing; the computer comes first, since the row above has its button.
            val missing = when {
                !there -> R.string.fs_what_connect_first
                answer.recording == null -> R.string.profile_choose_one
                else -> null
            }
            if (missing != null) Text(stringResource(missing), style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
            PrimaryButton(stringResource(R.string.continue_label), {
                vm.chooseProfile(Profile.BASS_TAB)
                vm.startTranscription()
            }, Modifier.testTag("fs-what-continue"), enabled = there && answer.recording != null)
        },
    ) {
        ScreenTitle(stringResource(R.string.profile_title), Modifier.focusRequester(headingFocus).focusable())
        Lead(stringResource(R.string.fs_what_hint))
        ChoiceGroup(CHOICES.size) {
            CHOICES.forEachIndexed { i, c ->
                androidx.compose.foundation.layout.Box(Modifier.testTag("fs-what-${c.tag}")) {
                    ChoiceCard(stringResource(c.title), stringResource(c.desc), answer.recording == c.recording, true, i) {
                        SongAnswers.set(source, answer.copy(recording = c.recording))
                    }
                }
            }
        }
        if (there) RowGroup(Modifier.testTag("fs-what-where")) {
            ListRow(stringResource(R.string.where_companion), null, subtitle = stringResource(R.string.fs_where_desc), icon = R.drawable.ic_bc_computer)
        } else {
            Text(stringResource(R.string.fs_where_needed), style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
            // Connect or Pair this phone again, as on Home: the pairing screen, or another try at a paired computer.
            ConnectionStatusRow(vm, Modifier.testTag("fs-what-connect"))
        }
    }
}
