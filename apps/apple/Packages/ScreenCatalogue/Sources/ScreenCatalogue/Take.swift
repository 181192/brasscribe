import AppKit
import SwiftUI

/// What was read off a screen at one moment: the first condition that does not hold (nil when all do), and what the
/// screen showed, as text. A take counts only when two readings, one before its picture and one after, both hold and
/// say the same.
public struct Reading: Equatable, Sendable {
    public var unmet: String?
    public var state: String
    public init(unmet: String? = nil, state: String = "") { self.unmet = unmet; self.state = state }
}

/// A screen that did not reach its conditions in time: the catalogue fails instead of keeping a picture of something
/// else.
public struct ScreenNotTaken: Error, CustomStringConvertible, Sendable {
    public let screen: String
    /// The condition it waited for last.
    public let waitedFor: String
    public let tries: Int
    public let seconds: Double
    /// The tree as it was last read, when there was one: the screen's checks still run on it.
    public var nodes: [AXNode] = []
    public var description: String {
        "screen not taken: \(screen): \(waitedFor) (\(tries) tries in \(String(format: "%.1f", seconds)) s)"
    }
}

/// The catalogue stopped: so many screens were not taken that the rest are not tried. Each waits up to the rule's
/// bound, and a catalogue in which nothing can be taken would otherwise run into its job's time limit.
public struct CatalogueStopped: Error, CustomStringConvertible, Sendable {
    public let notTaken: Int
    public var description: String { "catalogue stopped: \(notTaken) screens were not taken, so the rest are not tried" }
}

/// How many screens may be not taken before the catalogue stops, and how many were so far.
public struct NotTakenLimit: Sendable {
    public let limit: Int
    public private(set) var count = 0
    public init(limit: Int = 3) { self.limit = limit }
    /// One more screen was not taken.
    public mutating func note() { count += 1 }
    /// Throws `CatalogueStopped` once the limit is reached: the next screen is not tried.
    public func check() throws { if count >= limit { throw CatalogueStopped(notTaken: count) } }
}

/// The rule for one screenshot (README, Screen catalogue): the picture is the last of `takes` takes in a row with the
/// same pixels, each taken after two display frames, with the screen's conditions read before and after it and the
/// same both times. A screen that does not get there within `bound` seconds is not taken.
@MainActor
public enum SteadyTake {
    public struct Rule: Sendable {
        public var takes: Int
        public var bound: TimeInterval
        public init(takes: Int = 5, bound: TimeInterval = 30) { self.takes = takes; self.bound = bound }
    }

    public struct Taken {
        public let picture: NSBitmapImageRep
        public let tries: Int
        public let seconds: Double
        /// What it waited for on the way, and for how many tries each.
        public let waited: [(condition: String, tries: Int)]
        /// One line for the takes log.
        public func line(_ screen: String) -> String {
            let why = waited.isEmpty ? "" : "; waited for: " + waited.map { "\($0.condition) (\($0.tries))" }.joined(separator: ", ")
            return "\(screen): taken in \(String(format: "%.1f", seconds)) s, \(tries) tries\(why)"
        }
    }

    public static let moved = "it changed while its picture was taken"
    public static let restless = "it does not keep still"

    /// `frames` lets two display frames go by; `read` reads the conditions; `picture` takes the screen's pixels;
    /// `drawn` says what of the reading the picture does not show (nil when it shows all of it). `lastPicture` gets
    /// each picture as it is taken, so a screen that is not taken still leaves its last one to look at.
    public static func take(_ screen: String, rule: Rule = Rule(), now: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
                            frames: () async -> Void, read: () -> Reading, picture: () -> NSBitmapImageRep,
                            drawn: (NSBitmapImageRep) -> String? = { _ in nil },
                            lastPicture: (NSBitmapImageRep) -> Void = { _ in }) async throws -> Taken {
        let start = now()
        var tries = 0, run = 0
        var last: Data?
        var waited: [(condition: String, tries: Int)] = []
        func wait(_ condition: String) {
            if let i = waited.firstIndex(where: { $0.condition == condition }) { waited[i].tries += 1 } else { waited.append((condition, 1)) }
            // the last one waited for is the one a screen that is not taken names
            if let i = waited.firstIndex(where: { $0.condition == condition }), i != waited.count - 1 { waited.append(waited.remove(at: i)) }
            run = 0
            last = nil
        }
        repeat {
            tries += 1
            await frames()
            let before = read()
            if let unmet = before.unmet { wait(unmet); continue }
            let rep = picture()
            lastPicture(rep)
            let after = read()
            if let unmet = after.unmet { wait(unmet); continue }
            if after != before { wait(moved); continue }
            if let missing = drawn(rep) { wait(missing); continue }
            let pixels = Pictures.pixels(rep)
            if pixels == last {
                run += 1
            } else {
                if last != nil { wait(restless) }
                run = 1
                last = pixels
            }
            if run >= rule.takes { return Taken(picture: rep, tries: tries, seconds: now() - start, waited: waited) }
        } while now() - start < rule.bound
        throw ScreenNotTaken(screen: screen, waitedFor: waited.last?.condition ?? restless, tries: tries, seconds: now() - start)
    }

