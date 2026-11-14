package no.kalli.fretscribe

import android.app.Activity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import no.kalli.scribe.design.R as DesignR
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.OnDeviceRouting
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.ui.currentLang
import no.kalli.scribe.play.ui.findActivity
import no.kalli.scribe.play.export.Exporter
import no.kalli.scribe.play.ui.ListRow
import no.kalli.scribe.play.ui.PlaySheet
import no.kalli.scribe.play.ui.PrimaryButton
import java.io.File

/** The words of a format: its name and what it is for. */
private fun words(format: TabShareFormat): Pair<Int, Int> = when (format) {
    TabShareFormat.PDF -> R.string.fs_share_pdf to R.string.fs_share_pdf_for
    TabShareFormat.GUITAR_PRO -> R.string.fs_share_gp to R.string.fs_share_gp_for
    TabShareFormat.MUSICXML -> R.string.fs_share_musicxml to R.string.fs_share_musicxml_for
    TabShareFormat.MIDI -> R.string.fs_share_midi to R.string.fs_share_midi_for
    TabShareFormat.TEXT -> R.string.fs_share_text to R.string.fs_share_text_for
    TabShareFormat.INSTRUCTIONS -> R.string.fs_share_instructions to R.string.fs_share_instructions_for
}

/**
 * [musicXml] is the page as it is shown, with the player's fixes ([fixed]: there are some, which the computer's own
 * files do not have).
 *
 * Share or print for a tab (design/brands/fretscribe/flows.md §11): Print as the one primary, and under it what the
 * tab can be shared as, one row each: a tap makes the file and opens the system's share sheet with it (which also
 * saves to Files). The phone makes the PDF, the Guitar Pro file, the MusicXML and the MIDI itself; the tab as text
 * and the playing instructions come from the computer, and their rows say so when it is not there.
 */
@Composable
internal fun TabShareSheet(vm: PlayViewModel, title: String, musicXml: String, job: String?, outputs: Set<String>, fixed: Boolean, close: () -> Unit) {
    val c = ScribeTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val exports = remember { TabExports(context.applicationContext) }
    // The computer is there when it answers now, not when it is only paired (as the pages and Check the song decide it).
    val connection by vm.connection.state.collectAsState()
    val there = vm.container.usingFixture || OnDeviceRouting.computerThere(connection)
    val engineNow = remember(job, there) { if (job != null && there) vm.container.engine() else null }
    // Read as state: the sheet's content is composed in a window of its own, and follows it when the computer comes or goes.
    val engine by rememberUpdatedState(engineNow)
    println("SHEET connection=$connection there=$there")
    val lang = currentLang()
    val legend = stringResource(R.string.fs_share_marks_note)
    val suffix = stringResource(R.string.fs_share_instructions_suffix)
    // What is being made (null: nothing), and what went wrong with the last one.
    var making by remember { mutableStateOf<TabShareFormat?>(null) }
    var printing by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    val failed = stringResource(R.string.fs_share_failed)

    fun make(format: TabShareFormat, print: Boolean, then: (File) -> Unit) {
        if (making != null) return
        making = format
        printing = print
        said = null
        scope.launch {
            try {
                then(exports.build(format, title, musicXml, job, outputs, engine, engine != null, lang, legend, suffix, fixed))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.w(PlayViewModel.TAG, "the tab could not be made as $format", e)
                said = failed
            } finally {
                making = null
            }
        }
    }

    PlaySheet(onDismiss = close, containerColor = c.bg) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).testTag("fs-share")) {
            Text(stringResource(R.string.export_title), style = MaterialTheme.typography.titleLarge, color = c.text,
                modifier = Modifier.padding(horizontal = ScribeSpace.s4).semantics { heading() })
            val fromComputer = exports.pdfFromComputer(job, outputs, engine != null, fixed)
            println("CONTENT engine=${engine != null} from=$fromComputer")
            Text(stringResource(if (fromComputer) R.string.fs_share_pdf_computer else R.string.fs_share_pdf_phone),
                style = MaterialTheme.typography.bodyMedium, color = c.textMuted,
                modifier = Modifier.padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s2).testTag("fs-share-pdf-from"))
            PrimaryButton(stringResource(R.string.fs_share_print), {
                make(TabShareFormat.PDF, print = true) { file ->
                    val activity = context.findActivity() ?: throw IllegalStateException("no activity to print from")
                    Exporter(activity, vm.container.core, false).print(activity, title.ifBlank { file.nameWithoutExtension }, file)
                }
            }, Modifier.padding(horizontal = ScribeSpace.s4).testTag("fs-share-print"), enabled = making == null, icon = DesignR.drawable.ic_bc_print)
            // What is being made, and what went wrong, are said once.
            Column(Modifier.fillMaxWidth().padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s2).semantics { liveRegion = LiveRegionMode.Polite }) {
                val now = making
                if (now != null) {
                    Text(if (printing) stringResource(R.string.fs_share_making_print) else stringResource(R.string.fs_share_making, stringResource(words(now).first)),
                        style = MaterialTheme.typography.bodyMedium, color = c.text, modifier = Modifier.testTag("fs-share-making"))
                    LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = ScribeSpace.s1), color = c.brand, trackColor = c.border)
                }
                said?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = c.text, modifier = Modifier.testTag("fs-share-said")) }
            }
            HorizontalDivider(thickness = 1.dp, color = c.border)
            Text(stringResource(R.string.fs_share_as), style = MaterialTheme.typography.titleMedium, color = c.text,
                modifier = Modifier.padding(start = ScribeSpace.s4, end = ScribeSpace.s4, top = ScribeSpace.s3).semantics { heading() })
            TabShareFormat.entries.forEach { format ->
                val (name, purpose) = words(format)
                val missing = exports.missing(format, job, outputs, engine != null, lang, fixed)
                ListRow(
                    stringResource(name),
                    { make(format, print = false) { context.startActivity(exports.shareIntent(it, format)) } },
                    Modifier.testTag("fs-share-${format.name.lowercase()}"),
                    subtitle = stringResource(when (missing) {
                        null -> purpose
                        TabShareMissing.NEEDS_COMPUTER -> R.string.fs_share_needs_computer
                        TabShareMissing.NOT_FROM_COMPUTER -> R.string.fs_share_not_from_computer
                        TabShareMissing.NOT_MADE -> R.string.fs_share_not_made
                        TabShareMissing.FIXED -> R.string.fs_share_fixed
                    }),
                    icon = DesignR.drawable.ic_bc_export, chevron = false, enabled = missing == null && making == null,
                )
            }
        }
    }
}
