package no.brasscribe.play.score

import android.content.Context
import java.io.File

/**
 * Realistic-tier instruments installed on the phone: the SFZ folders that sounds/build.py produces
 * (one per mapping.json target), copied to the app's external files under sounds/. Samples are not
 * bundled. Which folder a part plays comes from the band resolver ([BandSoundMap.resolve]), never from
 * the part name alone, so the realistic tier and the band SoundFont agree on every part.
 */
class SoundPack(context: Context) {
    val dir: File = File(context.getExternalFilesDir(null), "sounds")

    init {
        // The app creates the folders itself: files copied in with adb or a file manager are readable
        // by the app only inside folders it owns.
        INSTRUMENTS.forEach { File(dir, "$it/samples").mkdirs() }
    }

    /** The sustain SFZ of a resolved part's instrument, if it (or a sibling build of the same instrument) is installed. */
    fun sfzFor(sound: TrackSound): File? = sfzFor(dir, sound)

    companion object {
        val INSTRUMENTS = listOf("soprano-cornet", "cornet-a", "cornet-b", "flugelhorn", "tenor-horn", "baritone",
            "euphonium", "trombone", "bass-trombone", "eb-bass", "bb-bass")

        /** Builds of the same instrument that can stand in for each other (the two cornet sources). */
        private val SIBLINGS = mapOf("cornet-a" to listOf("cornet-b"), "cornet-b" to listOf("cornet-a"))

        fun sfzFor(dir: File, sound: TrackSound): File? {
            val target = sound.target ?: return null
            return (listOf(target) + SIBLINGS[target].orEmpty())
                .map { File(dir, "$it/$it-sus.sfz") }.firstOrNull { it.isFile }
        }
    }
}