    /// Two display frames of `view`'s window, which is never on a screen and so has no display link: for each, the
    /// main run loop turns (SwiftUI runs its updates and its tasks), then the layout, the drawing and the layer tree
    /// are committed.
    public static func frames(of view: NSView, count: Int = 2, pause: Duration = .milliseconds(50)) async {
        for _ in 0..<count {
            try? await Task.sleep(for: pause)
            view.layoutSubtreeIfNeeded()
            view.displayIfNeeded()
            CATransaction.flush()
        }
    }
}

/// One screen of a catalogue, taken by the rule: its picture and the tree read beside it.
@MainActor
public struct ScreenTake {
    public let picture: NSBitmapImageRep
    public let nodes: [AXNode]
    /// The entries of `unreadable` for this screen that name no text falling short in the picture, as a finding, or nil.
    public let stale: String?

    /// The screens not taken so far in this process: after three, the catalogue stops.
    public private(set) static var notTaken = NotTakenLimit()

    /// Takes `view`, the content of `window`, once it is the screen asked for and keeps still (`SteadyTake`), reading
    /// before and after each picture: the window and its size (`size`, read each time, for a window that follows its
    /// content), the appearance and language (`asked`, `witness`), the screen's own readiness (`ready`: what it still
    /// waits for, or nil; `shows`: the same, asked of the tree) and its content (`Conditions.content`); and in each
    /// picture, that its texts are drawn and can be read (7:1 to their ground under Increase Contrast, 4.5:1
    /// otherwise), but for those `unreadable` names for this screen.
    /// `frames` lets two display frames go by; before each, the process is told again what contrast this screen asked
    /// for (a view of another suite, drawn meanwhile, may have asked for its own). A line goes to
    /// `takes-<language>.log` in `output`; a screen that is not taken leaves its last picture in `not-taken/` there
    /// and throws `ScreenNotTaken` with the tree it last read. After three screens were not taken (`notTaken`), no
    /// screen is tried and `CatalogueStopped` is thrown.
    public static func take(_ name: String, window: NSWindow, view: NSView, size: () -> CGSize, asked: Asked, witness: AppearanceWitness,
                            controls: Bool = true, busyExpected: Bool = false, ready: () -> String? = { nil },
                            shows: ([AXNode]) -> String? = { _ in nil }, unreadable: Unreadable? = nil, rule: SteadyTake.Rule = SteadyTake.Rule(),
                            frames: (() async -> Void)? = nil, picture: () -> NSBitmapImageRep, output: URL) async throws -> ScreenTake {
        try notTaken.check()
        var nodes: [AXNode] = []
        var last: NSBitmapImageRep?
        let language = Bundle.main.preferredLocalizations.first ?? "en"
        let minimum = Conditions.minimumContrast(increased: asked.increasedContrast)
        func read() -> Reading {
            let wanted = size()
            if let unmet = Conditions.window(window, shows: view, at: wanted) ?? Conditions.appearance(asked, window: window, witness: witness)
                ?? ready() { return Reading(unmet: unmet) }
            nodes = AXTree.read(view)
            return Reading(unmet: Conditions.content(nodes, controls: controls, busyExpected: busyExpected) ?? shows(nodes),
                           state: "\(wanted.width) × \(wanted.height)\n" + Conditions.state(nodes))
        }
        do {
            let taken = try await SteadyTake.take(name, rule: rule, frames: {
                SystemContrast.set(asked.increasedContrast)
                if let frames { await frames() } else { await SteadyTake.frames(of: view) }
            }, read: read, picture: picture, drawn: {
                Conditions.drawn($0, nodes: nodes, bounds: view.bounds, minimum: minimum,
                                 unreadable: unreadable?.covers(name, in: nodes) ?? { _ in false })
            }, lastPicture: { last = $0 })
            Pictures.log(taken.line(name), to: output, language: language)
            let stale = unreadable?.stale(name, picture: taken.picture, nodes: nodes, bounds: view.bounds, minimum: minimum)
            if let stale { Pictures.log(stale, to: output, language: language) }
            return ScreenTake(picture: taken.picture, nodes: nodes, stale: stale)
        } catch var failed as ScreenNotTaken {
            notTaken.note()
            Pictures.log(failed.description, to: output, language: language)
            if let last { try? Pictures.write(last, tree: nodes, name: name, to: output.appending(path: "not-taken", directoryHint: .isDirectory)) }
            failed.nodes = nodes
            throw failed
        }
    }
}

