import CoreGraphics
import Foundation

/// Whether the menu-bar mark can be seen (design/server-app.md §3.3). On a MacBook with a notch a crowded
/// menu bar puts extra items behind the camera housing, or off the screen, without telling the app.
public enum StatusItemVisibility {
    /// What AppKit reports about the status item's window after launch.
    public struct Reading: Equatable, Sendable {
        /// Nil: there is no window for the item at all.
        public var frame: CGRect?
        /// `NSWindow.occlusionState.contains(.visible)`.
        public var occlusionVisible: Bool
        /// Every screen's frame.
        public var screens: [CGRect]
        /// The notch's area on each screen (top-left and top-right auxiliary areas leave it between them).
        public var notches: [CGRect]

        public init(frame: CGRect?, occlusionVisible: Bool, screens: [CGRect], notches: [CGRect] = []) {
            self.frame = frame; self.occlusionVisible = occlusionVisible; self.screens = screens; self.notches = notches
        }
    }

    public static func isHidden(_ r: Reading) -> Bool {
        guard let frame = r.frame, frame.width > 0, frame.height > 0 else { return true }
        if !r.occlusionVisible { return true }
        // Mostly off every screen.
        let onScreen = r.screens.map { $0.intersection(frame) }.filter { !$0.isNull }.map { $0.width * $0.height }.reduce(0, +)
        if onScreen < frame.width * frame.height / 2 { return true }
        // Under the notch.
        return r.notches.contains { !$0.intersection(frame).isNull && $0.intersection(frame).width >= frame.width / 2 }
    }
}

/// What opening the app again (Finder, Launchpad, Spotlight, the Dock) shows.
public enum ReopenPolicy {
    public enum Target: String, Equatable, Sendable { case setup, main }

    /// The first run until it's finished; after that the "Brasscribe on this Mac" window, whatever else is open.
    public static func target(setupComplete: Bool) -> Target { setupComplete ? .main : .setup }
}

/// Window requests made before SwiftUI hands over its `openWindow` (a reopen event can arrive first).
@MainActor
public final class WindowOpener {
    private var open: ((String) -> Void)?
    private var pending: [String] = []

    public init() {}

    public var isReady: Bool { open != nil }

    public func attach(_ open: @escaping (String) -> Void) {
        self.open = open
        let queued = pending
        pending = []
        for id in queued { open(id) }
    }

    public func callAsFunction(_ id: String) {
        if let open { open(id) } else if !pending.contains(id) { pending.append(id) }
    }
}
