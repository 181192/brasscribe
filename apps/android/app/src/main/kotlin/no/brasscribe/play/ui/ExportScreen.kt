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
    val shown = scoreMidi?.shown
    // The labels follow the recorded lineup: a quartet has no conductor, so its third choice is the score.
    val lineup = r.lineup ?: Lineup.ofParts(partNames)
    val myPart = shown?.singleOrNull() ?: defaultPart(partNames, lineup)
    val manyParts = partNames.size > 1
    var what by rememberSaveable { mutableStateOf(if (manyParts) ExportScope.MY_PART else ExportScope.CONDUCTOR) }
    val myName = PartNames.display(partNames.getOrElse(myPart) { "" })
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

    fun make(then: (List<ExportFile>) -> Unit) = scope.launch {
        try {
            val comp = r.composition
            val parts = comp?.voices.orEmpty().filter { it.notes.isNotEmpty() }.map { partViewFor(comp!!, it.id, checked[it.id].orEmpty(), vm.container.core) }
            val files = withContext(Dispatchers.Default) {
                exporter.buildAll(r, formats, what, myPart, partNames, vm.container.engine(), scoreMidi?.let { m -> { m.bytes() } }, parts, currentLang())
            }
            vm.say(R.string.exported, files.joinToString { it.file.nameWithoutExtension })
            then(files)
        } catch (e: Exception) {
            vm.say(R.string.export_failed, e.message ?: e.javaClass.simpleName)
        }
    }

    val print = ExportFormat.PDF in formats
    PlayScaffold(
        title = null, onBack = vm::back, backLabel = stringResource(R.string.back), status = status,
        bottom = {
            if (print) PrimaryButton(stringResource(R.string.export_print), {
                // Every part: one print job per player's PDF, as on Windows.
                make { files -> files.filter { it.format == ExportFormat.PDF }.forEach { exporter.print(context as Activity, it) } }
            }, icon = R.drawable.ic_bc_print, modifier = Modifier.semantics { testTag = "print" })
            Row(horizontalArrangement = Arrangement.spacedBy(BrasscribeSpace.s3)) {
                val share = stringResource(R.string.export_share)
                val save = stringResource(R.string.export_save)
                val shareAction = { make { context.startActivity(exporter.shareIntent(it)) } }
                if (print) SecondaryButton(share, { shareAction() }, Modifier.weight(1f).semantics { testTag = "share" }, enabled = formats.isNotEmpty(), icon = R.drawable.ic_bc_export)
                else PrimaryButton(share, { shareAction() }, Modifier.weight(1f).semantics { testTag = "share" }, enabled = formats.isNotEmpty(), icon = R.drawable.ic_bc_export)
                OutlineButton(save, { make { pendingSave = it; saveTree.launch(null) } }, Modifier.weight(1f), enabled = formats.isNotEmpty(), icon = R.drawable.ic_bc_folder)
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
            ChoiceGroup(3) {
                ChoiceCard(stringResource(R.string.export_scope_my_part, myName), null, what == ExportScope.MY_PART, true, 0) { what = ExportScope.MY_PART }
                ChoiceCard(stringResource(R.string.export_scope_every_part), stringResource(R.string.export_scope_every_part_tip),
                    what == ExportScope.EVERY_PART, true, 1) { what = ExportScope.EVERY_PART }
                ChoiceCard(stringResource(if (lineup == Lineup.QUARTET) R.string.export_scope_score_quartet else R.string.export_scope_conductor), null, what == ExportScope.CONDUCTOR, true, 2) { what = ExportScope.CONDUCTOR }
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
