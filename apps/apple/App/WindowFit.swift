import CoreGraphics

/// Keeps a Mac window on its screen: inside the visible frame (no part under the Dock or the menu
/// bar), in AppKit screen coordinates (y up). Pure functions, so the rules are unit-tested.
enum WindowFit {
    /// The main window's one minimum, a frame size (design/system.md §2). Every screen lays out at it
    /// without clipping, and no screen asks for more.
    static let minimumWindow = CGSize(width: 900, height: 600)
    /// The title bar and toolbar above the content.
    static let toolbarHeight: CGFloat = 52
    /// The content area at the minimum window.
    static var minimumContent: CGSize { CGSize(width: minimumWindow.width, height: minimumWindow.height - toolbarHeight) }
    /// Below this window width the library sidebar steps aside; its button brings it back.
    static let sidebarCollapseWidth: CGFloat = 1000
    /// Sheets: at most this share of the visible screen height; longer content scrolls inside.
    static let sheetHeightShare: CGFloat = 0.9

    /// The first window's size: 1280 × 900, or 90 % of the visible area on a smaller screen.
    static func defaultSize(visible v: CGRect) -> CGSize {
        CGSize(width: min(1280, (v.width * 0.9).rounded(.down)), height: min(900, (v.height * 0.9).rounded(.down)))
    }

    /// The frame moved and shrunk only as much as needed to fit `v`, never below `minSize`. A window
    /// that fits stays where it is. When the screen is smaller than the minimum, the top-left corner
    /// is pinned to the visible top-left, so the title bar and the first controls stay reachable.
    static func clamp(_ f: CGRect, into v: CGRect, minSize: CGSize = .zero) -> CGRect {
        let w = max(minSize.width, min(f.width, v.width))
        let h = max(minSize.height, min(f.height, v.height))
        let x = w <= v.width ? min(max(f.minX, v.minX), v.maxX - w) : v.minX
        let y = h <= v.height ? min(max(f.minY, v.minY), v.maxY - h) : v.maxY - h
        return CGRect(x: x, y: y, width: w, height: h)
    }

    /// Zoom's "standard" frame (a double-click on the title bar, or the green button with Option):
    /// the screen's visible frame, clear of the Dock and the menu bar, never below `minSize`.
    static func standardFrame(visible v: CGRect, minSize: CGSize = .zero) -> CGRect {
        clamp(v, into: v, minSize: minSize)
    }

    /// The frame reaches past the visible frame (under the Dock or the menu bar, or off the screen).
    static func overflows(_ f: CGRect, _ v: CGRect) -> Bool {
        f.minX < v.minX - 0.5 || f.minY < v.minY - 0.5 || f.maxX > v.maxX + 0.5 || f.maxY > v.maxY + 0.5
    }
}
