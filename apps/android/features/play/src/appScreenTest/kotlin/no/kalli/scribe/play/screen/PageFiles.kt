package no.kalli.scribe.play.screen

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.test.core.app.ApplicationProvider
import no.kalli.scribe.play.MainActivity
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Printed music as another app or the phone's picker hands it over: pictures and PDFs made here (the fixture
 * computer does not read what is on them), and the intents the share sheet starts the app with.
 */
object PageFiles {
    private val context: Context get() = ApplicationProvider.getApplicationContext()

    /** Where the files to hand over are written: not the app's own folder for its pages. */
    private val dir: File get() = File(context.cacheDir, "handed-over").apply { mkdirs() }

    /** [bytes] as a file named [name], and the address another app would hand over for it. */
    fun handedOver(name: String, bytes: ByteArray): Uri = Uri.fromFile(File(dir, name).apply { writeBytes(bytes) })

    /** A picture of a page: paper with five dark lines across it, as [format] writes it. */
    fun picture(format: Bitmap.CompressFormat = Bitmap.CompressFormat.PNG, width: Int = 240, height: Int = 320): ByteArray {
        val page = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        page.eraseColor(Color.WHITE)
        for (line in 0 until 5) for (x in width / 10 until width * 9 / 10) page.setPixel(x, height / 3 + line * 8, Color.BLACK)
        return ByteArrayOutputStream().also { page.compress(format, 95, it) }.toByteArray()
    }

    /** A PDF by how it starts, with nothing to read in it. */
    fun pdf(): ByteArray = "%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n".toByteArray()

    /** A picture the computer does not read and the phone does: the smallest GIF there is. */
    fun gif(): ByteArray = "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b".chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    /** [uri] shared to the app from the share sheet, as [type]. */
    fun shared(uri: Uri, type: String = "image/png"): Intent = Intent(Intent.ACTION_SEND, null, context, MainActivity::class.java)
        .setType(type).putExtra(Intent.EXTRA_STREAM, uri)

    /** Several files shared to the app at once. */
    fun sharedTogether(uris: List<Uri>, type: String = "image/*"): Intent = Intent(Intent.ACTION_SEND_MULTIPLE, null, context, MainActivity::class.java)
        .setType(type).putParcelableArrayListExtra(Intent.EXTRA_STREAM, ArrayList(uris))

    fun clear() {
        dir.deleteRecursively()
    }
}
