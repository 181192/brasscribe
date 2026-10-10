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

    /// CATALOGUE_CHECKS=0 takes the screenshots without failing on findings (the base of a comparison).
    nonisolated static var checks: Bool { ProcessInfo.processInfo.environment["CATALOGUE_CHECKS"] != "0" }

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

    /// The screen's tree, checked, and its screenshot and tree written as `name`.
    static func record(_ r: Rendering, name: String, known: (Finding) -> Bool = { _ in false }) throws {
        let nodes = AXTree.read(r.hosting)
        if let broken = Guards.tree(nodes, screen: name) { Issue.record(Comment(rawValue: broken)) }
        let findings = Checks.run(nodes, bounds: r.hosting.bounds, text: text).filter { !known($0) }
        if checks {
            #expect(findings.isEmpty, "\(name):\n\(findings.map { "  \($0)" }.joined(separator: "\n"))")
        }
        try Pictures.write(Pictures.bitmap(of: r.hosting), tree: nodes, name: name, to: output)
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

    /// Draws `view` at `width` points wide and its own height (or `height`), in `variant`.
    init(_ view: some View, width: CGFloat, height: CGFloat? = nil, variant: Variant, app: AppModel) async {
        let root = view
            .environment(app)
            .environment(\.textScale, variant.textSize.scale)
            .environment(\.colorScheme, variant.dark ? .dark : .light)
            .catalogueContrast(increased: variant.increasedContrast)
            .defaultAppStorage(Catalogue.defaults)
            .frame(width: width)
            .frame(height: height)
            .fixedSize(horizontal: false, vertical: height == nil)
        hosting = NSHostingView(rootView: AnyView(root))
        window = NSWindow(contentRect: CGRect(x: -30_000, y: -30_000, width: width, height: height ?? 800), styleMask: [.borderless],
                          backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: variant.dark ? .darkAqua : .aqua)
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

    /// Settles until `done` holds, or the timeout.
    func settle(until done: () -> Bool, timeout: TimeInterval = 5) async {
        let end = Date().addingTimeInterval(timeout)
        while !done(), Date() < end { try? await Task.sleep(for: .milliseconds(30)) }
        await fit()
    }

    func close() {
        window.contentView = nil
        window.close()
    }
}
