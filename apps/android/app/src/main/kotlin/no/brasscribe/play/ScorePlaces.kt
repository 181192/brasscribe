package no.brasscribe.play

import java.io.File

/** Where a score was left in practice: the bar (1-based), the speed in per cent, and the bars repeated. */
data class ScorePlace(val bar: Int, val speed: Int, val repeat: IntRange?)

/**
 * Where each score in Your scores was left in practice, kept on the phone by the saved score's id: one small file to a
 * score, written whole and then put in place, which goes when the score is deleted. What can't be read, or holds
 * numbers no score has, is no place.
 */
class ScorePlaces(private val dir: File) {
    private fun named(id: String): File? = id.takeIf { ID.matches(it) }?.let { File(dir, it) }

    /** Where the score [id] was left; null when it was never practised, or what is kept can't be read. */
    fun read(id: String): ScorePlace? {
        val words = named(id)?.takeIf { it.isFile }?.let { runCatching { it.readText() }.getOrNull() }?.trim()?.split(' ') ?: return null
        // Whole numbers only: no "Infinity", no "NaN", nothing that is not a bar or a speed.
        fun number(i: Int) = words.getOrNull(i)?.takeIf { WHOLE.matches(it) }?.toIntOrNull()
        val bar = number(0)?.takeIf { it >= 1 } ?: return null
        val speed = number(1)?.takeIf { it in SPEED } ?: return null
        val first = number(2)
        val last = number(3)
        val repeat = if (first != null && last != null && first in 1..last) first..last else null
        return ScorePlace(bar, speed, repeat)
    }

    /** Keeps [place] for the score [id]: written whole, then put in the place of what was there. */
    fun save(id: String, place: ScorePlace) {
        val to = named(id) ?: return
        runCatching {
            dir.mkdirs()
            val part = File(dir, to.name + ".part")
            part.writeText(listOfNotNull(place.bar, place.speed, place.repeat?.first, place.repeat?.last).joinToString(" "))
            if (!part.renameTo(to)) part.delete()
        }.onFailure { android.util.Log.w(PlayViewModel.TAG, "where the score was left could not be kept", it) }
    }

    /** The score [id] left Your scores: its place goes too. */
    fun forget(id: String) {
        named(id)?.delete()
    }

    /** Drops the places of every score but [ids]. */
    fun prune(ids: Set<String>) {
        dir.listFiles()?.filter { it.name !in ids }?.forEach { it.delete() }
    }

    companion object {
        /** The ids Your scores gives (UUIDs): nothing else names a file here. */
        private val ID = Regex("""[A-Za-z0-9-]{1,64}""")
        private val WHOLE = Regex("""\d{1,6}""")
        private val SPEED = 25..150

        fun of(context: android.content.Context): ScorePlaces = ScorePlaces(File(context.noBackupFilesDir, "score-practice"))
    }
}
