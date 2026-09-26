import SwiftUI

/// The app's colours in one place, until the shared design system provides them.
/// The accent keeps at least 4.5:1 contrast on light and dark bars (the system blue on a
/// grey toolbar fails the accessibility audit on iPad). Notation colours are in
/// `NotationPalette`.
enum Palette {
    static let accent = Color(light: Color(red: 0.0, green: 0.33, blue: 0.72), dark: Color(red: 0.45, green: 0.72, blue: 1.0))
}

extension Color {
    init(light: Color, dark: Color) {
        #if os(iOS)
        self.init(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
        #else
        self.init(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(dark) : NSColor(light) })
        #endif
    }
}
