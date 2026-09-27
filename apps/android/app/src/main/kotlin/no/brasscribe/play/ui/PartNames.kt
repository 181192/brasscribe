package no.brasscribe.play.ui

import no.brasscribe.play.model.Lang

/**
 * Part names as the band room says them. The scores are written with English part names; in bokmål
 * they are shown with the names the core's talking score uses (core/brasscribe-core/src/talking_score.rs),
 * so the same part has one name everywhere on screen. Sound and part lookups keep the English name.
 */
object PartNames {
    private val NB = mapOf(
        "Soprano Cornet" to "Sopran-kornett", "Solo Cornet" to "Solokornett", "Repiano Cornet" to "Repiano-kornett",
        "1st Cornet" to "1. kornett", "Tenor Horn" to "Althorn",
        "2nd Cornet" to "2. kornett", "3rd Cornet" to "3. kornett", "Flugelhorn" to "Flygelhorn",
        "Solo Horn" to "Solo althorn", "1st Horn" to "1. althorn", "2nd Horn" to "2. althorn",
        "1st Baritone" to "1. baryton", "2nd Baritone" to "2. baryton",
        "1st Trombone" to "1. trombone", "2nd Trombone" to "2. trombone", "Bass Trombone" to "Basstrombone",
        "Euphonium" to "Eufonium", "E♭ Bass" to "Ess-bass", "B♭ Bass" to "B-bass", "Percussion" to "Slagverk",
        // The transcribed layers.
        "Bass" to "Bass", "Strings" to "Strykere", "Brass" to "Messing", "Drums" to "Trommer",
    )

    /** A compound like "Repiano-kornett" may break only after its hyphen (review 3, P2-C). */
    fun display(name: String, lang: Lang = currentLang()): String =
        (if (lang == Lang.NB) NB[name.replace(' ', ' ').trim()] ?: name else name).replace("-", "-\u200B")

    /** "Old Hundredth — brass band (draft)" → "Old Hundredth": the short song title for headers. */
    fun shortTitle(title: String): String {
        val t = title.replace('\u00A0', ' ')
        return t.split(Regex("""\s[—–-]\s""")).first().replace(Regex("""\s*\((draft|utkast)\)\s*$""", RegexOption.IGNORE_CASE), "").trim()
            .ifBlank { title }
    }
}
