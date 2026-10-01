package no.brasscribe.play.fret

import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.ErrorWords
import no.brasscribe.play.NoCompanionException
import no.brasscribe.play.OnDeviceRouting
import no.brasscribe.play.PlayApplication
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.ScoreEntry
import no.brasscribe.play.Screen
import no.brasscribe.play.engine.Octave
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.engine.Tab
import no.brasscribe.play.ui.InfoNote
import no.brasscribe.play.ui.Lead
import no.brasscribe.play.ui.OutlineButton
import no.brasscribe.play.ui.PlayScaffold
import no.brasscribe.play.ui.PrimaryButton
import no.brasscribe.play.ui.RowDivider
import no.brasscribe.play.ui.RowGroup
import no.brasscribe.play.ui.ScreenTitle
import no.brasscribe.play.ui.currentLang
import no.brasscribe.play.ui.keyName

/** The tab's facts as they come from the computer: still being read, there, or not to be had right now. */
private sealed interface Heard {
    data object Reading : Heard
    data class Ready(val tab: Tab) : Heard
    data class Missing(val why: Int) : Heard
}

/** What a row's button asks for: the same recording written down again with this changed. */
private class Change(val label: String, val tag: String, val answer: (SongAnswer) -> SongAnswer)

/**
 * "Check the song" (design/fretscribe/flows.md §7), in its first form: what Fretscribe heard, one row per
 * finding the result has (tuning, octave, reference pitch, key and tempo, notes marked ? and notes with
 * no place), and Show the tab. A row's button sends the recording to the computer again with that one
 * thing changed; the computer keeps what it already worked out, so only the fingering is done again.
 */
@Composable
fun CheckTheSongScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val result by vm.result.collectAsState()
    val source by vm.source.collectAsState()
    val connection by vm.connection.state.collectAsState()
    val c = BrasscribeTheme.colors
    val jobId = result?.jobId
    val heard by produceState<Heard>(Heard.Reading, jobId) {
        value = Heard.Reading
        value = try {
            val engine = vm.container.engine() ?: throw NoCompanionException()
            Heard.Ready(withContext(Dispatchers.IO) { engine.tab(jobId ?: throw NoCompanionException()) })
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            android.util.Log.w(PlayViewModel.TAG, "the tab's facts could not be read", e)
            Heard.Missing(ErrorWords.of(e))
        }
    }
    val there = vm.container.usingFixture || OnDeviceRouting.computerThere(connection)
    // The recording is sent again from its file: a song opened from Your songs has none in hand.
    val canChange = there && source?.file?.isFile == true
    val headingFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { headingFocus.requestFocus() } }

    fun writeAgain(change: Change) {
        SongAnswers.set(source, change.answer(SongAnswers.of(source)))
        vm.chooseProfile(Profile.BASS_TAB)
        // Writing down the notes takes this screen's place, and it comes back when they are written.
        vm.back()
        vm.startTranscription()
    }

    PlayScaffold(
        title = source?.name?.substringBeforeLast('.'), onBack = vm::back, backLabel = stringResource(R.string.back), status = status,
        bottom = {
            Text(stringResource(R.string.fs_check_later), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            PrimaryButton(stringResource(R.string.fs_show_tab), { vm.navigate(Screen.SCORE) }, Modifier.testTag("fs-show-tab"))
        },
    ) {
        ScreenTitle(stringResource(R.string.fs_check_title), Modifier.focusRequester(headingFocus).focusable())
        when (val h = heard) {
            Heard.Reading -> {
                Lead(stringResource(R.string.fs_check_reading))
                LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
            }
            is Heard.Missing -> InfoNote(stringResource(R.string.fs_check_missing, stringResource(h.why)), Modifier.testTag("fs-check-missing"))
            is Heard.Ready -> {
                Lead(stringResource(R.string.fs_check_lead))
                val rows = remember(h.tab) { SongCheck.rows(h.tab) }
                val changes = rows.map { changeFor(it) }
                RowGroup {
                    rows.forEachIndexed { i, row ->
                        if (i > 0) RowDivider()
                        SongRowView(row, changes[i]?.takeIf { canChange }, ::writeAgain)
                    }
                }
                if (changes.any { it != null } && !canChange) InfoNote(stringResource(if (there) R.string.fs_check_open_again else R.string.fs_check_connect))
            }
        }
    }
}

/** The change a row offers, if the computer takes one for it. */
@Composable
private fun changeFor(row: SongRow): Change? = when (row) {
    is SongRow.Tuning -> row.soundsLike?.let { id ->
        Change(stringResource(R.string.fs_check_use, tuningName(id)), "tuning") { it.copy(tuning = id) }
    }
    is SongRow.Octave ->
        if (row.chosen) Change(stringResource(R.string.fs_check_octave_auto), "octave") { it.copy(octave = Octave.AUTO) }
        else if (row.shift != 0) Change(stringResource(R.string.fs_check_as_heard), "octave") { it.copy(octave = Octave.AS_HEARD) }
        else null
    else -> null
}

