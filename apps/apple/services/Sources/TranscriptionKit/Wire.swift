/// The names and the number this app shares with the engine. The link and the network service carry the
/// family's name, not a product's: one engine serves every app.
public enum Wire {
    /// The scheme of the pairing link in the computer's QR code: `scribe://pair?…`. Info.plist declares the same.
    public static let pairScheme = "scribe"
    /// The Bonjour service an engine on the local network advertises. Info.plist lists the same under NSBonjourServices.
    public static let serviceType = "_scribe._tcp"
    /// The interface version this app is built for. The engine says its own in `GET /v1/health` and, to a paired
    /// device, in `GET /v1/devices/me`; when the two differ the app says which of them to update and sends that
    /// engine nothing but those two (`InterfaceMatch`).
    public static let interfaceVersion = 1
    /// What the engine puts before the computer's name in the name it is known by on the network ("Brasscribe on Studio
    /// Mac", the engine's `discovery.PREFIX`). It is the engine's: each app says the computer's name in its own words.
    public static let serverNamePrefix = "Brasscribe on "
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
        /// computer is the older one. The engine can also run there without Bandroom (`scribe serve --lan`), and is
        /// then itself what to update.
        case computer
    }

    /// `engine` is `interface_version` of the engine's answer; nil when it has none, or one that is not a whole number.
    public static func of(engine: Int?, app: Int = Wire.interfaceVersion) -> InterfaceMatch {
        guard let engine, engine >= app else { return .mismatch(.computer) }
        return engine == app ? .match : .mismatch(.app)
    }
}
