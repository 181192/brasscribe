#if os(macOS)
import AppKit
import Foundation
import ScreenCatalogue
import SwiftUI

// Test code every Play app's tests share (compiled into each product's unit-test target).

/// Renders the app's screens off screen, for the layout tests: an NSHostingView in a borderless
/// window that is never ordered front, drawn with `cacheDisplay(in:to:)` into a bitmap. Nothing
/// is shown on the Mac's screen.
@MainActor
final class OffscreenHost {
    // `toolbarHeight` (the unified title bar and toolbar of the real window: the borderless test window has none, so a
    // window size W × H renders its content area at W × (H − toolbar)) and `pageColor` (the page's ground) are the
    // product's, in an extension in its own tests (`PlayTestsProduct.swift`).

    let window: NSWindow
    let hosting: NSHostingView<AnyView>
    /// The appearance asked for, the size last asked for, and what the content says it is drawn in.
    let asked: Asked
    private(set) var size: CGSize
    let witness: AppearanceWitness

    /// Light by default; the screen catalogue also draws it dark and with increased contrast. The appearance is the
    /// window's, as on a Mac set that way: SwiftUI and AppKit both read it from there (and Increase Contrast from
    /// `SystemContrast`, which every host tells what it asks for, on or off), in every hosting view of
    /// the screen. `witness` is given when the caller has put it where the screen's own views are (`catalogueWitness`);
    /// otherwise it sits at the root.
    init(_ view: some View, size: CGSize, dark: Bool = false, increasedContrast: Bool = false, witness: AppearanceWitness? = nil) {
        asked = Asked(dark: dark, increasedContrast: increasedContrast)
        self.size = size
        SystemContrast.set(increasedContrast)
        window = NSWindow(contentRect: CGRect(origin: CGPoint(x: -30_000, y: -30_000), size: size),
                          styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: asked.appearance)
        if let witness {
            self.witness = witness
            hosting = NSHostingView(rootView: AnyView(view))
        } else {
            let own = AppearanceWitness()
            self.witness = own
            hosting = NSHostingView(rootView: AnyView(view.catalogueWitness(own)))
        }
        // SwiftUI hands the window its content minimum (`contentMinSize`), as in the app; the test still
        // sets the size itself
        hosting.sizingOptions = .minSize
        hosting.frame = CGRect(origin: .zero, size: size)
        window.contentView = hosting
    }

    /// From here on only the test sizes the window. With a sizing option set, the hosting view sizes its window itself
    /// on macOS 27 when a split view's sidebar comes back (a window of 1024 becomes 1305 wide), so a screen would be
    /// drawn at another size than the one asked for; and with the library's split view that resize does not come to
    /// rest (1305, 1304, 1305, …, each from inside the layout of the one before) until the main thread's stack is used
    /// up. Call it once the window's minimum has been read: it is not handed to the window after this.
    func holdWindowSize() { hosting.sizingOptions = [] }

    func resize(_ size: CGSize) async {
        self.size = size
        window.setContentSize(size)
        hosting.frame = CGRect(origin: .zero, size: size)
        await settle(0.15)
    }

    /// Lets SwiftUI run its updates and tasks (the score opens and engraves off the main thread):
    /// the test suspends, so the main run loop and the main actor carry on.
    func settle(_ seconds: TimeInterval = 0.3) async {
        try? await Task.sleep(for: .seconds(seconds))
        hosting.layoutSubtreeIfNeeded()
    }

    /// Settles until `done` holds, or the timeout.
    func settle(until done: () -> Bool, timeout: TimeInterval = 10) async {
        let end = Date().addingTimeInterval(timeout)
        while !done(), Date() < end { await settle(0.05) }
        await settle(0.3)
    }

    /// The screen's picture and tree for the catalogue, taken by its rule (`ScreenTake`): only once the window is
    /// this one at its size, in the appearance and language asked for, with its content in place (`ready` says what
    /// the screen itself still waits for, `shows` the same of its tree) and drawn, and keeping still.
    func take(_ name: String, controls: Bool = true, ready: () -> String? = { nil }, shows: ([AXNode]) -> String? = { _ in nil },
              unreadable: Unreadable? = nil, output: URL) async throws -> ScreenTake {
        try await ScreenTake.take(name, window: window, view: hosting, size: { self.size }, asked: asked, witness: witness, controls: controls,
                                  ready: ready, shows: shows, unreadable: unreadable, picture: { self.bitmap() }, output: output)
    }

