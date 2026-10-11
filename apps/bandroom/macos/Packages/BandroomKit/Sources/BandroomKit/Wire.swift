import Foundation

/// The number Bandroom shares with the engine it runs.
public enum Wire {
    /// The interface version this Bandroom is built for. The engine says its own in `GET /v1/health`; when the two
    /// differ Bandroom says which of them is behind and asks that engine nothing else (`InterfaceMatch`).
    public static let interfaceVersion = 1
}

/// Whether Bandroom and the engine it started speak the same interface, and if not, which of the two is behind.
public enum InterfaceMatch: Equatable, Sendable {
    case match
    case mismatch(Behind)

    /// The older of the two.
    public enum Behind: Equatable, Sendable {
        /// The engine's number is higher: this copy of Bandroom is the older one.
        case bandroom
        /// The engine's number is lower, or it has none (an engine from before the number): the engine is the older one.
        case engine
    }

    /// `engine` is `interface_version` of the engine's health answer; nil when it has none.
    public static func of(engine: Int?, app: Int = Wire.interfaceVersion) -> InterfaceMatch {
        guard let engine, engine >= app else { return .mismatch(.engine) }
        return engine == app ? .match : .mismatch(.bandroom)
    }

    /// The one that is behind, nil when they match.
    public var behind: Behind? {
        if case .mismatch(let b) = self { b } else { nil }
    }
}
