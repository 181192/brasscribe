import AppKit
import SwiftUI
import Testing
@testable import Brasscribe_Bandroom

// The screen catalogue's machinery: every screen drawn off screen in each variant, its accessibility tree read
// in-process, the checks run on it, and a screenshot written (README, Testing). Nothing here shows a window: the
// views are drawn by an NSHostingView in a borderless window that is never ordered in, far off any screen.

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

    /// The pixels per point of every screenshot, whatever the screens of the machine: a Mac with a Retina display and a
    /// CI runner without one take the same pictures.
    static let scale: CGFloat = 2

    /// CATALOGUE_CHECKS=0 takes the screenshots without failing on findings (the base of a comparison).
    nonisolated static var checks: Bool { ProcessInfo.processInfo.environment["CATALOGUE_CHECKS"] != "0" }

    private static var prepared = false

    /// Once per run: the accessibility tree in-process, and the language checked.
    static func prepare() {
        guard !prepared else { return }
        prepared = true
        // SwiftUI builds its accessibility tree only for an assistive client. This attribute, which VoiceOver sets on an
        // app, asks for it in this process. It is not documented: `AXSnapshot.read` fails loudly when it stops working.
        NSApp.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    }

    /// A model of its own, on canned engine answers (`DemoEngine`): BANDROOM_DEMO is read when it is made.
    static func model(busy: Bool, request: Bool = false) async -> AppModel {
        prepare()
        setenv("BANDROOM_DEMO", busy ? "busy" : "idle", 1)
        if request { setenv("BANDROOM_DEMO_REQUEST", "1", 1) } else { unsetenv("BANDROOM_DEMO_REQUEST") }
        let app = AppModel(defaults: defaults)
        app.launch()
        await app.monitor.refresh()
        await app.monitor.refreshRequests()
        unsetenv("BANDROOM_DEMO_REQUEST")
        // The first sample of this computer (the demo's own) comes from a task of its own.
        let end = Date().addingTimeInterval(5)
        while app.host == nil, Date() < end { try? await Task.sleep(for: .milliseconds(20)) }
        return app
    }
}

/// A screen drawn off screen: the window, the hosting view and the pixels.
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
            // Increased contrast as System Settings › Accessibility › Display sets it. SwiftUI reads the setting only from
            // the window server; this environment key, not documented, is what it sets from it. `ContrastProbe` checks that it
            // still works.
            .environment(\._colorSchemeContrast, variant.increasedContrast ? .increased : .standard)
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

    /// The pixels, at `Catalogue.scale` pixels per point.
    func bitmap() -> NSBitmapImageRep {
        hosting.layoutSubtreeIfNeeded()
        let size = hosting.bounds.size
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * Catalogue.scale), pixelsHigh: Int(size.height * Catalogue.scale),
                                   bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                   bytesPerRow: 0, bitsPerPixel: 0)!
        rep.size = size
        hosting.cacheDisplay(in: hosting.bounds, to: rep)
        return rep
    }

    func close() {
        window.contentView = nil
        window.close()
    }
}

/// One element of the accessibility tree, in the view's coordinates (origin top left).
struct AXNode: CustomStringConvertible {
    let role: String
    let label: String
    let value: String
    let frame: CGRect
    let isLeaf: Bool

    /// What a screen reader says for it: its label, or for text its value.
    var words: String { label.isEmpty ? value : label }
    var description: String { "\(role) “\(words)” \(Int(frame.minX)),\(Int(frame.minY)) \(Int(frame.width))×\(Int(frame.height))" }

    static let actionable: Set<String> = ["AXButton", "AXMenuButton", "AXPopUpButton", "AXCheckBox", "AXRadioButton", "AXLink",
                                          "AXTextField", "AXSlider", "AXDisclosureTriangle", "AXComboBox", "AXIncrementor"]
    var isActionable: Bool { Self.actionable.contains(role) }
    /// Text on its own (a heading made of one text is a heading, not a group of texts).
    var isText: Bool { role == "AXStaticText" || (role == "AXHeading" && isLeaf) }
}

