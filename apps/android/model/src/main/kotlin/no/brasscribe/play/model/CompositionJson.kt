package no.brasscribe.play.model

import kotlinx.serialization.json.Json

/** JSON settings shared by every reader of engine output: tolerant of new fields, compact on write. */
val BrasscribeJson: Json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    encodeDefaults = true
}

object CompositionJson {
    fun decode(text: String): Composition = BrasscribeJson.decodeFromString(Composition.serializer(), text)
    fun encode(composition: Composition): String = BrasscribeJson.encodeToString(Composition.serializer(), composition)
}
