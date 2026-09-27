import AppKit

/// Settings › Appearance (design/system.md §10): follow the system, or force light or dark on this Mac.
/// Stored per device in UserDefaults under `appearance`; unknown or missing values mean "Match system".
public enum AppearanceChoice: String, CaseIterable, Identifiable, Sendable {
    case system, light, dark

    public static let defaultsKey = "appearance"

    public var id: String { rawValue }

    public init(stored: String?) {
        self = stored.flatMap(AppearanceChoice.init(rawValue:)) ?? .system
    }

    /// The appearance for `NSApp.appearance`; nil follows the system. Increase Contrast still applies on top:
    /// AppKit resolves the high-contrast variant of the named appearance and of the asset-catalog colours.
    public var appearanceName: NSAppearance.Name? {
        switch self {
        case .system: nil
        case .light: .aqua
        case .dark: .darkAqua
        }
    }

    /// The stored choice. `BANDROOM_APPEARANCE` (used for screenshots) wins over it.
    public static func current(defaults: UserDefaults = .standard,
                               environment: [String: String] = ProcessInfo.processInfo.environment) -> AppearanceChoice {
        if let forced = environment["BANDROOM_APPEARANCE"], let choice = AppearanceChoice(rawValue: forced) { return choice }
        return AppearanceChoice(stored: defaults.string(forKey: defaultsKey))
    }
}