@MainActor
enum AXSnapshot {
    /// The tree under the hosting view, in the order assistive technology reads it.
    static func read(_ r: Rendering) -> [AXNode] {
        var nodes: [AXNode] = []
        // Each attribute by its selector, whatever type the element hands back (a title can be a number).
        func get(_ o: NSObject, _ selector: String) -> Any? {
            let s = NSSelectorFromString(selector)
            guard o.responds(to: s) else { return nil }
            return o.perform(s)?.takeUnretainedValue()
        }
        func text(_ v: Any?) -> String {
            switch v {
            case let s as String: s
            case let a as NSAttributedString: a.string
            case let n as NSNumber: n.stringValue
            default: ""
            }
        }
        func walk(_ element: Any, depth: Int) {
            guard depth < 60, let o = element as? NSObject else { return }
            let children = get(o, "accessibilityChildren") as? [Any] ?? []
            if depth > 0 {
                let role = text(get(o, "accessibilityRole"))
                // The name: its label, its title, or the text that titles it (a switch or a field in a form has it beside it).
                let titledBy = (get(o, "accessibilityTitleUIElement") as? NSObject).map {
                    [text(get($0, "accessibilityLabel")), text(get($0, "accessibilityValue"))].first { !$0.isEmpty } ?? ""
                } ?? ""
                let label = [text(get(o, "accessibilityLabel")), text(get(o, "accessibilityTitle")), titledBy].first { !$0.isEmpty } ?? ""
                let value = text(get(o, "accessibilityValue"))
                let screen = (o as? NSAccessibilityElementProtocol)?.accessibilityFrame() ?? .zero
                nodes.append(AXNode(role: role, label: label, value: value, frame: local(screen, in: r), isLeaf: children.isEmpty))
            }
            // In the order VoiceOver and the keyboard go through them (it follows accessibilitySortPriority), which the
            // plain list of children does not.
            let navigation = get(o, "accessibilityChildrenInNavigationOrder") as? [Any] ?? []
            for c in navigation.isEmpty ? children : navigation { walk(c, depth: depth + 1) }
        }
        walk(r.hosting, depth: 0)
        return nodes
    }

    /// A frame on the screen, in the hosting view's points with the origin at its top left.
    static func local(_ screen: CGRect, in r: Rendering) -> CGRect {
        let inWindow = r.window.convertFromScreen(screen)
        var rect = r.hosting.convert(inWindow, from: nil)
        if !r.hosting.isFlipped { rect.origin.y = r.hosting.bounds.height - rect.maxY }
        return rect
    }
}

/// What a check found on a screen.
struct Finding: CustomStringConvertible, Hashable {
    enum Kind: String { case unlabelled = "no name", smallTarget = "target under 24 × 24 pt", clippedText = "text cut off",
                        outOfOrder = "out of reading order", outsideWindow = "outside the window" }
    let kind: Kind
    let node: String
    var description: String { "\(kind.rawValue): \(node)" }
}

/// The checks on one screen in one variant (README, Testing): every control has a name, a target of at least
/// 24 × 24 pt (WCAG 2.5.8), no text cut off or out of the window, and the controls in reading order.
@MainActor
enum Checks {
    static func run(_ nodes: [AXNode], bounds: CGRect) -> [Finding] {
        var found: [Finding] = []
        let shown = nodes.filter { $0.frame.width >= 1 && $0.frame.height >= 1 }
        for n in shown where n.isActionable {
            if n.label.trimmingCharacters(in: .whitespaces).isEmpty && n.role != "AXTextField" && n.role != "AXSlider" {
                found.append(Finding(kind: .unlabelled, node: n.description))
            }
            if isSmall(n, among: shown.filter(\.isActionable)) {
                found.append(Finding(kind: .smallTarget, node: n.description))
            }
        }
        for n in shown where n.role == "AXImage" && n.words.isEmpty {
            found.append(Finding(kind: .unlabelled, node: n.description))
        }
        for n in shown where !bounds.insetBy(dx: -1, dy: -1).contains(n.frame) {
            found.append(Finding(kind: .outsideWindow, node: n.description))
        }
        for n in shown where n.isText && TextFit.isCut(n.words, in: n.frame) {
            found.append(Finding(kind: .clippedText, node: n.description))
        }
        found += order(shown.filter(\.isActionable))
        return found
    }

