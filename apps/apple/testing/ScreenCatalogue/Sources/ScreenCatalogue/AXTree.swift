#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// One element of the accessibility tree, in the view's coordinates (origin top left).
public struct AXNode: CustomStringConvertible, Sendable {
    public let role: String
    public let label: String
    public let value: String
    public let frame: CGRect
    public let isLeaf: Bool
    /// Inside a scroll area, which may have it out of view.
    public let inScrollArea: Bool
    /// The part of the view its scroll area shows (the innermost one's frame, within those around it); nil outside one.
    public let viewport: CGRect?

    public init(role: String, label: String, value: String = "", frame: CGRect, isLeaf: Bool = true, inScrollArea: Bool = false,
                viewport: CGRect? = nil) {
        self.role = role; self.label = label; self.value = value; self.frame = frame; self.isLeaf = isLeaf
        self.inScrollArea = inScrollArea || viewport != nil; self.viewport = viewport
    }

    /// Scrolled out of its scroll area's view: it is there for VoiceOver and the keyboard, and not there to click.
    public var isOutOfView: Bool { viewport.map { !$0.intersects(frame) } ?? false }

    /// Its words: for a text what it shows (a form's value is titled by its row's label), else its name.
    public var words: String { (role == "AXStaticText" && !value.isEmpty) || label.isEmpty ? value : label }
    public var description: String { "\(role) “\(words)” \(Int(frame.minX)),\(Int(frame.minY)) \(Int(frame.width))×\(Int(frame.height))" }

    public static let actionable: Set<String> = ["AXButton", "AXMenuButton", "AXPopUpButton", "AXCheckBox", "AXRadioButton", "AXLink",
                                                 "AXTextField", "AXSlider", "AXDisclosureTriangle", "AXComboBox", "AXIncrementor",
                                                 "AXToolbarButton"]
    public var isActionable: Bool { Self.actionable.contains(role) }
    /// Text on its own (a heading made of one text is a heading, not a group of texts).
    public var isText: Bool { role == "AXStaticText" || (role == "AXHeading" && isLeaf) }
}

#if os(macOS)
@MainActor
public enum AXTree {
    /// SwiftUI builds its accessibility tree only for an assistive client. This attribute, which VoiceOver sets on an app,
    /// asks for it in this process. It is not documented: `Guards.tree` fails loudly when it stops working.
    public static func enableInProcess() {
        NSApp.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
    }

    /// The tree under `view` (in a window), in the order VoiceOver and the keyboard go through it.
    public static func read(_ view: NSView) -> [AXNode] {
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
        func walk(_ element: Any, depth: Int, viewport: CGRect?) {
            guard depth < 60, let o = element as? NSObject else { return }
            let children = get(o, "accessibilityChildren") as? [Any] ?? []
            let role = depth > 0 ? text(get(o, "accessibilityRole")) : ""
            var inner = viewport
            if depth > 0 {
                // The name: its label, its title, or the text that titles it (a switch or a field in a form has it beside it).
                let titledBy = (get(o, "accessibilityTitleUIElement") as? NSObject).map {
                    [text(get($0, "accessibilityLabel")), text(get($0, "accessibilityValue"))].first { !$0.isEmpty } ?? ""
                } ?? ""
                let label = [text(get(o, "accessibilityLabel")), text(get(o, "accessibilityTitle")), titledBy].first { !$0.isEmpty } ?? ""
                let value = text(get(o, "accessibilityValue"))
                let frame = local((o as? NSAccessibilityElementProtocol)?.accessibilityFrame() ?? .zero, in: view)
                nodes.append(AXNode(role: role, label: label, value: value, frame: frame, isLeaf: children.isEmpty, viewport: viewport))
                if role == "AXScrollArea" { inner = viewport.map { $0.intersection(frame) } ?? frame }
            }
            // In the order VoiceOver and the keyboard go through them (it follows accessibilitySortPriority), which the
            // plain list of children does not.
            let navigation = get(o, "accessibilityChildrenInNavigationOrder") as? [Any] ?? []
            for c in navigation.isEmpty ? children : navigation { walk(c, depth: depth + 1, viewport: inner) }
        }
        walk(view, depth: 0, viewport: nil)
        return nodes
    }

