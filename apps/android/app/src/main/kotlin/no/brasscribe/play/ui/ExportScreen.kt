package no.brasscribe.play.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.R
import no.brasscribe.play.export.ExportFile
import no.brasscribe.play.export.ExportFormat
import no.brasscribe.play.export.Exporter
import no.brasscribe.play.ui.theme.LocalPlayTokens

private val LABELS = mapOf(
    ExportFormat.MUSICXML to R.string.export_musicxml_score, ExportFormat.PDF to R.string.export_pdf,
    ExportFormat.MIDI to R.string.export_midi, ExportFormat.AUDIO to R.string.export_audio,
    ExportFormat.TALKING_SCORE to R.string.export_talking, ExportFormat.BRAILLE to R.string.export_braille,
)

@Composable
fun ExportScreen(vm: PlayViewModel) {
    val context = LocalContext.current
    val status by vm.status.collectAsState()
    val result by vm.result.collectAsState()
    val checked by vm.checked.collectAsState()
    val r = result ?: return
    val t = LocalPlayTokens.current
    val scope = rememberCoroutineScope()
    val exporter = remember { Exporter(context, vm.container.core) }
    var pendingSave by remember { mutableStateOf<ExportFile?>(null) }
    val midiFromScore = vm.scoreController != null

    val save = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri: Uri? ->
        val f = pendingSave ?: return@rememberLauncherForActivityResult
        if (uri != null) scope.launch {
            withContext(Dispatchers.IO) { context.contentResolver.openOutputStream(uri)?.use { it.write(f.file.readBytes()) } }
            vm.say(R.string.exported, f.file.name)
        }
        pendingSave = null
    }

    fun make(format: ExportFormat, then: (ExportFile) -> Unit) = scope.launch {
        try {
            val comp = r.composition
            val parts = comp?.voices.orEmpty().filter { it.notes.isNotEmpty() }
                .map { partViewFor(comp!!, it.id, checked[it.id].orEmpty(), vm.container.core) }
            val f = withContext(Dispatchers.Default) {
                exporter.build(r, format, vm.container.engine(), vm.scoreController?.let { c -> { c.midiBytes() } }, parts, currentLang())
            }
            vm.say(R.string.exported, f.file.name)
            then(f)
        } catch (e: Exception) {
            vm.say(R.string.export_failed, e.message ?: e.javaClass.simpleName)
        }
    }

    PlayScaffold(title = stringResource(R.string.export_title), onBack = vm::back, status = status) {
        Heading(stringResource(R.string.export_title))
        ExportFormat.entries.forEach { format ->
            val ok = exporter.available(r, format, midiFromScore)
            Column(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                SubHeading(stringResource(LABELS.getValue(format)))
                if (ok) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { make(format) { context.startActivity(exporter.shareIntent(it)) } }, modifier = Modifier.heightIn(min = 48.dp)) {
                            Text(stringResource(R.string.export_share))
                        }
                        OutlinedButton(onClick = { make(format) { pendingSave = it; save.launch(it.file.name) } }, modifier = Modifier.heightIn(min = 48.dp)) {
                            Text(stringResource(R.string.export_save))
                        }
                    }
                } else {
                    Text(
                        stringResource(if (format == ExportFormat.BRAILLE) R.string.export_braille_unavailable else R.string.export_needs_engine),
                        color = t.textMuted, style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
    }
}
