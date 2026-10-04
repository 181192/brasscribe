import AppKit

/// What a check found on a screen.
public struct Finding: CustomStringConvertible, Hashable, Sendable {
    public enum Kind: String, Sendable {
        case unlabelled = "no name", smallTarget = "target under 24 × 24 pt", clippedText = "text cut off",
             outOfOrder = "out of reading order", outsideWindow = "outside the window"
    }
    public let kind: Kind
    public let node: String
    public init(kind: Kind, node: String) { self.kind = kind; self.node = node }
    public var description: String { "\(kind.rawValue): \(node)" }
}

/// The checks on one screen in one variant: every control has a name, a target of at least 24 × 24 pt (WCAG 2.5.8),
/// no text cut off or out of the window, and the controls in reading order.
@MainActor
public enum Checks {
    public static func run(_ nodes: [AXNode], bounds: CGRect, text: TextFit) -> [Finding] {
        var found: [Finding] = []
        let shown = nodes.filter { $0.frame.width >= 1 && $0.frame.height >= 1 }
        // A control a scroll area has under one docked over it (a sheet's footer) is out of view, not crowded.
        let docked = shown.filter { $0.isActionable && !$0.inScrollArea }
        let controls = shown.filter { n in n.isActionable && !(n.inScrollArea && docked.contains { $0.frame.intersects(n.frame) }) }
        for n in controls {
            if n.label.trimmingCharacters(in: .whitespaces).isEmpty && n.role != "AXTextField" && n.role != "AXSlider" {
                found.append(Finding(kind: .unlabelled, node: n.description))
            }
            if isSmall(n, among: controls) { found.append(Finding(kind: .smallTarget, node: n.description)) }
        }
        for n in shown where n.role == "AXImage" && n.words.isEmpty {
            found.append(Finding(kind: .unlabelled, node: n.description))
        }
        // What a scroll area has out of view is not out of the window.
        for n in shown where !n.inScrollArea && !bounds.insetBy(dx: -1, dy: -1).contains(n.frame) {
            found.append(Finding(kind: .outsideWindow, node: n.description))
        }
        for n in shown where n.isText && text.isCut(n.words, in: n.frame) {
            found.append(Finding(kind: .clippedText, node: n.description))
        }
        found += order(controls)
        return found
    }

    /// The app's own buttons, menus and links must be at least 24 × 24 pt. The system's standard controls (a switch,
    /// a checkbox, a radio button, a text field) keep the sizes macOS draws them at, under WCAG 2.5.8's spacing
    /// exception: a circle of 24 pt across on each undersized one touches no other control and no other such circle.
    public nonisolated static let ownControls: Set<String> = ["AXButton", "AXMenuButton", "AXPopUpButton", "AXLink"]

    public nonisolated static func isSmall(_ n: AXNode, among controls: [AXNode]) -> Bool {
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

    /// The controls in the order VoiceOver and the keyboard go through them (`AXTree` reads the navigation order),
    /// against the order they are read: a control that comes after one below it in the same column, or after one to its
    /// right on the same line, is out of order. This is not a Tab walk: SwiftUI moves focus only in a key window on a screen.
    public nonisolated static func order(_ controls: [AXNode]) -> [Finding] {
        var found: [Finding] = []
        for (a, b) in zip(controls, controls.dropFirst()) {
            // Only within a column: from a sidebar to the content beside it is not going back up.
            let sameColumn = min(a.frame.maxX, b.frame.maxX) - max(a.frame.minX, b.frame.minX) > 0
            let above = sameColumn && b.frame.maxY <= a.frame.minY - 2
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
/// font. Every font the text could be in (the system font in four weights, and the app's own `fonts`, at every size in
/// `sizes` whose line height fits the frame's height a whole number of times) is tried; the text is cut only when it
/// fits the frame in none of them. A text SwiftUI cut off with "…" keeps its whole words in the tree, so they need more
/// room than its frame has. Only a text of one line is found cut this way; a text of several lines cut at its last one
/// is not (see `isCut`).
@MainActor
public struct TextFit {
    private struct Face { let font: NSFont; let lineHeight: CGFloat }
    private let faces: [Face]
    /// The tallest frame judged as one line of text.
    static let tallestLine: CGFloat = 32

    /// `fonts`: PostScript names of the app's own faces (registered in the process, as the app's bundle does).
    public init(fonts: [String] = [], sizes: ClosedRange<CGFloat> = 10...56) {
        var all: [NSFont] = []
        for tenth in stride(from: Int(sizes.lowerBound * 10), through: Int(sizes.upperBound * 10), by: 5) {
            let size = CGFloat(tenth) / 10
            for weight in [NSFont.Weight.regular, .medium, .semibold, .bold] { all.append(.systemFont(ofSize: size, weight: weight)) }
            for name in fonts { if let f = NSFont(name: name, size: size) { all.append(f) } }
        }
        faces = all.map { Face(font: $0, lineHeight: ceil($0.ascender - $0.descender + $0.leading)) }
    }

    public func isCut(_ text: String, in frame: CGRect) -> Bool {
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
                // A frame taller than a line of text at most 26 pt is as likely a line with room around it (a frame or
                // padding on the text) as one big line, so it is not taken as evidence.
                if frame.height <= Self.tallestLine { cut = true }
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
