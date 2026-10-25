#if os(macOS)
import AppKit

/// Holds a main window's minimum at `WindowFit.minimumWindow`, 900 × 600.
///
/// SwiftUI hands the window its content's minimum (`contentMinSize`): the split view's 900 × 548
/// plus the 52 pt title bar and toolbar, which is 900 × 600. But a window SwiftUI opens later, with
/// File › New Window, or as the first window when the app starts in the background and the window
/// comes from the New Window action, gets 900 × 620 with the same layout: the same toolbar, the same
/// 52 pt inset and the same 548 pt content. Nothing in the content needs the extra 20 pt. The layout
/// tests (ResponsiveLayoutTests) check that every screen lays out at 900 × 548 without clipping and
/// that none asks for more, so the window's own minimum is the one that holds.
@MainActor
enum WindowMinimum {
    private static var observations: [ObjectIdentifier: NSKeyValueObservation] = [:]

    /// Applies the minimum to a main window now, and again each time SwiftUI sets the content's minimum.
    static func keep(_ window: NSWindow) {
        guard window.canBecomeMain else { return }
        hold(window)
    }

    /// `keep` for any window (the layout tests' off-screen window cannot become main).
    static func hold(_ window: NSWindow) {
        guard observations[ObjectIdentifier(window)] == nil else { return }
        // closed windows let their observations go
        observations = observations.filter { key, _ in NSApp.windows.contains { ObjectIdentifier($0) == key } }
        apply(window)
        observations[ObjectIdentifier(window)] = window.observe(\.contentMinSize) { w, _ in
            MainActor.assumeIsolated { apply(w) }
        }
    }

    /// The content size of a `WindowFit.minimumWindow` frame (the whole frame when the content runs
    /// under the toolbar, as SwiftUI's windows do).
    static func contentMinimum(_ window: NSWindow) -> CGSize {
        window.contentRect(forFrameRect: CGRect(origin: .zero, size: WindowFit.minimumWindow)).size
    }

    static func apply(_ window: NSWindow) {
        let target = contentMinimum(window)
        if window.contentMinSize != target { window.contentMinSize = target }
        if window.minSize != WindowFit.minimumWindow { window.minSize = WindowFit.minimumWindow }
    }
}
#endif
