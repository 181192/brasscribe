package no.brasscribe.play.ui

import no.brasscribe.play.model.Lang

/**
 * Part names as the band room says them. The scores are written with English part names; in bokmål
 * they are shown with the core's one name table (part_name_nb, the same names as its talking score and
 * seat picker), so the same part has one name everywhere and in every app. Sound and part lookups keep
 * the English name. Without the core the English name is shown.
 */
object PartNames {
    /** The core's Norwegian name of a part; installed by the app container. */
    @Volatile var nb: (String) -> String = { it }

    /** A compound like "Repiano-kornett" may break only after its hyphen (review 3, P2-C). */
    fun display(name: String, lang: Lang = currentLang()): String {
        val clean = name.replace('\u00A0', ' ').trim()
        return (if (lang == Lang.NB) runCatching { nb(clean) }.getOrDefault(clean) else name).replace("-", "-\u200B")
    }

    /** "Old Hundredth — brass band (draft)" → "Old Hundredth": the short song title for headers. */
    fun shortTitle(title: String): String {
        val t = title.replace('\u00A0', ' ')
        return t.split(Regex("""\s[—–-]\s""")).first().replace(Regex("""\s*\((draft|utkast)\)\s*$""", RegexOption.IGNORE_CASE), "").trim()
            .ifBlank { title }
    }
}
