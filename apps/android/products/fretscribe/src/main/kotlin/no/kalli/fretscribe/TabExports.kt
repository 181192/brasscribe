package no.kalli.fretscribe

import alphaTab.Settings
import alphaTab.TabRhythmMode
import alphaTab.exporter.Gp7Exporter
import alphaTab.midi.AlphaSynthMidiFileHandler
import alphaTab.midi.MidiFile
import alphaTab.midi.MidiFileGenerator
import alphaTab.model.Score
import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import no.kalli.scribe.engine.EngineApi
import no.kalli.scribe.model.Lang
import no.kalli.scribe.score.AlphaTabMusicXml
import no.kalli.scribe.score.export.PhonePdf
import java.io.File

/** What a tab can be shared as, in the order Share or print lists them. */
enum class TabShareFormat(val extension: String, val mime: String) {
    PDF("pdf", "application/pdf"),
    /** Guitar Pro 7 and later (.gp): strings, frets and rhythm, to go on editing there. */
    GUITAR_PRO("gp", "application/octet-stream"),
    MUSICXML("musicxml", "application/vnd.recordare.musicxml+xml"),
    MIDI("mid", "audio/midi"),
    /** The tab drawn with letters and dashes, to paste anywhere. */
    TEXT("txt", "text/plain"),
    /** What to play in words, for a screen reader or a braille display. */
    INSTRUCTIONS("txt", "text/plain"),
}

/** Why a format can't be had now. */
enum class TabShareMissing {
    /** The computer writes it, and it is not connected. */
    NEEDS_COMPUTER,
    /** The song did not come from a computer (it was opened from a file). */
    NOT_FROM_COMPUTER,
    /** The computer did not write it for this song. */
    NOT_MADE,
    /** The player fixed notes on the phone since: the computer's file does not have the fixes. */
    FIXED,
}

/**
 * The files of Share or print for a tab. The phone makes most of them itself from the tab's MusicXML, so they can be
 * had away from the computer: the MusicXML as it is, the Guitar Pro file and the MIDI through alphaTab, and the PDF
 * when the computer's own is out of reach (laid out by alphaTab, [PhonePdf]). The tab as text and the playing
 * instructions are written by the core on the computer, and are fetched from it.
 */
class TabExports(private val context: Context) {
    private val dir: File get() = File(context.cacheDir, "exports").apply { mkdirs() }

    /** Why [format] can't be had for the song of [job] (null: not from a computer) that wrote [outputs], with the computer there or not; null when it can. */
    fun missing(format: TabShareFormat, job: String?, outputs: Set<String>, connected: Boolean, lang: Lang, fixed: Boolean = false): TabShareMissing? = when (format) {
        TabShareFormat.PDF, TabShareFormat.GUITAR_PRO, TabShareFormat.MUSICXML, TabShareFormat.MIDI -> null
        TabShareFormat.TEXT, TabShareFormat.INSTRUCTIONS -> when {
            job == null -> TabShareMissing.NOT_FROM_COMPUTER
            fixed -> TabShareMissing.FIXED
            !connected -> TabShareMissing.NEEDS_COMPUTER
            // (A computer that does not say what it wrote is asked all the same.)
            outputs.isNotEmpty() && artifact(format, lang) !in outputs -> TabShareMissing.NOT_MADE
            else -> null
        }
    }

    /** The computer's PDF is used: it wrote one and can be asked for it. Else the phone lays the pages out. */
    fun pdfFromComputer(job: String?, outputs: Set<String>, connected: Boolean, fixed: Boolean = false): Boolean =
        job != null && connected && !fixed && TAB_PDF in outputs

    private fun artifact(format: TabShareFormat, lang: Lang): String =
        if (format == TabShareFormat.TEXT) "tab.txt" else "tab-instructions.${if (lang == Lang.NB) "nb" else "en"}.txt"

    private fun safe(s: String) = s.replace(Regex("[^\\p{L}\\p{N} ._-]"), "").trim()

