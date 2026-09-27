package no.brasscribe.play

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * What a score is called on Home (review 3): the name the player gave it; failing that, the file name
 * without its extension; and never a bare timestamp like "20260815_155324" or "take-1790…". A
 * recording without a name is "Recording, 26 Sep 19:02".
 */
object ScoreTitles {
    private val stamp = Regex("""^(?:take[-_ ]?|rec(?:ording)?[-_ ]?|IMG[-_]|VID[-_]|AUD[-_])?(\d{8}[-_ ]?\d{4,6}|\d{10,13})$""", RegexOption.IGNORE_CASE)

    /** True for names that are only a date and time or a number: they say nothing to a player. */
    fun isTimestamp(name: String): Boolean = stamp.matches(name.trim())

    fun withoutExtension(name: String): String =
        name.substringAfterLast('/').let { if ('.' in it && it.substringAfterLast('.').length in 1..5) it.substringBeforeLast('.') else it }.trim()

    /** "Recording, 26 Sep 19:02" (bokmål "Opptak, 26. sep. 19:02"). */
    fun recording(time: Long, locale: Locale = Locale.getDefault()): String {
        val nb = locale.language in setOf("nb", "no", "nn")
        val date = SimpleDateFormat(if (nb) "d. MMM HH:mm" else "d MMM HH:mm", locale).format(Date(time))
        return (if (nb) "Opptak, " else "Recording, ") + date
    }

    /** The title to show for a score saved as [raw] at [updated]. */
    fun display(raw: String, updated: Long, locale: Locale = Locale.getDefault()): String {
        val name = withoutExtension(raw)
        return if (name.isBlank() || isTimestamp(name)) recording(updated, locale) else name
    }
}
