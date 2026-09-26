package no.brasscribe.play.score

import android.content.Context
import java.io.File

/**
 * Realistic-tier instruments installed on the phone: the SFZ folders that sounds/build.py produces
 * (cornet-a, flugelhorn, tenor-horn, baritone, euphonium, trombone, bass-trombone, eb-bass, bb-bass,
 * soprano-cornet), copied to the app's external files under sounds/. Samples are not bundled.
 */
class SoundPack(context: Context) {
    val dir: File = File(context.getExternalFilesDir(null), "sounds")

    /** The sustain SFZ for a brass-band part name, if that instrument is installed. */
    fun sfzFor(partName: String): File? {
        val n = partName.lowercase()
        val instrument = when {
            "soprano" in n -> "soprano-cornet"
            "cornet" in n -> "cornet-a"
            "flugel" in n -> "flugelhorn"
            "horn" in n -> "tenor-horn"
            "baritone" in n -> "baritone"
            "euphonium" in n -> "euphonium"
            "bass trombone" in n -> "bass-trombone"
            "trombone" in n -> "trombone"
            "e♭ bass" in n || "eb bass" in n || "e-flat bass" in n -> "eb-bass"
            "b♭ bass" in n || "bb bass" in n || "b-flat bass" in n -> "bb-bass"
            else -> return null
        }
        return File(dir, "$instrument/$instrument-sus.sfz").takeIf { it.isFile }
    }
}
