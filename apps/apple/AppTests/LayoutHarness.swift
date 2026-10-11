#if os(macOS)
import AppKit
import Foundation
import ScoreKit
import ScreenCatalogue
import SwiftUI
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// Renders the app's screens off screen, for the layout tests: an NSHostingView in a borderless
/// window that is never ordered front, drawn with `cacheDisplay(in:to:)` into a bitmap. Nothing
/// is shown on the Mac's screen.
@MainActor
final class OffscreenHost {
    /// The unified title bar and toolbar of the real window. The borderless test window has none, so
    /// a window size W × H renders its content area at W × (H − toolbar).
    static let toolbarHeight: CGFloat = WindowFit.toolbarHeight

    let window: NSWindow
    let hosting: NSHostingView<AnyView>

    /// Light by default; the screen catalogue also draws it dark and with increased contrast.
    init(_ view: some View, size: CGSize, dark: Bool = false, increasedContrast: Bool = false) {
        window = NSWindow(contentRect: CGRect(origin: CGPoint(x: -30_000, y: -30_000), size: size),
                          styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        let schemed = view.environment(\.colorScheme, dark ? .dark : .light)
        hosting = NSHostingView(rootView: increasedContrast ? AnyView(schemed.catalogueContrast(increased: true)) : AnyView(schemed))
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

    /// The window's pixels. On macOS 26 the sidebar and the inspector float in glass that only the
    /// window server draws; their SwiftUI content is drawn here on a plain panel in its place.
    func bitmap() -> NSBitmapImageRep {
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
        NSColor(Color.Scribe.bg).setFill()
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

/// The window's layout, as `RootView` builds it on the Mac: the library in a sidebar (`LibrarySplit`,
/// with its window minimum and the sidebar rule) and the screen in the detail column's navigation stack.
struct HarnessShell<Content: View>: View {
    @State private var columns: NavigationSplitViewVisibility
    private let content: Content

    init(sidebar: Bool = true, @ViewBuilder content: () -> Content) {
        _columns = State(initialValue: sidebar ? .all : .detailOnly)
        self.content = content()
    }

    var body: some View {
        LibrarySplit(columns: $columns) { NavigationStack { content } }
            .tint(Color.Scribe.primary)
    }
}

/// The score screen's switch between the score and the music stand (`ScoreScreen`), for a model the
/// test holds.
struct ScoreOrStand: View {
    @Bindable var model: PracticeModel
    var body: some View {
        Group {
            if let stand = model.stand { MusicStandView(model: model, stand: stand) } else { PracticeView(model: model) }
        }
        .pageBackground()
    }
}

/// Fixture data for the layout tests: Old Hundredth, in a library of its own (unit tests keep
/// their scores out of the user's library).
@MainActor
enum LayoutFixtures {
    static func freshLibrary() {
        try? FileManager.default.removeItem(at: Piece.libraryURL)
        try? FileManager.default.createDirectory(at: Piece.libraryURL, withIntermediateDirectories: true)
    }

    static func app(connection: ConnectionState = .connected(serverName: "Brasscribe on Studio Mac")) -> AppModel {
        UserDefaults.standard.register(defaults: ["firstRunDone": true])
        // no engine answers here, so a Brasscribe running on this Mac never adds its scores to the library
        setenv("BRASSCRIBE_COMPANION", "http://127.0.0.1:9", 1)
        let app = AppModel()
        app.pieces = []
        let record = connection == .offline ? nil
            : EngineRecord(serverID: "7f3a9c2e", serverName: "Brasscribe on Studio Mac", deviceID: "d-41b2", token: "staged",
                           lastAddress: "http://192.0.2.20:8765", lastOK: Date().addingTimeInterval(-12))
        app.connection.stage(connection, record: record)
        return app
    }

    static func piece(title: String = "Old Hundredth", lineup: Lineup? = nil) throws -> Piece {
        let dir = try #require(fixtureDir())
        let xml = try Data(contentsOf: dir.appending(path: "brass-band.musicxml"))
        let comp = (try? Data(contentsOf: dir.appending(path: "composition.json"))).flatMap { try? Composition.decode($0) }
        let result = TranscriptionResult(jobID: "fixture", composition: comp, musicXML: xml, available: FixtureService(directory: dir).available)
        return try Piece.create(title: title, profile: .brassBand, result: result, original: nil, video: nil, fixtureDirectory: dir,
                                output: lineup.map { OutputChoice(lineup: $0) })
    }

    /// The lived-in library of the `home-full` screenshot scene.
    static func library(_ app: AppModel) throws {
        let first = try piece()
        let day: TimeInterval = 86_400
        var all = [first]
        let rows: [(String, TimeInterval, Lineup, Int)] = [
            ("Deep Harmony", 1 * day, .fullBand, 0), ("Abide with Me", 2 * day, .minimalBand, 12), ("Crimond", 3 * day, .quartet, 0),
            ("20260815_155324", 5 * day, .fullBand, 0), ("Floral Dance", 12 * day, .fullBand, 4),
        ]
        for (title, ago, lineup, toCheck) in rows {
            var p = first
            p.id = UUID(); p.title = title; p.created = Date().addingTimeInterval(-ago); p.output = OutputChoice(lineup: lineup); p.toCheck = toCheck
            all.append(p)
        }
        app.pieces = all
    }

    static func model(_ piece: Piece) async throws -> PracticeModel { try await PracticeModel.open(piece) }
}

/// Where the thumbnails go: apps/apple/docs/responsive, only when BRASSCRIBE_RESPONSIVE_SHOTS is set
/// (TEST_RUNNER_BRASSCRIBE_RESPONSIVE_SHOTS=1 on the xcodebuild line).
enum Thumbnails {
    static var enabled: Bool { ProcessInfo.processInfo.environment["BRASSCRIBE_RESPONSIVE_SHOTS"] != nil }

    static var directory: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().appending(path: "docs/responsive")
    }

    /// A JPEG at most `width` px wide.
    static func save(_ rep: NSBitmapImageRep, name: String, width: CGFloat = 480) {
        guard enabled else { return }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let scale = min(1, width / CGFloat(rep.pixelsWide))
        let w = Int((CGFloat(rep.pixelsWide) * scale).rounded()), h = Int((CGFloat(rep.pixelsHigh) * scale).rounded())
        guard let small = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4,
                                           hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: small)
        NSGraphicsContext.current?.imageInterpolation = .high
        NSColor.white.setFill()
        CGRect(x: 0, y: 0, width: w, height: h).fill()
        rep.draw(in: CGRect(x: 0, y: 0, width: w, height: h), from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
        NSGraphicsContext.restoreGraphicsState()
        if let data = small.representation(using: .jpeg, properties: [.compressionFactor: 0.72]) {
            try? data.write(to: directory.appending(path: "\(name).jpg"))
        }
    }

    /// The measurements, as JSON, next to the thumbnails.
    static func report(_ value: some Encodable, name: String) {
        guard enabled else { return }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        try? enc.encode(value).write(to: directory.appending(path: "\(name).json"))
    }
}
#endif