/** What a row says, as shown and as spoken (the tempo sign and the time signature are said in words). */
@Composable
private fun rowWords(row: SongRow): Triple<String, String, String> = when (row) {
    is SongRow.Tuning -> {
        val written = tuningName(row.written)
        val shown = row.soundsLike?.let { stringResource(R.string.fs_check_sounds_like, tuningName(it), written) } ?: written
        val spoken = row.soundsLike?.let { stringResource(R.string.fs_check_sounds_like, tuningName(it, spoken = true), tuningName(row.written, spoken = true)) }
            ?: tuningName(row.written, spoken = true)
        Triple(stringResource(R.string.fs_check_tuning), shown, spoken)
    }
    is SongRow.Octave -> {
        val text = when {
            row.chosen && row.shift == 0 -> stringResource(R.string.fs_check_octave_as_heard)
            row.chosen && row.shift < 0 -> stringResource(R.string.fs_check_octave_chosen_down)
            row.chosen -> stringResource(R.string.fs_check_octave_chosen_up)
            row.shift <= -24 -> stringResource(R.string.fs_check_octave_two_down)
            row.shift < 0 -> stringResource(R.string.fs_check_octave_down)
            row.shift > 0 -> stringResource(R.string.fs_check_octave_up)
            else -> pluralStringResource(R.plurals.fs_check_octave_notes, row.notesMoved, row.notesMoved)
        }
        Triple(stringResource(R.string.fs_check_octave), text, text)
    }
    is SongRow.ReferencePitch -> {
        val cents = kotlin.math.abs(row.cents)
        val text = stringResource(if (row.cents > 0) R.string.fs_check_reference_sharp else R.string.fs_check_reference_flat, cents) +
            if (row.retuned) " " + stringResource(R.string.fs_check_reference_allowed) else ""
        Triple(stringResource(R.string.fs_check_reference), text, text)
    }
    is SongRow.KeyAndTempo -> {
        val key = keyName(row.fifths, row.minor, 0, currentLang())
        Triple(stringResource(R.string.fs_check_key_tempo),
            stringResource(R.string.fs_check_key_tempo_value, key, row.bpm, row.beats, row.beatUnit),
            stringResource(R.string.fs_check_key_tempo_spoken, key, row.bpm, row.beats, row.beatUnit))
    }
    is SongRow.Doubtful -> pluralStringResource(R.plurals.fs_check_marked, row.count, row.count).let {
        Triple(stringResource(R.string.fs_check_notes), it, it)
    }
    is SongRow.NoPlace -> pluralStringResource(R.plurals.fs_check_no_place, row.count, row.count).let {
        Triple(stringResource(R.string.fs_check_no_place_title), it, it)
    }
}

private fun tagOf(row: SongRow): String = when (row) {
    is SongRow.Tuning -> "tuning"
    is SongRow.Octave -> "octave"
    is SongRow.ReferencePitch -> "reference"
    is SongRow.KeyAndTempo -> "key"
    is SongRow.Doubtful -> "marked"
    is SongRow.NoPlace -> "no-place"
}

/** One finding: its name and what was heard, read as one element, and its button under them. */
@Composable
private fun SongRowView(row: SongRow, change: Change?, onChange: (Change) -> Unit) {
    val c = BrasscribeTheme.colors
    val (label, shown, spoken) = rowWords(row)
    Column(
        Modifier.fillMaxWidth().padding(horizontal = BrasscribeSpace.s4, vertical = BrasscribeSpace.s3),
        verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2),
    ) {
        Column(Modifier.fillMaxWidth().testTag("fs-check-${tagOf(row)}").semantics(mergeDescendants = true) { contentDescription = "$label: $spoken" }) {
            Text(label, style = MaterialTheme.typography.bodyMedium, color = c.textMuted, modifier = Modifier.clearAndSetSemantics { })
            Text(shown, style = MaterialTheme.typography.titleMedium, color = c.text, modifier = Modifier.clearAndSetSemantics { })
        }
        if (change != null) OutlineButton(change.label, { onChange(change) }, Modifier.testTag("fs-check-change-${change.tag}"), fill = false)
    }
}

/**
 * A song's line in Your songs: "4-string bass · Drop D · 3 notes to check · Today" for a tab on this phone,
 * and where it is or where it opens for what the computer lists. Null leaves the row to the shared line
 * (a tab file opened from the phone).
 */
@Composable
fun songRowSubtitle(entry: ScoreEntry): String? {
    val tab = entry.profile == Profile.BASS_TAB.id
    val saved = entry.saved
    if (!tab && saved != null) return null
    if (!tab) return stringResource(R.string.other_product_row)
    val date = android.text.format.DateUtils.getRelativeTimeSpanString(entry.updated, System.currentTimeMillis(),
        android.text.format.DateUtils.DAY_IN_MILLIS).toString()
    if (saved == null) return listOf(stringResource(R.string.fs_song_tab), date, stringResource(R.string.on_your_computer)).joinToString(" · ")
    val library = (LocalContext.current.applicationContext as PlayApplication).container.scoreLibrary
    // Read off the main thread, and again when the song is saved again.
    val facts by produceState<SongFacts?>(null, saved.id, saved.updated) {
        value = withContext(Dispatchers.IO) { library.content(saved.id)?.let { SongFacts.of(it.musicXml, it.compositionJson) } }
    }
    val f = facts ?: return listOf(stringResource(R.string.fs_song_tab), date).joinToString(" · ")
    return listOfNotNull(
        f.strings?.let { stringResource(R.string.fs_bass_with_strings, it) } ?: stringResource(R.string.fs_song_tab),
        f.tuning?.let { tuningName(it) },
        f.toCheck.takeIf { it > 0 }?.let { pluralStringResource(R.plurals.fs_song_to_check, it, it) },
        date,
    ).joinToString(" · ")
}
