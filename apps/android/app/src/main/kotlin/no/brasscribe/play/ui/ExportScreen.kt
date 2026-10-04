package no.brasscribe.play.ui

import android.app.Activity
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.foundation.selection.toggleable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.Lineup
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.lineup
import no.brasscribe.play.R
import no.brasscribe.play.export.ExportFile
import no.brasscribe.play.export.ExportFormat
import no.brasscribe.play.export.ExportScope
import no.brasscribe.play.export.Exporter

private val LABELS = mapOf(
    ExportFormat.PDF to (R.string.export_pdf to R.string.export_pdf_desc),
    ExportFormat.MUSICXML to (R.string.export_musicxml_score to R.string.export_musicxml_desc),
    ExportFormat.AUDIO to (R.string.export_audio to R.string.export_audio_desc),
    ExportFormat.MIDI to (R.string.export_midi to R.string.export_midi_desc),
    ExportFormat.TALKING_SCORE to (R.string.export_talking to R.string.export_talking_desc),
    ExportFormat.BRAILLE to (R.string.export_braille to R.string.export_braille_desc),
)

/**
 * Share or print (the usability review's P1: not "Export"): the formats as a checklist, PDF only by
 * default, and Print as the one primary when a PDF is chosen; Share and Save to Files otherwise.
 */
