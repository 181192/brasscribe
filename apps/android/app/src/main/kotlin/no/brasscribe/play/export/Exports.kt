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

/** What Share or print makes: the player's own part, one file per player, or the conductor's score. */
enum class ExportScope { MY_PART, EVERY_PART, CONDUCTOR }

/** A file ready to share or save. */
class ExportFile(val file: File, val format: ExportFormat)

/** Builds export files; engine-only formats come from the job's artifacts. */
class Exporter(private val context: Context, private val core: CoreBridge) {
    private val dir: File get() = File(context.cacheDir, "exports").apply { mkdirs() }

    fun available(r: TranscriptionResult, format: ExportFormat, midiFromScore: Boolean): Boolean = when (format) {
        ExportFormat.MUSICXML, ExportFormat.TALKING_SCORE -> true
        ExportFormat.MIDI -> midiFromScore || r.jobId != null
        // The engine's files show the score as it made it; after a change on the phone they are stale.
        ExportFormat.PDF -> r.jobId != null && "brass-band.pdf" in r.engineOutputs && !r.changedOnPhone
        ExportFormat.AUDIO -> r.jobId != null && "brass-band.mp3" in r.engineOutputs && !r.changedOnPhone
        // Braille music comes from the engine (music21's translator; the core does not write BRF).
        ExportFormat.BRAILLE -> r.jobId != null && (r.engineOutputs.isEmpty() || r.engineOutputs.any { it.endsWith(".brf") }) && !r.changedOnPhone
    }

    /** Whether [format] can be made for single parts (audio and MIDI are always the whole score). */
    fun perPart(r: TranscriptionResult, format: ExportFormat): Boolean = when (format) {
        ExportFormat.MUSICXML, ExportFormat.TALKING_SCORE, ExportFormat.BRAILLE -> true
        ExportFormat.PDF -> r.engineOutputs.any { it.startsWith("parts/") && it.endsWith(".pdf") }
        ExportFormat.AUDIO, ExportFormat.MIDI -> false
    }

    /** The engine's file for part [index] (0-based): parts/NN-Name.ext, numbered in score order. */
    private fun partFile(r: TranscriptionResult, index: Int, ext: String): String? {
        val prefix = "parts/%02d-".format(index + 1)
        return r.engineOutputs.firstOrNull { it.startsWith(prefix) && it.endsWith(".$ext") }
    }

    private fun safe(s: String) = s.replace(Regex("[^\\p{L}\\p{N} ._-]"), "").trim()

    /**
     * Every file of [formats] for [scope]: one per part for Every part, the shown part for My part,
     * the full score for the conductor. Audio and MIDI are always the whole score.
     */
    suspend fun buildAll(
        r: TranscriptionResult, formats: List<ExportFormat>, scope: ExportScope, myPart: Int, partNames: List<String>,
        engine: EngineApi?, midi: (() -> ByteArray?)?, parts: List<PartView>, lang: Lang,
    ): List<ExportFile> {
        val targets: List<Int?> = when (scope) {
            ExportScope.CONDUCTOR -> listOf(null)
            ExportScope.MY_PART -> listOf(myPart.takeIf { partNames.isNotEmpty() })
            ExportScope.EVERY_PART -> partNames.indices.toList().ifEmpty { listOf(null) }
        }
        val out = ArrayList<ExportFile>()
        for (format in formats) {
            if (format == ExportFormat.AUDIO || format == ExportFormat.MIDI || !perPart(r, format)) {
                out += build(r, format, engine, midi, parts, lang)
                continue
            }
            for (t in targets) out += if (t == null) build(r, format, engine, midi, parts, lang) else buildPart(r, format, t, partNames[t], engine, lang)
        }
        return out
    }

    private suspend fun buildPart(r: TranscriptionResult, format: ExportFormat, index: Int, name: String, engine: EngineApi?, lang: Lang): ExportFile {
        val base = safe(r.composition?.title.orEmpty()).ifBlank { "score" }
        val bytes: ByteArray = when (format) {
            ExportFormat.PDF -> engine!!.artifact(r.jobId!!, partFile(r, index, "pdf") ?: error("no PDF for $name"))
            ExportFormat.BRAILLE -> engine!!.braille(r.jobId!!, (index + 1).toString())
            ExportFormat.MUSICXML -> no.brasscribe.play.model.MusicXmlParts.single(r.musicXml, index).toByteArray()
            ExportFormat.TALKING_SCORE -> (runCatching {
                core.talkingScore(r.musicXml, r.compositionJsonFor(core))?.use { it.toHtml(lang, listOf(index)) }
            }.getOrNull() ?: error("no talking score")).toByteArray()
            else -> error("$format is whole-score only")
        }
        val f = File(dir, "$base - ${safe(name)}.${format.extension}")
        f.writeBytes(bytes)
        return ExportFile(f, format)
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
            resolver.openOutputStream(out)?.use { o -> e.file.inputStream().use { it.copyTo(o, 1 shl 16) }; n++ }
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