    /// The app's own buttons, menus and links must be at least 24 × 24 pt. The system's standard controls (a switch,
    /// a checkbox, a radio button, a text field) keep the sizes macOS draws them at, under WCAG 2.5.8's spacing
    /// exception: a circle of 24 pt across on each undersized one touches no other control and no other such circle.
    static let ownControls: Set<String> = ["AXButton", "AXMenuButton", "AXPopUpButton", "AXLink"]

    static func isSmall(_ n: AXNode, among controls: [AXNode]) -> Bool {
        let undersized = { (c: AXNode) in c.frame.width < 24 - 0.5 || c.frame.height < 24 - 0.5 }
        guard undersized(n) else { return false }
        if ownControls.contains(n.role) { return true }
        let center = CGPoint(x: n.frame.midX, y: n.frame.midY)
        for other in controls where other.frame != n.frame {
            // Two undersized controls: their circles meet when their centres are under 24 pt apart. Another control: the
            // circle meets it when it is under 12 pt from the centre.
            let near = undersized(other) ? CGPoint(x: other.frame.midX, y: other.frame.midY)
                : CGPoint(x: min(max(center.x, other.frame.minX), other.frame.maxX), y: min(max(center.y, other.frame.minY), other.frame.maxY))
            let reach: CGFloat = undersized(other) ? 24 : 12
            if hypot(near.x - center.x, near.y - center.y) < reach - 0.5 { return true }
        }
        return false
    }

    /// The controls in the order VoiceOver and the keyboard go through them (`AXSnapshot` reads the navigation order),
    /// against the order they are read: a control that comes after one below it, or after one to its right on the same
    /// line, is out of order. This is not a Tab walk: SwiftUI moves focus only in a key window on a screen (README).
    static func order(_ controls: [AXNode]) -> [Finding] {
        var found: [Finding] = []
        for (a, b) in zip(controls, controls.dropFirst()) {
            let above = b.frame.maxY <= a.frame.minY - 2
            let overlap = min(a.frame.maxY, b.frame.maxY) - max(a.frame.minY, b.frame.minY)
            let sameLine = overlap > 0.5 * min(a.frame.height, b.frame.height)
            let leftOf = b.frame.maxX <= a.frame.minX + 2
            if above || (sameLine && leftOf) {
                found.append(Finding(kind: .outOfOrder, node: "\(b) comes after \(a)"))
            }
        }
        return found
    }
}

/// Whether a text fits its frame, from the frame alone: the accessibility tree gives the words and the frame, not the
/// font. Every font the text could be in (system or Instrument Serif, any size and weight whose line height fits the
/// frame's height a whole number of times) is tried; the text is cut only when it fits the frame in none of them.
/// A text SwiftUI cut off with "…" keeps its whole words in the tree, so they need more room than its frame has.
/// Only a text of one line is found cut this way; a text of several lines cut at its last one is not (see `isCut`).
@MainActor
enum TextFit {
    private struct Face { let font: NSFont; let lineHeight: CGFloat }

    private static let faces: [Face] = {
        var fonts: [NSFont] = []
        // From the smallest text Bandroom draws (12 pt) less a little, to its largest (40 pt) at its largest text size.
        for tenth in stride(from: 100, through: 560, by: 5) {
            let size = CGFloat(tenth) / 10
            for weight in [NSFont.Weight.regular, .medium, .semibold, .bold] { fonts.append(.systemFont(ofSize: size, weight: weight)) }
            if let serif = NSFont(name: "InstrumentSerif-Regular", size: size) { fonts.append(serif) }
        }
        return fonts.map { Face(font: $0, lineHeight: ceil($0.ascender - $0.descender + $0.leading)) }
    }()

