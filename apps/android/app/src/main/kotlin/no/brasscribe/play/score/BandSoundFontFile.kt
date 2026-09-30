package no.brasscribe.play.score

import android.content.Context
import java.io.File

/**
 * Where the band SoundFont comes from, in order:
 *  1. a sideloaded file in the app's external files under sounds/ (brasscribe-band-mobile.sf2,
 *     -16bit.sf2 or .sf2), so a tester can try another build without reinstalling;
 *  2. the phone SoundFont bundled in the APK (assets/sounds/brasscribe-band-mobile.sf2, present when
 *     data/sounds/band held it at build time), copied once to the app's files that are not backed up;
 *  3. none: the explicit basic tier, alphaTab's General MIDI SoundFont, logged and shown as such.
 */
object BandSoundFontFile {
    const val ASSET = "sounds/brasscribe-band-mobile.sf2"
    private const val COPY = "brasscribe-band-mobile.sf2"
    private const val TAG = "BrasscribePlay"
    private val SIDELOAD = listOf("brasscribe-band-mobile.sf2", "brasscribe-band-16bit.sf2", "brasscribe-band.sf2")

    fun sideloaded(context: Context): File? = context.getExternalFilesDir(null)?.resolve("sounds")
        ?.let { d -> SIDELOAD.map { d.resolve(it) }.firstOrNull { it.isFile } }

    /** True when a band SoundFont will load: sideloaded, or bundled in the APK. Cheap; safe on the UI thread. */
    fun available(context: Context): Boolean = sideloaded(context) != null || bundled(context)

    fun bundled(context: Context): Boolean = runCatching { context.assets.openFd(ASSET).use { it.length > 0 } }
        .getOrElse { runCatching { context.assets.open(ASSET).close() }.isSuccess }

    /** The file to load (copies the bundled asset on first use). Reads storage: call off the UI thread. */
    fun resolve(context: Context, sideload: File? = sideloaded(context)): File? {
        sideload?.takeIf { it.isFile }?.let { return it }
        if (!bundled(context)) {
            android.util.Log.i(TAG, "basic tier: no band SoundFont bundled or sideloaded, alphaTab plays General MIDI")
            return null
        }
        // Out of the backup: at 68 MB it is past the cloud backup's quota, and then no score would be backed up.
        File(context.filesDir, "sounds/$COPY").takeIf { it.isFile }?.delete()
        val out = File(context.noBackupFilesDir, "sounds/$COPY")
        val size = runCatching { context.assets.openFd(ASSET).use { it.length } }.getOrDefault(-1L)
        if (out.isFile && (size < 0 || out.length() == size)) return out
        return runCatching {
            out.parentFile?.mkdirs()
            val tmp = File(out.path + ".part")
            context.assets.open(ASSET).use { input -> tmp.outputStream().use { input.copyTo(it, 1 shl 16) } }
            check(tmp.renameTo(out)) { "rename failed" }
            out
        }.onFailure { android.util.Log.w(TAG, "bundled band SoundFont could not be copied", it) }.getOrNull()
    }
}