@Composable
fun ExportScreen(vm: PlayViewModel) {
    val context = LocalContext.current
    val status by vm.status.collectAsState()
    val result by vm.result.collectAsState()
    val source by vm.source.collectAsState()
    val checked by vm.checked.collectAsState()
    val r = result ?: return
    val c = BrasscribeTheme.colors
    val scope = rememberCoroutineScope()
    val exporter = remember { Exporter(context, vm.container.core) }
    val scoreMidi = remember { vm.scoreController?.midiSource() ?: vm.scoreMidi }
    val midiFromScore = scoreMidi != null
    val order = LABELS.keys.toList()
    val available = order.filter { exporter.available(r, it, midiFromScore) }
    var chosen by rememberSaveable { mutableStateOf(setOf(if (ExportFormat.PDF in available) ExportFormat.PDF else ExportFormat.MUSICXML).map { it.name }.toSet()) }
    val formats = order.filter { it.name in chosen && it in available }
    var pendingSave by remember { mutableStateOf<List<ExportFile>>(emptyList()) }
    // What: the player's own part first (the part on screen), every part, or the conductor's score.
    val partNames = remember(r.musicXml) { no.brasscribe.play.model.MusicXmlParts.names(r.musicXml) }
    // The labels follow the recorded lineup: a quartet has no conductor, so its third choice is the score.
    val lineup = r.lineup ?: Lineup.ofParts(partNames)
    // Your part: this score's pick, else the seat's part. With none of your own, Every part is the default.
    val myPart = remember(partNames, r) { vm.yourPart(partNames, r).index }
    val manyParts = partNames.size > 1
    var what by rememberSaveable { mutableStateOf(if (!manyParts) ExportScope.CONDUCTOR else if (myPart != null) ExportScope.MY_PART else ExportScope.EVERY_PART) }
    val myName = myPart?.let { PartNames.display(partNames.getOrElse(it) { "" }) }
    val fileCount = formats.sumOf { f ->
        if (f == ExportFormat.AUDIO || f == ExportFormat.MIDI || !exporter.perPart(r, f) || what != ExportScope.EVERY_PART) 1 else partNames.size
    }

    val saveTree = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri: Uri? ->
        val files = pendingSave
        if (uri != null && files.isNotEmpty()) scope.launch {
            val n = withContext(Dispatchers.IO) { exporter.saveTo(uri, files) }
            vm.say(R.string.exported_files, n)
        }
        pendingSave = emptyList()
    }

    // The phone lays out its PDFs part by part (Every part: some 25): how far it is, while it works.
    var laying by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    var making by remember { mutableStateOf(false) }
    fun make(then: (List<ExportFile>) -> Unit) = scope.launch {
        if (making) return@launch
        making = true
        try {
            val comp = r.composition
            val parts = comp?.voices.orEmpty().filter { it.notes.isNotEmpty() }.map { partViewFor(comp!!, it.id, checked[it.id].orEmpty(), vm.container.core) }
            val phonePdf = ExportFormat.PDF in formats && !exporter.pdfFromComputer(r)
            // Said once: the progress line under the buttons is not said part by part.
            if (phonePdf) vm.say(R.string.stage_export)
            val files = withContext(Dispatchers.Default) {
                exporter.buildAll(r, formats, what, myPart ?: 0, partNames, vm.container.engine(), scoreMidi?.let { m -> { m.bytes() } }, parts, currentLang(),
                    progress = { done, of -> if (phonePdf) laying = done to of })
            }
            vm.say(R.string.exported, files.joinToString { it.file.nameWithoutExtension })
            then(files)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            android.util.Log.w(no.brasscribe.play.PlayViewModel.TAG, "export failed", e)
            vm.say(R.string.export_failed, e.message ?: e.javaClass.simpleName)
        } finally {
            laying = null
            making = false
        }
    }

    val print = ExportFormat.PDF in formats
    val sideways = androidx.compose.ui.platform.LocalConfiguration.current.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
    PlayScaffold(
        title = null, onBack = vm::back, backLabel = stringResource(R.string.back), status = status,
        bottom = {
            laying?.let { (done, of) ->
                androidx.compose.material3.LinearProgressIndicator({ if (of == 0) 0f else done.toFloat() / of }, Modifier.fillMaxWidth(), color = c.brass, trackColor = c.border)
                // Not a live region: Every part would be said some 25 times. Its end is said (exported).
                Text(stringResource(R.string.export_laying_out, minOf(done + 1, of), of), style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.semantics { testTag = "export-progress" })
            }
            val printButton = @Composable { m: Modifier -> PrimaryButton(stringResource(R.string.export_print), {
                // Every part: one print job, the players' PDFs one after another.
                make { files ->
                    scope.launch {
                        try {
                            val jobs = exporter.printJobs(files.filter { it.format == ExportFormat.PDF }, r.composition?.title.orEmpty())
                            jobs.forEach { (name, file) -> exporter.print(context as Activity, name, file) }
                        } catch (e: kotlinx.coroutines.CancellationException) {
                            throw e
                        } catch (e: Exception) {
                            vm.say(R.string.export_failed, e.message ?: e.javaClass.simpleName)
                        }
                    }
                }
            }, icon = R.drawable.ic_bc_print, modifier = m.semantics { testTag = "print" }, enabled = !making) }
            val share = stringResource(R.string.export_share)
            val save = stringResource(R.string.export_save)
            val shareAction = { make { context.startActivity(exporter.shareIntent(it)) } }
            val shareAndSave = @Composable { m: Modifier ->
                if (print) SecondaryButton(share, { shareAction() }, m.semantics { testTag = "share" }, enabled = formats.isNotEmpty() && !making, icon = R.drawable.ic_bc_export)
                else PrimaryButton(share, { shareAction() }, m.semantics { testTag = "share" }, enabled = formats.isNotEmpty() && !making, icon = R.drawable.ic_bc_export)
                OutlineButton(save, { make { pendingSave = it; saveTree.launch(null) } }, m, enabled = formats.isNotEmpty() && !making, icon = R.drawable.ic_bc_folder)
            }
            // On its side the phone has little height: the buttons in one row, so the list keeps the room.
            if (sideways) Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                if (print) printButton(Modifier.weight(1f))
                shareAndSave(Modifier.weight(1f))
            } else {
                if (print) printButton(Modifier)
                Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) { shareAndSave(Modifier.weight(1f)) }
            }
            Text(
                pluralStringResource(R.plurals.export_count, fileCount, fileCount),
                style = MaterialTheme.typography.bodySmall, color = c.textMuted,
            )
        },
    ) {
        ScreenTitle(stringResource(R.string.export_title))
        if (manyParts) {
            SectionLabel(stringResource(R.string.export_what))
            ChoiceGroup(if (myName != null) 3 else 2) {
                if (myName != null) ChoiceCard(stringResource(R.string.export_scope_my_part, myName), null, what == ExportScope.MY_PART, true, 0) { what = ExportScope.MY_PART }
                ChoiceCard(stringResource(R.string.export_scope_every_part), stringResource(R.string.export_scope_every_part_tip),
                    what == ExportScope.EVERY_PART, true, if (myName != null) 1 else 0) { what = ExportScope.EVERY_PART }
                ChoiceCard(stringResource(if (lineup == Lineup.QUARTET) R.string.export_scope_score_quartet else R.string.export_scope_conductor), null, what == ExportScope.CONDUCTOR, true, if (myName != null) 2 else 1) { what = ExportScope.CONDUCTOR }
            }
        }
        SectionLabel(stringResource(R.string.export_formats))
        RowGroup {
            order.forEachIndexed { i, f ->
                if (i > 0) RowDivider()
                val ok = f in available
                val (label, desc) = LABELS.getValue(f)
                val on = f.name in chosen && ok
                val wholeOnly = manyParts && what != ExportScope.CONDUCTOR && ok && !exporter.perPart(r, f)
                ListRow(
                    stringResource(label),
                    onClick = null,
                    subtitle = when {
                        // Which PDF it is, the computer's or the phone's, and why (in an app that lays out its own).
                        f == ExportFormat.PDF && ok && no.brasscribe.play.Product.PHONE_PDF && !wholeOnly -> stringResource(when {
                            exporter.pdfFromComputer(r) -> R.string.export_pdf_computer
                            r.changedOnPhone && r.jobId != null && "brass-band.pdf" in r.engineOutputs -> R.string.export_pdf_phone_changed
                            else -> R.string.export_pdf_phone
                        })
                        !ok && r.changedOnPhone && f != ExportFormat.MIDI -> stringResource(R.string.export_made_before_change)
                        !ok -> stringResource(if (f == ExportFormat.BRAILLE) R.string.export_braille_unavailable else R.string.export_needs_engine)
                        wholeOnly -> stringResource(R.string.export_whole_score_only, stringResource(desc))
                        else -> stringResource(desc)
                    },
                    enabled = ok,
                    chevron = false,
                    modifier = Modifier.toggleable(on, enabled = ok, role = Role.Checkbox) { v -> chosen = if (v) chosen + f.name else chosen - f.name },
                    trailing = {
                        Checkbox(on, null, enabled = ok, colors = CheckboxDefaults.colors(checkedColor = c.primary, checkmarkColor = c.onPrimary, uncheckedColor = c.borderStrong))
                    },
                )
            }
        }
        InfoNote(stringResource(R.string.export_marks_note), boxed = false)
    }
}
