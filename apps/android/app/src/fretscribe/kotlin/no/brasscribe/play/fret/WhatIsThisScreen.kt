package no.brasscribe.play.fret

import androidx.annotation.StringRes
import androidx.compose.foundation.focusable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import no.brasscribe.play.engine.FrettedInstrument
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
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

/**
 * What "A full song" says for [instrument]: which instrument is picked out of it. For a ukulele and a
 * mandolin it also says when that works: the computer finds them where it finds a guitar, so with a guitar
 * in the song the tab would hold both.
 */
@StringRes
internal fun songWords(instrument: Instrument): Int = when (instrument) {
    Instrument.GUITAR -> R.string.fs_what_song_desc_guitar
    Instrument.BASS -> R.string.fs_what_song_desc
    Instrument.UKULELE -> R.string.fs_what_song_desc_ukulele
    Instrument.MANDOLIN -> R.string.fs_what_song_desc_mandolin
}

/** Why this computer cannot write a tab for [kind]: its Fretscribe is from before that instrument. Said before anything is sent. */
@StringRes
internal fun tooOldWords(kind: FrettedInstrument?): Int = when (kind?.let(Instrument::of)) {
    Instrument.GUITAR -> R.string.fs_too_old_guitar
    Instrument.UKULELE -> R.string.fs_too_old_ukulele
    Instrument.MANDOLIN -> R.string.fs_too_old_mandolin
    else -> R.string.error_core_missing
}

/**
 * Asks the computer in use which profiles it has: when the screen opens, and whenever the computer comes, goes
 * or is another one ([there]). The answer is [ComputerProfiles.answer]: while it is asked nothing is known, and a
 * failed request leaves the list unknown, which sends a bass under the id every computer has.
 */
@Composable
internal fun computerProfiles(vm: PlayViewModel, there: Boolean): ComputerProfiles.Answer? {
    val container = vm.container
    // The computer's own id, so another computer is asked afresh. (A test's fixture computer is its source.)
    val computer = if (!there) null else if (container.usingFixture) "fixture-${System.identityHashCode(container.fixtureSource)}"
        else container.settings.serverId ?: container.settings.url
    LaunchedEffect(computer) {
        if (computer == null) { ComputerProfiles.clear(); return@LaunchedEffect }
        // This computer has already said what it has: the next screen need not ask it again. Another computer,
        // or one that could not be asked, is asked, and until it answers nothing is known.
        if (ComputerProfiles.answer?.let { it.computer == computer && !it.asking && it.listed != null } == true) return@LaunchedEffect
        ComputerProfiles.asking(computer)
        val listed = withContext(Dispatchers.IO) { runCatching { container.engine()?.profiles()?.map { it.name }?.toSet() }.getOrNull() }
        ComputerProfiles.answered(computer, listed)
    }
    // Until the effect has run, an answer for another computer is not this one's.
    return ComputerProfiles.answer?.takeIf { it.computer == computer } ?: computer?.let { ComputerProfiles.Answer(it, asking = true, listed = null) }
}

/**
 * "What is this?" (design/fretscribe/flows.md §5): the instrument alone, or a full song it is picked out
 * of. For a guitar or a bass nothing is chosen until the player chooses; a ukulele or a mandolin starts on
 * the instrument alone, as the computer takes it, and A full song says when it works. The answer stays
 * with the recording. In this version the computer writes down the notes for both, so the row under the
 * choices says whether it is there, with the way to connect it when it is not.
 */
@Composable
fun WhatIsThisScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val source by vm.source.collectAsState()
    val connection by vm.connection.state.collectAsState()
    val context = LocalContext.current
    // The player's instrument as it is now: it is what the recording will be written down for.
    val mine = remember { yourInstrumentStore(context).load() }
    val given = SongAnswers.of(source)
    val answer = if (given.recording != null) given else given.copy(recording = startingAnswer(mine))
    val choices = listOf(
        Answer(Recording.INSTRUMENT, "instrument", R.string.fs_what_instrument, R.string.fs_what_instrument_desc),
        Answer(Recording.SONG, "song", R.string.fs_what_song, songWords(mine.instrument)),
    )
    // The fixture engine of the UI tests is always there.
    val there = vm.container.usingFixture || OnDeviceRouting.computerThere(connection)
    // The recording is sent from its file: without it there is nothing to continue with.
    val inHand = source?.file?.isFile == true
    // What this computer's Fretscribe can write: one from before the guitar still writes a bass, and nothing else.
    val asked = computerProfiles(vm, there)
    // Nothing is sent until the computer has said what it can write, or could not be asked.
    val asking = there && asked?.asking != false
    val tooOld = there && !asking && tabProfile(mine.kind, asked?.listed) == null
    val headingFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { headingFocus.requestFocus() } }

    PlayScaffold(
        title = source?.let { s -> if (s.durationS > 0) "${s.name} · ${clock(s.durationS)}" else s.name },
        onBack = vm::back, backLabel = stringResource(R.string.home), status = status,
        bottom = {
            // One line says what is still missing; the computer comes first, since the row above has its button.
            val missing = when {
                !inHand -> R.string.fs_what_no_recording
                !there -> R.string.fs_what_connect_first
                asking -> R.string.fs_what_asking
                tooOld -> tooOldWords(mine.kind)
                answer.recording == null -> R.string.profile_choose_one
                else -> null
            }
            val why = missing?.let { stringResource(it) }
            // The line can change while the screen is open (the computer answers): a screen reader is told, without interrupting.
            if (why != null) Text(why, Modifier.testTag("fs-what-missing").semantics { liveRegion = LiveRegionMode.Polite },
                style = MaterialTheme.typography.bodyMedium, color = BrasscribeTheme.colors.textMuted)
            PrimaryButton(stringResource(R.string.continue_label), {
                // From here the recording is written down afresh, for the player's instrument as it is now.
                SongAnswers.set(source, SongAnswer(answer.recording))
                vm.chooseProfile(Profile.TAB)
                vm.startTranscription()
                // The button says why it can't be pressed: "Continue, disabled" alone leaves that out.
            }, Modifier.testTag("fs-what-continue").then(if (why != null) Modifier.semantics { stateDescription = why } else Modifier),
                enabled = inHand && there && !asking && !tooOld && answer.recording != null)
        },
    ) {
        ScreenTitle(stringResource(R.string.profile_title), Modifier.focusRequester(headingFocus).focusable())
        Lead(stringResource(R.string.fs_what_hint))
        ChoiceGroup(choices.size) {
            choices.forEachIndexed { i, c ->
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