    /**
     * The file of [format] for the tab [musicXml] of the song [title]; [suffix] is added to the name of the playing
     * instructions (they and the text tab are both .txt). [connected]: the computer answers now. The computer's PDF
     * is used when it wrote one and answers; when asking for it fails, the phone lays the pages out after all.
     * Throws what the computer or alphaTab throws.
     */
    suspend fun build(format: TabShareFormat, title: String, musicXml: String, job: String?, outputs: Set<String>, engine: EngineApi?, connected: Boolean,
                      lang: Lang, legend: String, suffix: String, fixed: Boolean = false): File = withContext(Dispatchers.IO) {
        val base = safe(title).ifBlank { "tab" }
        val name = if (format == TabShareFormat.INSTRUCTIONS) "$base $suffix" else base
        val file = File(dir, "$name.${format.extension}")
        val bytes: ByteArray? = when (format) {
            TabShareFormat.MUSICXML -> musicXml.toByteArray()
            TabShareFormat.GUITAR_PRO -> guitarPro(musicXml)
            TabShareFormat.MIDI -> midi(musicXml)
            TabShareFormat.TEXT, TabShareFormat.INSTRUCTIONS -> {
                if (engine == null || job == null || !connected || fixed) throw IllegalStateException("$format needs the computer's, without fixes")
                engine.artifact(job, artifact(format, lang))
            }
            TabShareFormat.PDF -> {
                val computers = if (engine != null && job != null && pdfFromComputer(job, outputs, connected, fixed)) {
                    try {
                        engine.pdf(job)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        android.util.Log.w(TAG, "the computer's PDF could not be had: the phone lays it out", e)
                        null
                    }
                } else null
                computers ?: run { file.outputStream().use { phonePdf(musicXml, title, legend, it) }; null }
            }
        }
        if (bytes != null) file.writeBytes(bytes)
        file
    }

    private fun score(musicXml: String, settings: Settings): Score = AlphaTabMusicXml.parse(musicXml.toByteArray(), settings)

    /** The tab as a Guitar Pro file, written by alphaTab's own exporter from what it reads of the MusicXML. */
    fun guitarPro(musicXml: String): ByteArray = wholeZip(alphaTabsGuitarPro(musicXml))

    /** The Guitar Pro file as alphaTab writes it, before [wholeZip]. */
    internal fun alphaTabsGuitarPro(musicXml: String): ByteArray {
        val settings = Settings()
        return Gp7Exporter().export(score(musicXml, settings), settings).buffer.asByteArray()
    }

    /** The tab as a MIDI file, as alphaTab would play it. */
    fun midi(musicXml: String): ByteArray {
        val settings = Settings()
        val file = MidiFile()
        MidiFileGenerator(score(musicXml, settings), settings, AlphaSynthMidiFileHandler(file, true)).generate()
        return file.toBinary().buffer.asByteArray()
    }

    /** The tab on A4 pages, laid out on the phone: the song's name over it, the "?" marks as the tab has them. */
    fun phonePdf(musicXml: String, title: String, legend: String, out: java.io.OutputStream) {
        val pdf = PhonePdf(context, legend) {
            notation.rhythmMode = TabRhythmMode.ShowWithBars
            // The words over the first bar say the tuning, the strings and the capo.
            notation.elements.set(alphaTab.NotationElement.GuitarTuning, false)
        }
        val score = pdf.parse(musicXml.toByteArray())
        if (title.isNotBlank()) score.title = title
        val tab = pdf.engrave(score, (0 until score.tracks.length.toInt()).toList(), null, PhonePdf.PART_SCALE)
        pdf.Document().use { doc -> doc.add(tab); doc.writeTo(out) }
    }

    /** The system's share sheet for [file]. */
    fun shareIntent(file: File, format: TabShareFormat): Intent {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.exports", file)
        val send = Intent(Intent.ACTION_SEND).setType(format.mime).putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        return Intent.createChooser(send, file.name)
    }

