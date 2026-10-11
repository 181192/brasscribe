import AppKit
import ScreenCatalogue
import SwiftUI
import Testing
@testable import Brasscribe_Bandroom

// Bandroom's side of the screen catalogue: its variants, its models on canned engine answers, and the drawing off
// screen (README, Testing). The accessibility tree, the checks and the hooks' guards are the Mac apps' shared
// ScreenCatalogue package (apps/apple/Packages/ScreenCatalogue). Nothing here shows a window: the views are drawn by
// an NSHostingView in a borderless window that is never ordered in, far off any screen.

/// One way a screen is drawn: appearance, contrast and text size. The language is the run's own
/// (`xcodebuild -testLanguage nb` for bokmål), so it is part of the variant's name, not of the variant.
struct Variant: Sendable, CustomStringConvertible {
    let name: String
    let dark: Bool
    let increasedContrast: Bool
    let textSize: TextSize

    var description: String { name }

    static let light = Variant(name: "light", dark: false, increasedContrast: false, textSize: .standard)
    static let dark = Variant(name: "dark", dark: true, increasedContrast: false, textSize: .standard)
    static let contrast = Variant(name: "contrast", dark: false, increasedContrast: true, textSize: .standard)
    static let contrastDark = Variant(name: "contrast-dark", dark: true, increasedContrast: true, textSize: .standard)
    /// Bandroom's own largest text size (Settings › Text size); macOS has no system text size for its windows.
    static let largeText = Variant(name: "large-text", dark: false, increasedContrast: false, textSize: .larger)

    /// In English every variant; in another language the light one and the large text, where longer words run out of room.
    static var all: [Variant] { Catalogue.language == "en" ? [light, dark, contrast, contrastDark, largeText] : [light, largeText] }
}

@MainActor
enum Catalogue {
    /// The language the test host runs in: "en", or "nb" under `-testLanguage nb`.
    nonisolated static var language: String { Bundle.main.preferredLocalizations.first ?? "en" }

    /// Where the screenshots go: CATALOGUE_OUT (TEST_RUNNER_CATALOGUE_OUT on the xcodebuild line), or
    /// build/catalogue/screenshots in this checkout.
    static var output: URL {
        if let dir = ProcessInfo.processInfo.environment["CATALOGUE_OUT"], !dir.isEmpty { return URL(fileURLWithPath: dir, isDirectory: true) }
        return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "build/catalogue/screenshots", directoryHint: .isDirectory)
    }

    /// The settings the catalogue's models read and write: a store of its own, emptied once per run, never the app's.
    static let defaults: UserDefaults = {
        let name = "no.brasscribe.bandroom.catalogue"
        let store = UserDefaults(suiteName: name)!
        store.removePersistentDomain(forName: name)
        return store
    }()

    /// The faces Bandroom draws text in, for the cut-off text check: the system font and Instrument Serif (titles).
    static let text = TextFit(fonts: ["InstrumentSerif-Regular"])

    /// A model of its own, on canned engine answers (`DemoEngine`): BANDROOM_DEMO and BANDROOM_DEMO_REQUEST are read
    /// when it starts.
    static func model(busy: Bool, request: Bool = false) async -> AppModel {
        AXTree.enableInProcess()
        setenv("BANDROOM_DEMO", busy ? "busy" : "idle", 1)
        if request { setenv("BANDROOM_DEMO_REQUEST", "1", 1) } else { unsetenv("BANDROOM_DEMO_REQUEST") }
        let app = AppModel(defaults: defaults)
        app.launch()
        unsetenv("BANDROOM_DEMO_REQUEST")
        await app.monitor.refresh()
        await app.monitor.refreshRequests()
        // The first sample of this computer (the demo's own) comes from a task of its own.
        let end = Date().addingTimeInterval(5)
        while app.host == nil, Date() < end { try? await Task.sleep(for: .milliseconds(20)) }
        return app
    }

    /// The screen taken by the catalogue's rule (`ScreenTake`: the window at its size, the appearance and language asked
    /// for, its content in place and drawn, keeping still; `ready` says what the screen itself still waits for), its
    /// tree checked, and its screenshot and tree written as `name`. A screen that does not become the one asked for is
    /// not taken, and fails the run (its checks still run on the tree it had); after three, the catalogue stops.
    /// `unreadable` lists the texts known to be drawn in the colour of what is behind them: those are not asked to be
    /// in the picture, and an entry whose text is drawn, or gone, fails the run.
    static func record(_ r: Rendering, name: String, ready: () -> String? = { nil }, unreadable: Unreadable? = nil,
                       known: (Finding) -> Bool = { _ in false }) async throws {
        let nodes: [AXNode]
        var picture: NSBitmapImageRep?
        do {
            let take = try await ScreenTake.take(name, window: r.window, view: r.hosting, size: { r.size }, asked: r.asked, witness: r.witness,
                                                 ready: ready, unreadable: unreadable, frames: { await r.frames() },
                                                 picture: { Pictures.bitmap(of: r.hosting) }, output: output)
            nodes = take.nodes
            picture = take.picture
            if let stale = take.stale { Issue.record(Comment(rawValue: stale)) }
        } catch let notTaken as ScreenNotTaken {
            Issue.record(Comment(rawValue: notTaken.description))
            guard !notTaken.nodes.isEmpty else { return }
            nodes = notTaken.nodes
        }
        if let broken = Guards.tree(nodes, screen: name) { Issue.record(Comment(rawValue: broken)) }
        let findings = Checks.run(nodes, bounds: r.hosting.bounds, text: text).filter { !known($0) }
        #expect(findings.isEmpty, "\(name):\n\(findings.map { "  \($0)" }.joined(separator: "\n"))")
        if let picture { try Pictures.write(picture, tree: nodes, name: name, to: output) }
    }

    /// `<screen>-<variant>[-<language>]`.
    static func name(_ screen: String, _ variant: Variant) -> String {
        language == "en" ? "\(screen)-\(variant.name)" : "\(screen)-\(variant.name)-\(language)"
    }
}

