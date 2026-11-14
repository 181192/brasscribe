#if os(iOS)
import SwiftUI
import UIKit

/// A text size and appearance a phone's screen is asked in.
public struct PhoneAsked: Sendable, Equatable {
    public var dark: Bool
    public var textSize: DynamicTypeSize
    /// The phone on its side.
    public var landscape: Bool
    /// The run's language ("en", "nb"), when the run says which it is meant to be (`CATALOGUE_LANGUAGE`).
    public var language: String?
    public init(dark: Bool = false, textSize: DynamicTypeSize = .large, landscape: Bool = false, language: String? = Asked.runLanguage) {
        self.dark = dark; self.textSize = textSize; self.landscape = landscape; self.language = language
    }

    /// "dark-xxl-landscape": the variant's part of a screenshot's name ("light" for the plain one).
    public var name: String {
        ([dark ? "dark" : "light"] + (textSize == .large ? [] : [textSize == .xxLarge ? "xxl" : "\(textSize)"])
            + (landscape ? ["landscape"] : [])).joined(separator: "-")
    }

    var category: UIContentSizeCategory {
        switch textSize {
        case .xSmall: .extraSmall
        case .small: .small
        case .medium: .medium
        case .large: .large
        case .xLarge: .extraLarge
        case .xxLarge: .extraExtraLarge
        case .xxxLarge: .extraExtraExtraLarge
        case .accessibility1: .accessibilityMedium
        case .accessibility2: .accessibilityLarge
        case .accessibility3: .accessibilityExtraLarge
        case .accessibility4: .accessibilityExtraExtraLarge
        default: .accessibilityExtraExtraExtraLarge
        }
    }
}

/// One screen in a window of its own, over the test host's, filling the phone's screen with its real safe areas, at the
/// text size and appearance asked (as trait overrides of the window, so the navigation bar and sheets get them too).
@MainActor
public final class PhoneHost {
    public let window: UIWindow
    public let hosting: UIViewController
    public let asked: PhoneAsked
    private let witness = AppearanceWitness()

    public init(_ view: some View, asked: PhoneAsked) {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first!
        self.asked = asked
        window = UIWindow(windowScene: scene)
        hosting = UIHostingController(rootView: AnyView(view.catalogueWitness(witness)))
        window.overrideUserInterfaceStyle = asked.dark ? .dark : .light
        window.traitOverrides.preferredContentSizeCategory = asked.category
        window.windowLevel = .alert + 1
        window.rootViewController = hosting
        window.makeKeyAndVisible()
    }

    /// The phone turned to `landscape` (on its side) or upright, as the screen's own geometry: the safe areas are the
    /// phone's. Waits until the scene has turned.
    public static func turn(landscape: Bool) async {
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first else { return }
        scene.requestGeometryUpdate(.iOS(interfaceOrientations: landscape ? .landscapeRight : .portrait)) { _ in }
        for _ in 0..<50 where scene.effectiveGeometry.interfaceOrientation.isLandscape != landscape {
            try? await Task.sleep(for: .milliseconds(100))
        }
        try? await Task.sleep(for: .milliseconds(300))
    }

    /// Two display frames: the run loop turns, then the layout and the layer tree are committed.
    public func frames(count: Int = 2) async {
        for _ in 0..<count {
            try? await Task.sleep(for: .milliseconds(50))
            window.layoutIfNeeded()
            CATransaction.flush()
        }
    }

    /// Lets the screen settle for `seconds` (animations, tasks that load it).
    public func settle(_ seconds: TimeInterval = 0.5) async {
        let end = Date().addingTimeInterval(seconds)
        while Date() < end { await frames(count: 1) }
    }

    /// What does not hold yet of the window and appearance asked, or nil.
    func unmet(language: String) -> String? {
        let landscape = window.bounds.width > window.bounds.height
        if window.isHidden { return "its window is not shown" }
        if landscape != asked.landscape { return "the phone is \(landscape ? "on its side" : "upright")" }
        guard let dark = witness.dark, let size = witness.textSize else { return "its content is not drawn yet" }
        if dark != asked.dark { return "its content is drawn \(dark ? "dark" : "light")" }
        if size != asked.textSize { return "its content is drawn at \(size), not \(asked.textSize)" }
        if let wanted = asked.language, wanted != language { return "the run is in \(language), not \(wanted)" }
        return nil
    }

    /// Takes the screen by the catalogue's rule (`SteadyTake`): reading the tree before and after each picture, with
    /// the window and appearance as asked, the screen's own readiness (`ready`, `shows`), and its texts drawn and
    /// readable (4.5:1 to their ground). Writes a line to `takes-<language>.log` in `output`; a screen that is not
    /// taken leaves its last picture in `not-taken/` there and throws `ScreenNotTaken`.
    public func take(_ name: String, controls: Bool = true, ready: () -> String? = { nil }, shows: ([AXNode]) -> String? = { _ in nil },
                     unreadable: Unreadable? = nil, output: URL) async throws -> (picture: Bitmap, nodes: [AXNode]) {
        let language = Bundle.main.preferredLocalizations.first ?? "en"
        var nodes: [AXNode] = []
        var last: Bitmap?
        let bounds = window.bounds
        let minimum = Conditions.minimumContrast(increased: false)
        func read() -> Reading {
            if let unmet = unmet(language: language) ?? ready() { return Reading(unmet: unmet) }
            nodes = AXTree.read(window)
            return Reading(unmet: Conditions.content(nodes, controls: controls) ?? shows(nodes),
                           state: "\(bounds.width) × \(bounds.height)\n" + Conditions.state(nodes))
        }
        do {
            let taken = try await SteadyTake.take(name, frames: { await frames() }, read: read,
                                                  picture: { Pictures.bitmap(of: window)! },
                                                  drawn: { Conditions.drawn($0, nodes: nodes, bounds: bounds, unreadable: unreadable?.covers(name, in: nodes) ?? { _ in false }) },
                                                  readable: { Conditions.readable($0, nodes: nodes, bounds: bounds, minimum: minimum,
                                                                                  unreadable: unreadable?.covers(name, in: nodes) ?? { _ in false }) },
                                                  lastPicture: { last = $0 })
            Pictures.log(taken.line(name), to: output, language: language)
            if let stale = unreadable?.stale(name, picture: taken.picture, nodes: nodes, bounds: bounds, minimum: minimum) {
                Pictures.log(stale, to: output, language: language)
            }
            return (taken.picture, nodes)
        } catch var failed as ScreenNotTaken {
            Pictures.log(failed.description, to: output, language: language)
            if let last { try? Pictures.write(last, tree: nodes, name: name, to: output.appending(path: "not-taken", directoryHint: .isDirectory)) }
            failed.nodes = nodes
            throw failed
        }
    }

    public func close() {
        window.isHidden = true
        window.rootViewController = nil
    }
}
#endif
