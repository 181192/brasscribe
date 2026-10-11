import AppKit
import SwiftUI

/// Black under increased contrast, white otherwise: what `Guards.contrast` draws.
public struct ContrastProbe: View {
    @Environment(\.colorSchemeContrast) private var contrast
    public init() {}
    public var body: some View { Rectangle().fill(contrast == .increased ? Color.black : Color.white) }
}

/// The checks that fail loudly when a hook the catalogue relies on stops working, instead of letting
/// every screen pass on an empty tree or draw the same picture for both contrasts. Each returns what went wrong, or nil.
@MainActor
public enum Guards {
    /// The accessibility tree must have the screen's controls in it (or, for a screen without any, its words: without the
    /// hook SwiftUI hands out one empty group).
    public static func tree(_ nodes: [AXNode], screen: String, controls expected: Bool = true) -> String? {
        let controls = nodes.filter(\.isActionable).count
        let named = nodes.filter { !$0.words.isEmpty }.count
        return controls >= 1 || (!expected && named >= 1) ? nil
            : "\(screen): the accessibility tree has \(nodes.count) elements and \(controls) controls. Setting AXEnhancedUserInterface on NSApp no longer makes SwiftUI build it in-process (AXTree.enableInProcess)."
    }

    /// `ContrastProbe` drawn inside a navigation stack while `SystemContrast` asks for increased contrast, as `rep`,
    /// must be black: a navigation stack's content is in a hosting view of its own, as most of a screen is.
    public static func contrast(_ rep: NSBitmapImageRep) -> String? {
        let c = rep.colorAt(x: rep.pixelsWide / 2, y: rep.pixelsHigh / 2)?.usingColorSpace(.deviceRGB)
        return (c?.redComponent ?? 1) < 0.1 && (c?.greenComponent ?? 1) < 0.1 ? nil
            : "The increased-contrast variant draws as standard contrast: SwiftUI no longer reads Increase Contrast from NSWorkspace.accessibilityDisplayShouldIncreaseContrast (SystemContrast)."
    }

    /// In a run in another language than English, `localized` (an app string looked up in it) must differ from `english`.
    public static func language(_ language: String, localized: String, english: String) -> String? {
        language == "en" || localized != english ? nil
            : "The run is in \(language), but the app's strings are in English: -testLanguage no longer reaches Bundle.main."
    }
}

/// Screenshots and the accessibility tree beside them.
@MainActor
public enum Pictures {
    /// `view`'s pixels at `scale` pixels a point, whatever the screens of the machine: a Mac with a Retina display and a
    /// CI runner without one take the same pictures.
    public static func bitmap(of view: NSView, scale: CGFloat = 2) -> NSBitmapImageRep {
        view.layoutSubtreeIfNeeded()
        let size = view.bounds.size
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale),
                                   bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                   bytesPerRow: 0, bitsPerPixel: 0)!
        rep.size = size
        view.cacheDisplay(in: view.bounds, to: rep)
        return rep
    }

    /// The picture's pixels, to tell whether two takes are the same.
    public static func pixels(_ rep: NSBitmapImageRep) -> Data { rep.tiffRepresentation ?? Data() }

    /// Every pixel of `rect` (in pixels, origin top left) is the same colour, within what dithering and a gradient
    /// too faint to see make: nothing is drawn there. Every `step`th pixel each way is read.
    public static func isFlat(_ rep: NSBitmapImageRep, in rect: CGRect, step: Int = 1) -> Bool {
        guard let data = rep.bitmapData else { return true }
        let x0 = max(0, Int(rect.minX.rounded(.down))), x1 = min(rep.pixelsWide, Int(rect.maxX.rounded(.up)))
        let y0 = max(0, Int(rect.minY.rounded(.down))), y1 = min(rep.pixelsHigh, Int(rect.maxY.rounded(.up)))
        let size = rep.bitsPerPixel / 8
        guard x1 > x0, y1 > y0, size >= 1 else { return true }
        let first = data + y0 * rep.bytesPerRow + x0 * size
        for y in stride(from: y0, to: y1, by: max(1, step)) {
            for x in stride(from: x0, to: x1, by: max(1, step)) {
                let p = data + y * rep.bytesPerRow + x * size
                for i in 0..<size where abs(Int(p[i]) - Int(first[i])) > 6 { return false }
            }
        }
        return true
    }

    /// A line of `takes-<language>.log` in `directory`: how long each screen took and what it waited for.
    public static func log(_ line: String, to directory: URL, language: String) {
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appending(path: "takes-\(language).log")
        let data = Data((line + "\n").utf8)
        if let handle = try? FileHandle(forWritingTo: file) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: data)
        } else {
            try? data.write(to: file)
        }
    }

    /// `<name>.png` and `<name>.ax.txt` in `directory`.
    public static func write(_ rep: NSBitmapImageRep, tree: [AXNode], name: String, to directory: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let png = rep.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try png.write(to: directory.appending(path: "\(name).png"))
        try (tree.map(\.description).joined(separator: "\n") + "\n")
            .write(to: directory.appending(path: "\(name).ax.txt"), atomically: true, encoding: .utf8)
    }
}
