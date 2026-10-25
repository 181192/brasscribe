import SwiftUI
import TabKit

/// The page's colours from Fretscribe's tokens, as the screen's appearance resolves them: ink numerals, the lines in the
/// string colour, the doubt colour, and the cursor with its wash. High contrast has shapes only, so no wash.
enum TabColours {
    /// `highContrast`: Increase Contrast is on (by default, as `environment` says).
    static func palette(in environment: EnvironmentValues, highContrast: Bool? = nil) -> TabPalette {
        func hex(_ c: Color) -> String { css(c.resolve(in: environment)) }
        let contrast = highContrast ?? (environment.colorSchemeContrast == .increased)
        return TabPalette(ink: hex(Color.Scribe.ink), string: hex(Color.Scribe.line), uncertain: hex(Color.Scribe.uncertain),
                          cursor: hex(Color.Fretscribe.cursor), cursorTint: contrast ? nil : hex(Color.Fretscribe.cursorTint))
    }

    /// `#rrggbb`, or `#rrggbbaa` for a colour that is not opaque.
    static func css(_ c: Color.Resolved) -> String {
        func byte(_ v: Float) -> Int { Int((min(max(v, 0), 1) * 255).rounded()) }
        let rgb = String(format: "#%02x%02x%02x", byte(c.red), byte(c.green), byte(c.blue))
        return c.opacity >= 0.999 ? rgb : rgb + String(format: "%02x", byte(c.opacity))
    }
}
