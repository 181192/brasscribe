package no.brasscribe.play.engine

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
     * differ the app says which of them to update and sends that engine nothing else ([InterfaceMatch]).
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

/** Throws [InterfaceMismatchException] unless this engine's interface version is the app's. */
fun Health.requireSameInterface() {
    val match = InterfaceMatch.of(interfaceVersion)
    if (match != InterfaceMatch.MATCH) throw InterfaceMismatchException(match)
}
