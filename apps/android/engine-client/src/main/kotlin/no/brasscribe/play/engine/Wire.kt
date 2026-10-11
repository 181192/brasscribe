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
