import SwiftUI

/// Where a few landmarks of each screen end up, for the layout tests (AppTests/ResponsiveLayoutTests):
/// the page's column, its actions, the parts column. Only recorded while unit tests run; in the app
/// the modifier does nothing.
@MainActor
enum LayoutProbe {
    static let isOn = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
    /// Frames in the window's coordinates (top-left origin), by name.
    static var frames: [String: CGRect] = [:]
}

extension View {
    @ViewBuilder func layoutProbe(_ name: String) -> some View {
        if LayoutProbe.isOn {
            onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { LayoutProbe.frames[name] = $0 }
                .onDisappear { LayoutProbe.frames[name] = nil }
        } else {
            self
        }
    }
}