/// The appearance and language a screen is asked in.
public struct Asked: Sendable, Equatable {
    public var dark: Bool
    public var increasedContrast: Bool
    /// The run's language ("en", "nb"), when the run says which it is meant to be (`CATALOGUE_LANGUAGE`).
    public var language: String?
    public init(dark: Bool = false, increasedContrast: Bool = false, language: String? = Asked.runLanguage) {
        self.dark = dark; self.increasedContrast = increasedContrast; self.language = language
    }

    /// CATALOGUE_LANGUAGE (TEST_RUNNER_CATALOGUE_LANGUAGE on the xcodebuild line): the language the script asked for.
    public static var runLanguage: String? {
        ProcessInfo.processInfo.environment["CATALOGUE_LANGUAGE"].flatMap { $0.isEmpty ? nil : $0 }
    }

    /// The AppKit appearance of the window: Increase Contrast gives the system's high-contrast one.
    public var appearance: NSAppearance.Name {
        increasedContrast ? (dark ? .accessibilityHighContrastDarkAqua : .accessibilityHighContrastAqua) : (dark ? .darkAqua : .aqua)
    }
}

/// What the content of a window sees: a view in it (`catalogueWitness`) writes down its colour scheme and contrast
/// each time SwiftUI draws it, from the environment where the screen's own views are (inside a split view's column
/// or a navigation stack, which get theirs from AppKit and not from the window's root view).
@MainActor
public final class AppearanceWitness {
    public fileprivate(set) var dark: Bool?
    public fileprivate(set) var increasedContrast: Bool?
    public init() {}
}

private struct WitnessView: View {
    @Environment(\.colorScheme) private var scheme
    @Environment(\.colorSchemeContrast) private var contrast
    let witness: AppearanceWitness

    var body: some View {
        // Written while SwiftUI draws: the reading is of the frame it draws.
        let _ = note()
        Color.clear.frame(width: 0, height: 0).accessibilityHidden(true)
    }

    private func note() {
        witness.dark = scheme == .dark
        witness.increasedContrast = contrast == .increased
    }
}

public extension View {
    /// Has `witness` say what appearance this view is drawn in.
    func catalogueWitness(_ witness: AppearanceWitness) -> some View { background(WitnessView(witness: witness)) }
}

/// Increase Contrast for the process, as System Settings › Accessibility › Display sets it for the Mac. SwiftUI reads
/// the setting from `NSWorkspace` in every hosting view (a split view's columns, a list's rows and a form's each have
/// their own), so an environment value on the root view reaches only what the root draws itself. From the first view
/// a test draws off screen, `NSWorkspace.accessibilityDisplayShouldIncreaseContrast` answers in this process what the
/// last such view asked for, on or off, whatever the Mac's own setting, and each change is announced as the system
/// announces one. Nothing outside the test process is changed. `Guards.contrast` checks that it still works.
@MainActor
public enum SystemContrast {
    nonisolated(unsafe) fileprivate static var asked: Bool?