    companion object {
        const val TAB_PDF = "tab.pdf"

        private const val TAG = "TabExports"

        /** The most files, and the most bytes in one file and in all of them, [wholeZip] takes from a zip. */
        const val ZIP_MAX_ENTRIES = 256
        const val ZIP_MAX_BYTES = 64L * 1024 * 1024

        /**
         * The zip file [zip] written again with every file's checksum as its content has it. alphaTab 1.8.4 for Android
         * writes checksums into a Guitar Pro file that do not match its content: alphaTab reads it back all the same, but
         * a program that checks them refuses the file. The files are read by the directory at the end, without the check.
         * Every offset and size is checked against the file, and at most [ZIP_MAX_ENTRIES] files of at most
         * [ZIP_MAX_BYTES] in all are taken: anything else is refused with a [java.util.zip.ZipException].
         */
        fun wholeZip(zip: ByteArray): ByteArray {
            fun refuse(why: String): Nothing = throw java.util.zip.ZipException(why)
            val b = java.nio.ByteBuffer.wrap(zip).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            fun u16(at: Long): Int { if (at < 0 || at + 2 > zip.size) refuse("cut short"); return b.getShort(at.toInt()).toInt() and 0xFFFF }
            fun u32(at: Long): Long { if (at < 0 || at + 4 > zip.size) refuse("cut short"); return b.getInt(at.toInt()).toLong() and 0xFFFFFFFFL }
            // The end record: its signature, searched for from the end (a comment may follow it).
            val end = (zip.size - 22 downTo 0).firstOrNull { b.getInt(it) == 0x06054b50 }?.toLong() ?: refuse("not a zip file")
            val count = u16(end + 10)
            if (count > ZIP_MAX_ENTRIES) refuse("$count files")
            var at = u32(end + 16)
            var total = 0L
            val out = java.io.ByteArrayOutputStream()
            java.util.zip.ZipOutputStream(out).use { whole ->
                repeat(count) {
                    if (at + 46 > end || u32(at) != 0x02014b50L) refuse("not a zip directory")
                    val method = u16(at + 10)
                    val packed = u32(at + 20)
                    val size = u32(at + 24)
                    val nameLength = u16(at + 28)
                    val skip = u16(at + 30) + u16(at + 32)
                    val local = u32(at + 42)
                    if (at + 46 + nameLength + skip > end) refuse("not a zip directory")
                    val name = String(zip, (at + 46).toInt(), nameLength, Charsets.UTF_8)
                    at += 46 + nameLength + skip
                    if (size > ZIP_MAX_BYTES || packed > ZIP_MAX_BYTES) refuse("$name is too large")
                    total += size
                    if (total > ZIP_MAX_BYTES) refuse("the files are too large")
                    if (local + 30 > end || u32(local) != 0x04034b50L) refuse("$name has no header")
                    val from = local + 30 + u16(local + 26) + u16(local + 28)
                    if (from + packed > zip.size) refuse("$name is cut short")
                    val packedBytes = zip.copyOfRange(from.toInt(), (from + packed).toInt())
                    val content = when (method) {
                        0 -> { if (packed != size) refuse("$name is cut short"); packedBytes }
                        8 -> ByteArray(size.toInt()).also { into ->
                            val inflater = java.util.zip.Inflater(true)
                            try {
                                // (An extra byte after the stream, as the format asks of a reader without a header.)
                                inflater.setInput(packedBytes + 0)
                                var read = 0
                                while (read < into.size && !inflater.finished()) {
                                    val n = inflater.inflate(into, read, into.size - read)
                                    if (n == 0 && (inflater.needsInput() || inflater.needsDictionary())) break
                                    read += n
                                }
                                if (read != into.size) refuse("$name is cut short")
                            } catch (e: java.util.zip.DataFormatException) {
                                refuse("$name is not whole: ${e.message}")
                            } finally {
                                inflater.end()
                            }
                        }
                        else -> refuse("$name is packed in a way this does not read")
                    }
                    whole.putNextEntry(java.util.zip.ZipEntry(name))
                    whole.write(content)
                    whole.closeEntry()
                }
            }
            return out.toByteArray()
        }
    }
}
