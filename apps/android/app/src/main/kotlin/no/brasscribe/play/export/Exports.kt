package no.brasscribe.play.export

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import no.brasscribe.play.TranscriptionResult
import no.brasscribe.play.compositionJsonFor
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.Lang
import no.brasscribe.play.model.PartView
import no.brasscribe.play.model.TsContext
import no.brasscribe.play.model.TsSettings
import java.io.File

enum class ExportFormat(val extension: String, val mime: String) {
    MUSICXML("musicxml", "application/vnd.recordare.musicxml+xml"),
    PDF("pdf", "application/pdf"),
    MIDI("mid", "audio/midi"),
    AUDIO("mp3", "audio/mpeg"),
    TALKING_SCORE("html", "text/html"),
    BRAILLE("brf", "text/plain"),
}

/** A file ready to share or save. */
class ExportFile(val file: File, val format: ExportFormat)

/** Builds export files; engine-only formats come from the job's artifacts. */
class Exporter(private val context: Context, private val core: CoreBridge) {
    private val dir: File get() = File(context.cacheDir, "exports").apply { mkdirs() }

    fun available(r: TranscriptionResult, format: ExportFormat, midiFromScore: Boolean): Boolean = when (format) {
        ExportFormat.MUSICXML, ExportFormat.TALKING_SCORE -> true
        ExportFormat.MIDI -> midiFromScore || r.jobId != null
        ExportFormat.PDF -> r.jobId != null && "brass-band.pdf" in r.engineOutputs
        ExportFormat.AUDIO -> r.jobId != null && "brass-band.mp3" in r.engineOutputs
        // Braille music comes from the engine (music21's translator; the core does not write BRF).
        ExportFormat.BRAILLE -> r.jobId != null && (r.engineOutputs.isEmpty() || r.engineOutputs.any { it.endsWith(".brf") })
    }

    suspend fun build(r: TranscriptionResult, format: ExportFormat, engine: EngineApi?, midi: (() -> ByteArray?)?, parts: List<PartView>, lang: Lang): ExportFile {
        val base = r.composition?.title.orEmpty().ifBlank { "score" }.replace(Regex("[^\\p{L}\\p{N} ._-]"), "").trim().ifBlank { "score" }
        val bytes: ByteArray = when (format) {
            ExportFormat.MUSICXML -> r.musicXml.toByteArray()
            ExportFormat.PDF -> engine!!.pdf(r.jobId!!)
            ExportFormat.AUDIO -> engine!!.renderedAudio(r.jobId!!)
            ExportFormat.MIDI -> midi?.invoke() ?: engine!!.midi(r.jobId!!)
            ExportFormat.TALKING_SCORE -> (coreTalkingScore(r, lang) ?: talkingScoreHtml(r.composition?.title.orEmpty(), parts, lang)).toByteArray()
            ExportFormat.BRAILLE -> engine!!.braille(r.jobId!!)
        }
        val f = File(dir, "$base.${format.extension}")
        f.writeBytes(bytes)
        return ExportFile(f, format)
    }

    /** Every part of the arranged score, from the core's talking score; null without the core. */
    private fun coreTalkingScore(r: TranscriptionResult, lang: Lang): String? =
        runCatching { core.talkingScore(r.musicXml, r.compositionJsonFor(core))?.use { it.toHtml(lang, null) } }.getOrNull()

    /** The talking-score text export: a heading per part and bar, one line per event (spec §6). */
    fun talkingScoreHtml(title: String, parts: List<PartView>, lang: Lang): String = buildString {
        val esc = { s: String -> s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") }
        append("<!DOCTYPE html>\n<html lang=\"").append(if (lang == Lang.NB) "nb" else "en").append("\"><head><meta charset=\"utf-8\"><title>")
            .append(esc(title)).append("</title></head><body>\n<h1>").append(esc(title)).append("</h1>\n")
        for (p in parts) {
            append("<h2>").append(esc(if (lang == Lang.NB) p.partNameNb else p.partName)).append("</h2>\n")
            for (bar in p.bars) {
                append("<h3>").append(if (lang == Lang.NB) "Takt " else "Bar ").append(bar.number).append("</h3>\n<ul>\n")
                for (e in bar.events) {
                    // Inside a bar heading the bar is known, so every line is spoken in that bar's context.
                    val text = core.announce(e.stop, TsContext(p.partName, e.bar), TsSettings(), lang)
                    append("<li>").append(esc(text)).append("</li>\n")
                }
                append("</ul>\n")
            }
        }
        append("</body></html>\n")
    }

    /** One share sheet for several files (ACTION_SEND_MULTIPLE when more than one). */
    fun shareIntent(exports: List<ExportFile>): Intent {
        if (exports.size == 1) return shareIntent(exports[0])
        val uris = ArrayList(exports.map { FileProvider.getUriForFile(context, "${context.packageName}.exports", it.file) })
        val send = Intent(Intent.ACTION_SEND_MULTIPLE).setType("*/*").putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        send.clipData = android.content.ClipData.newRawUri(null, uris[0]).apply { uris.drop(1).forEach { addItem(android.content.ClipData.Item(it)) } }
        return Intent.createChooser(send, null)
    }

    /** Sends a PDF to the system print dialog. */
    fun print(activity: android.app.Activity, pdf: ExportFile) {
        val pm = activity.getSystemService(android.print.PrintManager::class.java) ?: return
        pm.print(pdf.file.nameWithoutExtension, PdfPrintAdapter(pdf.file), null)
    }

    /** Writes the files into a folder the user picked (Storage Access Framework tree). */
    fun saveTo(tree: android.net.Uri, exports: List<ExportFile>): Int {
        val resolver = context.contentResolver
        val dirDoc = android.provider.DocumentsContract.buildDocumentUriUsingTree(tree, android.provider.DocumentsContract.getTreeDocumentId(tree))
        var n = 0
        for (e in exports) {
            val out = android.provider.DocumentsContract.createDocument(resolver, dirDoc, e.format.mime, e.file.name) ?: continue
            resolver.openOutputStream(out)?.use { it.write(e.file.readBytes()); n++ }
        }
        return n
    }

    fun shareIntent(export: ExportFile): Intent {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.exports", export.file)
        val send = Intent(Intent.ACTION_SEND).setType(export.format.mime).putExtra(Intent.EXTRA_STREAM, uri)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        return Intent.createChooser(send, export.file.name)
    }
}

/** Prints an existing PDF file as it is. */
private class PdfPrintAdapter(private val file: File) : android.print.PrintDocumentAdapter() {
    override fun onLayout(
        oldAttributes: android.print.PrintAttributes?, newAttributes: android.print.PrintAttributes?,
        cancellationSignal: android.os.CancellationSignal?, callback: LayoutResultCallback, extras: android.os.Bundle?,
    ) {
        if (cancellationSignal?.isCanceled == true) { callback.onLayoutCancelled(); return }
        val info = android.print.PrintDocumentInfo.Builder(file.name)
            .setContentType(android.print.PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).build()
        callback.onLayoutFinished(info, true)
    }

    override fun onWrite(
        pages: Array<out android.print.PageRange>?, destination: android.os.ParcelFileDescriptor,
        cancellationSignal: android.os.CancellationSignal?, callback: WriteResultCallback,
    ) {
        runCatching {
            file.inputStream().use { input -> java.io.FileOutputStream(destination.fileDescriptor).use { input.copyTo(it) } }
        }.onSuccess { callback.onWriteFinished(arrayOf(android.print.PageRange.ALL_PAGES)) }
            .onFailure { callback.onWriteFailed(it.message) }
    }
}
