import CoreGraphics

/// Keeps a Mac window on its screen: inside the visible frame (no part under the Dock or the menu
/// bar), in AppKit screen coordinates (y up). Pure functions, so the rules are unit-tested.
enum WindowFit {
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
}