/// A screen drawn off screen: the window and the hosting view.
@MainActor
final class Rendering {
    let window: NSWindow
    let hosting: NSHostingView<AnyView>
    /// The appearance asked for, and what the content says it is drawn in.
    let asked: Asked
    let witness = AppearanceWitness()
    private let height: CGFloat?

    /// Draws `view` at `width` points wide and its own height (or `height`), in `variant`. The appearance is the
    /// window's, as on a Mac set that way: SwiftUI and AppKit both read it from there, and Increase Contrast from
    /// `SystemContrast`, which every rendering tells what its variant asks for, on or off.
    init(_ view: some View, width: CGFloat, height: CGFloat? = nil, variant: Variant, app: AppModel) async {
        asked = Asked(dark: variant.dark, increasedContrast: variant.increasedContrast)
        self.height = height
        SystemContrast.set(variant.increasedContrast)
        let root = view
            .catalogueWitness(witness)
            .environment(app)
            .environment(\.textScale, variant.textSize.scale)
            .defaultAppStorage(Catalogue.defaults)
            .frame(width: width)
            .frame(height: height)
            .fixedSize(horizontal: false, vertical: height == nil)
        hosting = NSHostingView(rootView: AnyView(root))
        window = NSWindow(contentRect: CGRect(x: -30_000, y: -30_000, width: width, height: height ?? 800), styleMask: [.borderless],
                          backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: asked.appearance)
        window.contentView = hosting
        await fit()
    }

    /// Sizes the window to the view, then lets SwiftUI run its updates and tasks.
    func fit() async {
        hosting.layoutSubtreeIfNeeded()
        let size = CGSize(width: window.frame.width, height: max(hosting.fittingSize.height, 40))
        window.setContentSize(size)
        hosting.frame = CGRect(origin: .zero, size: size)
        try? await Task.sleep(for: .milliseconds(350))
        hosting.layoutSubtreeIfNeeded()
        let again = max(hosting.fittingSize.height, 40)
        if abs(again - size.height) > 0.5 {
            window.setContentSize(CGSize(width: size.width, height: again))
            hosting.frame = CGRect(origin: .zero, size: CGSize(width: size.width, height: again))
            try? await Task.sleep(for: .milliseconds(150))
            hosting.layoutSubtreeIfNeeded()
        }
    }

    /// The size the window is to have now: its width, and the height given or the view's own.
    var size: CGSize {
        CGSize(width: window.frame.width, height: height ?? max(hosting.fittingSize.height, 40))
    }

    /// Two display frames, and the window at the view's height after each.
    func frames() async {
        for _ in 0..<2 {
            await SteadyTake.frames(of: hosting, count: 1)
            let wanted = size
            if abs(window.frame.height - wanted.height) > 0.5 || abs(hosting.frame.height - wanted.height) > 0.5 {
                window.setContentSize(wanted)
                hosting.frame = CGRect(origin: .zero, size: wanted)
                hosting.layoutSubtreeIfNeeded()
            }
        }
    }

    func close() {
        window.contentView = nil
        window.close()
    }
}
