package no.brasscribe.play.connection

/**
 * The engine calls itself "Brasscribe on <computer>". Each language builds its own phrase from the
 * computer part ("Brasscribe on Kari's Mac", "Brasscribe på Kari's Mac") instead of quoting the English
 * name inside a Norwegian sentence.
 */
object ServerNames {
    private const val PREFIX = "Brasscribe on "
    /** " (2)": what mDNS appends when two services share a name. */
    private val COLLISION = Regex("""\s+\(\d+\)$""")

    /** The computer's name, or null when [serverName] is not in the engine's form. */
    fun computer(serverName: String): String? =
        serverName.trim().takeIf { it.startsWith(PREFIX) }?.removePrefix(PREFIX)?.replace(COLLISION, "")?.trim()?.takeIf { it.isNotEmpty() }

    /** [format] turns the computer name into this language's phrase; [fallback] is for a missing name. */
    fun display(serverName: String, format: (String) -> String, fallback: String): String =
        computer(serverName)?.let(format)
            ?: serverName.trim().replace(COLLISION, "").takeIf { it.isNotEmpty() && it != PREFIX.trim() } ?: fallback
}