    /// A frame on the screen, in `view`'s points with the origin at its top left.
    static func local(_ screen: CGRect, in view: NSView) -> CGRect {
        guard let window = view.window else { return screen }
        var rect = view.convert(window.convertFromScreen(screen), from: nil)
        if !view.isFlipped { rect.origin.y = view.bounds.height - rect.maxY }
        return rect
    }
}

#else
@MainActor
public enum AXTree {
    /// SwiftUI on iOS builds its accessibility tree only for an assistive client or UI automation. libAccessibility's
    /// own switches for them (which the system sets when VoiceOver or an automation session starts) ask for it in this
    /// process. They are not documented: `Guards.tree` fails loudly when they stop working.
    public static func enableInProcess() {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW) else { return }
        typealias Switch = @convention(c) (Int32) -> Void
        for name in ["_AXSSetAutomationEnabled", "_AXSApplicationAccessibilitySetEnabled"] {
            if let sym = dlsym(lib, name) { unsafeBitCast(sym, to: Switch.self)(1) }
        }
    }

    /// The role a Mac would give an element with these traits, so the checks read both platforms alike.
    nonisolated static func role(_ t: UIAccessibilityTraits) -> String {
        if t.contains(.adjustable) { return "AXSlider" }
        if t.contains(.link) { return "AXLink" }
        if t.contains(.searchField) { return "AXTextField" }
        if t.contains(.toggleButton) { return "AXCheckBox" }
        if t.contains(.button) || t.contains(.tabBar) { return "AXButton" }
        if t.contains(.header) { return "AXHeading" }
        if t.contains(.image) { return "AXImage" }
        if t.contains(.staticText) { return "AXStaticText" }
        // No trait of its own: a group, or a control drawn without words of its own (a level, a progress bar).
        return "AXGroup"
    }

    /// The tree under `view` (in a window at the origin of its screen), in the order VoiceOver goes through it (the
    /// navigation bar first), each element in `view`'s points. An element inside a scroll view has what that scroll
    /// view shows as its viewport.
    public static func read(_ view: UIView) -> [AXNode] {
        let origin = view.convert(CGPoint.zero, to: nil)
        var bar: [AXNode] = []
        var rest: [AXNode] = []
        func children(_ e: NSObject) -> [NSObject] {
            let n = e.accessibilityElementCount()
            if n != NSNotFound, n > 0 { return (0..<n).compactMap { e.accessibilityElement(at: $0) as? NSObject } }
            if let els = e.accessibilityElements as? [NSObject] { return els }
            if let v = e as? UIView { return v.subviews.filter { !$0.isHidden && $0.alpha > 0.01 } }
            return []
        }
        /// What holds the element, nearest first: its accessibility containers, then the views they are in.
        func holders(_ e: NSObject) -> [NSObject] {
            var out: [NSObject] = []
            var c: Any? = (e as? UIView)?.superview ?? e.value(forKey: "accessibilityContainer")
            while let o = c as? NSObject, out.count < 40 {
                out.append(o)
                c = (o as? UIView)?.superview ?? o.value(forKey: "accessibilityContainer")
            }
            return out
        }
        func walk(_ e: NSObject, depth: Int) {
            guard depth < 60, !e.accessibilityElementsHidden else { return }
            if e.isAccessibilityElement {
                var frame = e.accessibilityFrame
                frame.origin.x -= origin.x; frame.origin.y -= origin.y
                let around = holders(e)
                let scroller = around.first { $0 is UIScrollView } as? UIScrollView
                let area = scroller.map { $0.convert($0.bounds, to: nil).offsetBy(dx: -origin.x, dy: -origin.y) }
                // A button of the navigation bar is the system's: it takes a finger in more than the frame it reports
                // (36 pt high on iOS 26), so it is told apart from the app's own (`Checks.ownControls`).
                let inBar = around.contains { $0 is UINavigationBar }
                let kind = role(e.accessibilityTraits)
                let node = AXNode(role: inBar && kind == "AXButton" ? "AXToolbarButton" : kind, label: e.accessibilityLabel ?? "",
                                  value: e.accessibilityValue ?? "", frame: frame, isLeaf: true, viewport: area)
                if inBar { bar.append(node) } else { rest.append(node) }
                return
            }
            for c in children(e) { walk(c, depth: depth + 1) }
        }
        walk(view, depth: 0)
        return bar + rest
    }
}
#endif
