package no.brasscribe.play.engine

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/**
 * The names and the number this app shares with the engine. The link and the network service carry the
 * family's name, not a product's: one engine serves every app.
 */
object Wire {
    /** The scheme of the pairing link in the computer's QR code: `scribe://pair?…`. The manifest declares the same. */
    const val PAIR_SCHEME = "scribe"

    /** The DNS-SD service an engine on the local network advertises. */
    const val SERVICE_TYPE = "_scribe._tcp"

    /**
     * The interface version this app is built for. The engine says its own in `GET /v1/health`; when the two
     * differ the app says which of them to update and asks that engine for its health only ([KtorEngineApi] refuses
     * every other request).
     */
    const val INTERFACE_VERSION = 1
}

/** Whether an engine and this app speak the same interface, and if not, which of the two is behind. */
enum class InterfaceMatch {
    /** The same number: they work together. */
    MATCH,
    /** The engine's number is higher: this app is the old one. */
    UPDATE_APP,
    /** The engine's number is lower, or it sends none (it is from before there was one): Bandroom is the old one. */
    UPDATE_COMPUTER;

    companion object {
        /** [engine] is `interface_version` from the engine's health answer. */
        fun of(engine: Int?, app: Int = Wire.INTERFACE_VERSION): InterfaceMatch = when {
            engine == null || engine < app -> UPDATE_COMPUTER
            engine > app -> UPDATE_APP
            else -> MATCH
        }
    }
}

/** The engine was asked for nothing more: its interface version is not this app's. [update] is never [InterfaceMatch.MATCH]. */
class InterfaceMismatchException(val update: InterfaceMatch) : Exception("the engine's interface version is not this app's: $update")

/**
 * Reads `interface_version` as a whole number, and as none when the engine sent something else in its place (a
 * fraction, a text, true): such an engine is not one this app is built for, and it is told apart from one that
 * cannot be reached. The rest of the answer is still read.
 */
object InterfaceVersionSerializer : KSerializer<Int?> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("InterfaceVersion", PrimitiveKind.INT)

    override fun deserialize(decoder: Decoder): Int? {
        val element = (decoder as? JsonDecoder)?.decodeJsonElement() ?: return decoder.decodeInt()
        return of(element)
    }

    override fun serialize(encoder: Encoder, value: Int?) {
        if (value == null) encoder.encodeNull() else encoder.encodeInt(value)
    }

    /** The number in [element], or null when it is not a whole number that fits. */
    fun of(element: JsonElement?): Int? {
        val primitive = element as? JsonPrimitive ?: return null
        if (primitive.isString) return null
        return primitive.content.toIntOrNull()
    }
}