    static func isCut(_ text: String, in frame: CGRect) -> Bool {
        let words = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !words.isEmpty, frame.height >= 6 else { return false }
        var cut = false
        for face in faces {
            let lines = (frame.height / face.lineHeight).rounded()
            // SwiftUI makes a text exactly as tall as its lines; a looser match lets in faces it is not in.
            guard lines >= 1, abs(frame.height - lines * face.lineHeight) <= 1 + 0.5 * lines else { continue }
            let attributed = NSAttributedString(string: words, attributes: [.font: face.font])
            if lines == 1 {
                if attributed.size().width <= frame.width + 1.5 { return false }
                cut = true
            } else {
                // A text of several lines is as wide as its widest line, not as the width it was wrapped at. In a face
                // where its words need as many lines as the frame has at that width, it fits; more, it was wrapped wider;
                // either way it may well be in that face, so it is not called cut. Fewer: the face is too small to be it.
                let needed = attributed.boundingRect(with: CGSize(width: frame.width + 1.5, height: .greatestFiniteMagnitude),
                                                     options: [.usesLineFragmentOrigin, .usesFontLeading]).height
                if (needed / face.lineHeight).rounded() >= lines { return false }
            }
        }
        return cut
    }
}

/// The checks that fail loudly when an undocumented hook the catalogue relies on stops working, instead of letting
/// every screen pass on an empty tree or draw the same picture for both contrasts.
@MainActor
enum Hooks {
    /// The accessibility tree must have the screen's controls in it.
    static func requireTree(_ nodes: [AXNode], scene: String) {
        let controls = nodes.filter(\.isActionable).count
        #expect(controls >= 1,
                "\(scene): the accessibility tree has \(nodes.count) elements and \(controls) controls. Setting AXEnhancedUserInterface on NSApp no longer makes SwiftUI build it in-process (Catalogue.prepare).")
    }

    /// `_colorSchemeContrast` must still set what views read as `colorSchemeContrast`.
    static func requireContrastHook(app: AppModel) async {
        let r = await Rendering(ContrastProbe(), width: 20, height: 20, variant: .contrast, app: app)
        defer { r.close() }
        let rep = r.bitmap()
        let c = rep.colorAt(x: rep.pixelsWide / 2, y: rep.pixelsHigh / 2)?.usingColorSpace(.deviceRGB)
        #expect((c?.redComponent ?? 0) < 0.1 && (c?.greenComponent ?? 1) < 0.1,
                "The increased-contrast variant draws as standard contrast: the _colorSchemeContrast environment key no longer sets colorSchemeContrast.")
    }

    /// Under `-testLanguage nb`, the app's strings must come out in bokmål.
    static func requireLanguage() {
        guard Catalogue.language != "en" else { return }
        #expect(String(localized: "Pair a phone") != "Pair a phone",
                "The run is in \(Catalogue.language), but the app's strings are in English: -testLanguage no longer reaches Bundle.main.")
    }
}

/// Black under increased contrast, white otherwise.
private struct ContrastProbe: View {
    @Environment(\.colorSchemeContrast) private var contrast
    var body: some View { Rectangle().fill(contrast == .increased ? Color.black : Color.white) }
}

/// Writes a screenshot as PNG: `<scene>-<variant>[-<language>].png`.
@MainActor
enum Screenshot {
    static func name(_ scene: String, _ variant: Variant) -> String {
        Catalogue.language == "en" ? "\(scene)-\(variant.name)" : "\(scene)-\(variant.name)-\(Catalogue.language)"
    }

    static func write(_ rep: NSBitmapImageRep, name: String) throws {
        let data = try #require(rep.representation(using: .png, properties: [:]))
        try data.write(to: Catalogue.output.appending(path: "\(name).png"))
    }

    /// The accessibility tree beside it, as the checks read it: `<name>.ax.txt`.
    static func writeTree(_ nodes: [AXNode], name: String) throws {
        try (nodes.map(\.description).joined(separator: "\n") + "\n")
            .write(to: Catalogue.output.appending(path: "\(name).ax.txt"), atomically: true, encoding: .utf8)
    }
}
