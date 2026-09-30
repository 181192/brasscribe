package no.brasscribe.play

import java.io.File

/**
 * The source as it outlives the process: its name, kind, length and the copy on disk. The decoded
 * samples are not kept; a restored source goes to the computer as its file.
 */
data class SavedSource(val name: String, val kind: SourceKind, val durationS: Double, val file: File?) {
    fun encode(): String = listOf(kind.name, durationS.toString(), file?.path.orEmpty(), name).joinToString("\n")

    fun toSource() = Source(name, kind, durationS, audio = null, file = file)

    companion object {
        fun of(s: Source) = SavedSource(s.name, s.kind, s.durationS, s.file)

        fun decode(text: String): SavedSource? {
            val parts = text.split("\n", limit = 4)
            if (parts.size != 4) return null
            val kind = SourceKind.entries.firstOrNull { it.name == parts[0] } ?: return null
            return SavedSource(parts[3], kind, parts[1].toDoubleOrNull() ?: 0.0, parts[2].takeIf { it.isNotEmpty() }?.let(::File))
        }
    }
}

/** Which of the screens the user had open can come back after the process was ended in the background. */
object RestoredStack {
    /** Screens that show a score: they come back only once it has been read again. */
    private val SCORE_SCREENS = setOf(Screen.REVIEW, Screen.OUTPUT, Screen.SCORE, Screen.EXPORT)

    /** A recording, a score being made and a problem cannot be resumed: the screen before them comes back. */
    private val TRANSIENT = setOf(Screen.RECORD, Screen.TRANSCRIBE, Screen.PROBLEM)

    fun needsScore(stack: List<Screen>): Boolean = stack.any { it in SCORE_SCREENS }

    /** The screens that come back at once, before the score is read. */
    fun plain(stack: List<Screen>, hasSource: Boolean): List<Screen> = filter(stack, hasSource, withScore = false)

    /** The screens that come back once the score is read. */
    fun withScore(stack: List<Screen>, hasSource: Boolean): List<Screen> = filter(stack, hasSource, withScore = true)

    private fun filter(stack: List<Screen>, hasSource: Boolean, withScore: Boolean): List<Screen> {
        val kept = stack.filterIndexed { i, s ->
            when {
                s in TRANSIENT -> false
                s in SCORE_SCREENS -> withScore
                s == Screen.PROFILE -> hasSource
                // "What do you play?" opened from Settings or a take: what it was asked for is gone.
                s == Screen.WHAT_DO_YOU_PLAY -> i == 0
                else -> true
            }
        }
        return if (kept.isEmpty() || kept.first() !in ROOTS) listOf(Screen.HOME) + kept.filter { it !in ROOTS } else kept
    }

    private val ROOTS = setOf(Screen.HOME, Screen.FIRST_RUN, Screen.WHAT_DO_YOU_PLAY)
}
