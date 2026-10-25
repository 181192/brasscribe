#if os(macOS)
import SwiftUI
@testable import BrasscribePlay

/// What the shared test code (testing/PlayTests) takes from this app.
extension OffscreenHost {
    static let toolbarHeight: CGFloat = WindowFit.toolbarHeight
    static var pageColor: Color { Color.Scribe.bg }
}
#endif
