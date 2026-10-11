/// The names and the number this app shares with the engine. The link and the network service carry the
/// family's name, not a product's: one engine serves every app.
public enum Wire {
    /// The scheme of the pairing link in the computer's QR code: `scribe://pair?…`. Info.plist declares the same.
    public static let pairScheme = "scribe"
    /// The Bonjour service an engine on the local network advertises. Info.plist lists the same under NSBonjourServices.
    public static let serviceType = "_scribe._tcp"
    /// The interface version this app is built for. The engine says its own in `GET /v1/health`; when the two
    /// differ the app says which of them to update and sends that engine nothing else (`InterfaceMatch`).
    public static let interfaceVersion = 1
}