    private static let installed: Void = {
        let workspace: AnyClass = NSWorkspace.self
        guard let system = class_getInstanceMethod(workspace, #selector(getter: NSWorkspace.accessibilityDisplayShouldIncreaseContrast)),
              let ours = class_getInstanceMethod(workspace, #selector(getter: NSWorkspace.catalogueIncreaseContrast)) else { return }
        method_exchangeImplementations(system, ours)
    }()

    /// What the process is told from now on. Every off-screen host says what it asks for when it is made, so a Mac
    /// with Increase Contrast on draws the light and dark variants without it; the answer stays until the next host
    /// asks. A take says it again before each of its frames.
    public static func set(_ increased: Bool) {
        guard asked != increased else { return }
        _ = installed
        asked = increased
        NSWorkspace.shared.notificationCenter.post(name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: NSWorkspace.shared)
    }

    /// What the process is told now.
    public static var reported: Bool { NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast }
}

extension NSWorkspace {
    /// Stands in for `accessibilityDisplayShouldIncreaseContrast` once `SystemContrast` is installed; the two are
    /// exchanged, so calling itself reaches the system's own answer.
    @objc dynamic var catalogueIncreaseContrast: Bool { SystemContrast.asked ?? catalogueIncreaseContrast }
}

/// The conditions of a take, each returning what does not hold yet, or nil.
@MainActor
public enum Conditions {
    /// `view` is the content of `window`, shown, at `size`.
    public static func window(_ window: NSWindow, shows view: NSView, at size: CGSize) -> String? {
        if view.window !== window || window.contentView !== view { return "its view is not in its window" }
        if view.isHiddenOrHasHiddenAncestor { return "its view is hidden" }
        let content = window.contentRect(forFrameRect: window.frame).size
        if abs(content.width - size.width) > 0.5 || abs(content.height - size.height) > 0.5 {
            return "its window is \(Int(content.width)) × \(Int(content.height)), not \(Int(size.width)) × \(Int(size.height))"
        }
        if abs(view.bounds.width - size.width) > 0.5 || abs(view.bounds.height - size.height) > 0.5 {
            return "its view is \(Int(view.bounds.width)) × \(Int(view.bounds.height)), not \(Int(size.width)) × \(Int(size.height))"
        }
        return nil
    }

    /// The window's effective appearance, the process's Increase Contrast, what the content sees and the run's
    /// language are what was asked.
    public static func appearance(_ asked: Asked, window: NSWindow, witness: AppearanceWitness,
                                  language: String = Bundle.main.preferredLocalizations.first ?? "en") -> String? {
        let names: [NSAppearance.Name] = [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua]
        let effective = window.effectiveAppearance.bestMatch(from: names)
        return appearance(asked, effective: effective, systemContrast: SystemContrast.reported, seenDark: witness.dark,
                          seenContrast: witness.increasedContrast, language: language)
    }

    /// The same, on readings given by hand.
    public nonisolated static func appearance(_ asked: Asked, effective: NSAppearance.Name?, systemContrast: Bool, seenDark: Bool?,
                                              seenContrast: Bool?, language: String) -> String? {
        if effective != asked.appearance { return "its window's appearance is \(effective?.rawValue ?? "unknown"), not \(asked.appearance.rawValue)" }
        if systemContrast != asked.increasedContrast { return "Increase Contrast is \(systemContrast ? "on" : "off") for the process" }
        guard let seenDark, let seenContrast else { return "its content is not drawn yet" }
        if seenDark != asked.dark { return "its content is drawn \(seenDark ? "dark" : "light")" }
        if seenContrast != asked.increasedContrast { return "its content is drawn with \(seenContrast ? "increased" : "standard") contrast" }
        if let wanted = asked.language, wanted != language { return "the run is in \(language), not \(wanted)" }
        return nil
    }

    /// The content is in place, as far as the tree says: it has the screen's controls (or words), and nothing is
    /// still loading (a spinner). `busyExpected` for a screen that shows a spinner when it is ready.
    public nonisolated static func content(_ nodes: [AXNode], controls: Bool = true, busyExpected: Bool = false) -> String? {
        let named = nodes.contains { !$0.words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if controls ? !nodes.contains(where: \.isActionable) : !named { return "its content is not there yet" }
        if !busyExpected, nodes.contains(where: { $0.role == "AXBusyIndicator" }) { return "it is still loading (a spinner)" }
        return nil
    }

    /// The tree as text: two readings with the same text have the same elements with the same words in the same places.
    public nonisolated static func state(_ nodes: [AXNode]) -> String { nodes.map(\.description).joined(separator: "\n") }

    /// The least contrast a text must have with its ground: 7:1 under Increase Contrast (WCAG 1.4.6), 4.5:1 otherwise
    /// (1.4.3). The tree does not say how large a text is, so large text gets no lower bar of its own.
    public nonisolated static func minimumContrast(increased: Bool) -> Double { increased ? 7 : 4.5 }

    /// The picture shows the tree's texts so that they can be read: every text in view has something drawn in its
    /// frame, with at least `minimum` contrast to the ground it is drawn on. A window that has not drawn yet, or a
    /// list whose rows have their words in the tree before they are on the screen, has frames of one flat colour.
    /// `unreadable` names texts known to fall short (`Unreadable`).
    public static func drawn(_ rep: NSBitmapImageRep, nodes: [AXNode], bounds: CGRect, minimum: Double = 4.5,
                             unreadable: (AXNode) -> Bool = { _ in false }) -> String? {
        if Pictures.isFlat(rep, in: CGRect(x: 0, y: 0, width: rep.pixelsWide, height: rep.pixelsHigh)) { return "nothing is drawn in its picture yet" }
        let missing = undrawn(rep, nodes: nodes, bounds: bounds).filter { !unreadable($0) }.map { Unreadable.text(of: $0, in: nodes).description }
        // All of them, each as `Unreadable` would name it, so that a screen that is not taken says everything it lacks in one run.
        if !missing.isEmpty {
            return "its text\(missing.count == 1 ? "" : "s") \(missing.prefix(24).joined(separator: ", ")) \(missing.count == 1 ? "is" : "are") not drawn in its picture yet"
        }
        let faint = faint(rep, nodes: nodes, bounds: bounds, minimum: minimum).filter { !unreadable($0.node) }
        if faint.isEmpty { return nil }
        let least = ratio(minimum)
        let named = faint.prefix(24).map { f in (name: Unreadable.text(of: f.node, in: nodes).description, ratio: f.ratio.map(ratio)) }
        if named.count == 1, let one = named.first {
            return one.ratio.map { "its text \(one.name) is \($0) on its ground, under \(least)" }
                ?? "its text \(one.name) has no ground drawn behind it, so nothing gives it \(least)"
        }
        return "its texts \(named.map { "\($0.name) (\($0.ratio ?? "no ground drawn behind it"))" }.joined(separator: ", ")) are under \(least) on their ground"
    }

    /// A contrast ratio as it is written: "4.65:1", "4.5:1", "7:1".
    public nonisolated static func ratio(_ value: Double) -> String {
        let hundredths = Int((value * 100).rounded())
        let decimals = hundredths % 100 == 0 ? "" : hundredths % 10 == 0 ? ".\(hundredths % 100 / 10)" : String(format: ".%02d", hundredths % 100)
        return "\(hundredths / 100)\(decimals):1"
    }

    /// The texts in view, each with its frame in the picture's pixels.
    private static func textsInView(_ rep: NSBitmapImageRep, nodes: [AXNode], bounds: CGRect) -> [(node: AXNode, pixels: CGRect)] {
        let scale = CGFloat(rep.pixelsWide) / max(bounds.width, 1)
        // A text under something docked over its scroll area (a sheet's footer) is in the tree and not in the picture.
        let docked = nodes.filter { !$0.inScrollArea && !$0.isText && $0.isLeaf && $0.frame.width >= 1 && $0.frame.height >= 1 }
        return nodes.compactMap { n in
            guard n.isText, !n.words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            let frame = n.frame.intersection(bounds)
            guard frame.width >= 4, frame.height >= 4, n.viewport.map({ $0.contains(n.frame) }) ?? true else { return nil }
            if n.inScrollArea, docked.contains(where: { $0.frame.intersects(n.frame) }) { return nil }
            return (n, CGRect(x: frame.minX * scale, y: frame.minY * scale, width: frame.width * scale, height: frame.height * scale))
        }
    }

    /// The texts in view that have nothing drawn in their frame in the picture.
    public static func undrawn(_ rep: NSBitmapImageRep, nodes: [AXNode], bounds: CGRect) -> [AXNode] {
        textsInView(rep, nodes: nodes, bounds: bounds).filter { Pictures.isFlat(rep, in: $0.pixels) }.map(\.node)
    }

    /// The texts in view that are drawn with less than `minimum` contrast to their ground, each with the ratio measured
    /// in the picture (`Pictures.contrast`, to two decimals, as it is reported); nil for a text whose ground is not in
    /// the picture.
    public static func faint(_ rep: NSBitmapImageRep, nodes: [AXNode], bounds: CGRect, minimum: Double) -> [(node: AXNode, ratio: Double?)] {
        textsInView(rep, nodes: nodes, bounds: bounds).compactMap { text in
            if Pictures.isFlat(rep, in: text.pixels) { return nil }
            guard let measured = Pictures.contrast(rep, in: text.pixels) else { return (text.node, nil) }
            let ratio = (measured * 100).rounded() / 100
            return ratio < minimum ? (text.node, ratio) : nil
        }
    }
}

/// Texts known not to be readable in their picture (drawn in the colour of what is behind them, or with less contrast
/// than is asked for), under one issue: for each screen (with its variant), each such text by its exact words, and by
/// which of the screen's texts with those words it is when there are several. Those texts, and no others, are not
/// asked to be readable in the screen's picture. The list is of the macOS the catalogue is taken on in CI. An entry
/// that names no text falling short in the picture (the text can be read, or is not in the tree) is stale and fails
/// the run (`stale`), so the list cannot outlive the fault it stands for.
public struct Unreadable: Sendable {
    /// One text: its words, and which of the texts with those words in the tree's order (1, the first).
    public struct Text: Sendable, Hashable, ExpressibleByStringLiteral, CustomStringConvertible {
        public let words: String
        public let nth: Int
        public init(_ words: String, nth: Int = 1) { self.words = words; self.nth = nth }
        public init(stringLiteral value: String) { self.init(value) }
        public var description: String { nth == 1 ? "“\(words)”" : "“\(words)” (nth: \(nth))" }
    }

    public let issue: String
    public let screens: [String: [Text]]
    public init(issue: String, screens: [String: [Text]]) { self.issue = issue; self.screens = screens }

    /// How an entry would name `node`: its words, and its place among the tree's texts with the same words.
    public static func text(of node: AXNode, in nodes: [AXNode]) -> Text {
        let same = nodes.filter { $0.isText && $0.words == node.words }
        let place = same.firstIndex { $0.role == node.role && $0.frame == node.frame } ?? 0
        return Text(node.words, nth: place + 1)
    }

    /// Whether a text of `screen`, in the tree `nodes`, is one an entry names.
    public func covers(_ screen: String, in nodes: [AXNode]) -> (AXNode) -> Bool {
        let listed = Set(screens[screen] ?? [])
        if listed.isEmpty { return { _ in false } }
        return { node in node.isText && listed.contains(Self.text(of: node, in: nodes)) }
    }

    /// The entries of `screen` that name no text falling short in `picture` (not drawn, or under `minimum`): what to
    /// take out of the list, or nil.
    @MainActor
    public func stale(_ screen: String, picture: NSBitmapImageRep, nodes: [AXNode], bounds: CGRect, minimum: Double = 4.5) -> String? {
        guard let listed = screens[screen] else { return nil }
        let short = Conditions.undrawn(picture, nodes: nodes, bounds: bounds)
            + Conditions.faint(picture, nodes: nodes, bounds: bounds, minimum: minimum).map(\.node)
        let missing = Set(short.map { Self.text(of: $0, in: nodes) })
        let stale = listed.filter { !missing.contains($0) }
        return stale.isEmpty ? nil
            : "\(screen): listed as unreadable (\(issue)), but readable or not on the screen: \(stale.map(\.description).joined(separator: ", ")). Take \(stale.count == 1 ? "it" : "them") out of the list."
    }
}
