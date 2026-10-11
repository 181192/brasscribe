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

/// Whether this app and an engine speak the same interface, and if not, which of the two is behind.
public enum InterfaceMatch: Equatable, Sendable {
    case match
    case mismatch(Update)

    /// The one to update.
    public enum Update: Equatable, Sendable {
        /// The engine's number is higher: this app is the older one.
        case app
        /// The engine's number is lower, or it has none (an engine from before the number): Bandroom on the
        /// computer is the older one.
        case computer
    }

    /// `engine` is `interface_version` of the engine's health answer; nil when it has none.
    public static func of(engine: Int?, app: Int = Wire.interfaceVersion) -> InterfaceMatch {
        guard let engine, engine >= app else { return .mismatch(.computer) }
        return engine == app ? .match : .mismatch(.app)
    }
}