    /// The window's pixels. On macOS 26 the sidebar and the inspector float in glass that only the
    /// window server draws; their SwiftUI content is drawn here on a plain panel in its place, in the
    /// window's appearance.
    func bitmap() -> NSBitmapImageRep {
        var rep: NSBitmapImageRep!
        window.effectiveAppearance.performAsCurrentDrawingAppearance { rep = draw() }
        return rep
    }

    private func draw() -> NSBitmapImageRep {
        hosting.layoutSubtreeIfNeeded()
        let rep = hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds)!
        hosting.cacheDisplay(in: hosting.bounds, to: rep)
        // shown, and inside the window (a collapsed sidebar keeps its views, hidden or off to the side)
        func shown(_ v: NSView) -> Bool {
            var cur: NSView? = v
            while let c = cur, c !== hosting {
                if c.isHidden || c.alphaValue < 0.01 || c.bounds.width < 1 { return false }
                cur = c.superview
            }
            return v.convert(v.bounds, to: hosting).intersects(hosting.bounds)
        }
        let all = Self.descendants(hosting).filter(shown)
        func named(_ v: NSView, _ suffixes: [String]) -> Bool {
            let n = NSStringFromClass(type(of: v))
            return suffixes.contains { n.hasSuffix($0) }
        }
        let glass = all.filter { named($0, ["GlassEffectView"]) }
        guard !glass.isEmpty, let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return rep }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        let h = hosting.bounds.height
        func flip(_ r: CGRect) -> CGRect { CGRect(x: r.minX, y: h - r.maxY, width: r.width, height: r.height) }
        // the blurred strip behind a floating sidebar shows the page
        NSColor(Self.pageColor).setFill()
        for a in all where named(a, ["BlurryAlleywayView"]) { flip(a.convert(a.bounds, to: hosting)).fill() }
        let dark = window.appearance?.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        for g in glass {
            NSColor(calibratedWhite: dark ? 0.17 : 0.955, alpha: 1).setFill()
            NSBezierPath(roundedRect: flip(g.convert(g.bounds, to: hosting)), xRadius: 14, yRadius: 14).fill()
            NSColor(calibratedWhite: dark ? 0.3 : 0.85, alpha: 1).setStroke()
            NSBezierPath(roundedRect: flip(g.convert(g.bounds, to: hosting)).insetBy(dx: 0.5, dy: 0.5), xRadius: 14, yRadius: 14).stroke()
            for v in g.subviews where shown(v) {
                let n = NSStringFromClass(type(of: v))
                if n.contains("Backdrop") || n.contains("CoreHostingView") { continue }
                guard let sub = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { continue }
                v.cacheDisplay(in: v.bounds, to: sub)
                sub.draw(in: flip(v.convert(v.bounds, to: hosting)), from: .zero, operation: .sourceOver, fraction: 1,
                         respectFlipped: false, hints: nil)
            }
        }
        NSGraphicsContext.restoreGraphicsState()
        return rep
    }

    static func descendants(_ v: NSView) -> [NSView] { v.subviews + v.subviews.flatMap(descendants) }

    /// The split view's sidebar is showing (not collapsed).
    var sidebarShown: Bool {
        for case let split as NSSplitView in Self.descendants(hosting) {
            if let controller = split.delegate as? NSSplitViewController, let sidebar = controller.splitViewItems.first(where: { $0.behavior == .sidebar }) {
                return !sidebar.isCollapsed
            }
        }
        return false
    }

    /// The smallest content size the window allows for this view: what SwiftUI hands the window.
    var windowMinimum: CGSize { window.contentMinSize }

    func close() { window.contentView = nil; window.close() }
}

/// The sizes SwiftUI reports for a view: its minimum, ideal (what a sheet opens at) and maximum.
@MainActor
enum Measure {
    struct Sizes: Codable { var min: CGSize; var ideal: CGSize; var max: CGSize }

    static func sizes(_ view: some View) -> Sizes {
        let c = NSHostingController(rootView: AnyView(view.environment(\.colorScheme, .light)))
        _ = c.view
        let min = c.sizeThatFits(in: CGSize(width: 1, height: 1))
        let ideal = c.view.fittingSize
        let max = c.sizeThatFits(in: CGSize(width: 100_000, height: 100_000))
        return Sizes(min: min, ideal: ideal, max: max)
    }
}
#endif
