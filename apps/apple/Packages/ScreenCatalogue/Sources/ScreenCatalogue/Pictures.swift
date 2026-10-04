import AppKit
import SwiftUI

public extension View {
    /// Increased contrast as System Settings › Accessibility › Display sets it. SwiftUI reads the setting only from the
    /// window server; this environment key, not documented, is what it sets from it. `Guards.contrast` checks that it
    /// still works.
    func catalogueContrast(increased: Bool) -> some View {
        environment(\._colorSchemeContrast, increased ? .increased : .standard)
    }
}

/// Black under increased contrast, white otherwise: what `Guards.contrast` draws.
public struct ContrastProbe: View {
    @Environment(\.colorSchemeContrast) private var contrast
    public init() {}
    public var body: some View { Rectangle().fill(contrast == .increased ? Color.black : Color.white) }
}

/// The checks that fail loudly when an undocumented hook the catalogue relies on stops working, instead of letting
/// every screen pass on an empty tree or draw the same picture for both contrasts. Each returns what went wrong, or nil.
@MainActor
public enum Guards {
    /// The accessibility tree must have the screen's controls in it.
    public static func tree(_ nodes: [AXNode], screen: String) -> String? {
        let controls = nodes.filter(\.isActionable).count
        return controls >= 1 ? nil
            : "\(screen): the accessibility tree has \(nodes.count) elements and \(controls) controls. Setting AXEnhancedUserInterface on NSApp no longer makes SwiftUI build it in-process (AXTree.enableInProcess)."
    }

    /// `ContrastProbe` drawn with `catalogueContrast(increased: true)`, as `rep`, must be black.
    public static func contrast(_ rep: NSBitmapImageRep) -> String? {
        let c = rep.colorAt(x: rep.pixelsWide / 2, y: rep.pixelsHigh / 2)?.usingColorSpace(.deviceRGB)
        return (c?.redComponent ?? 1) < 0.1 && (c?.greenComponent ?? 1) < 0.1 ? nil
            : "The increased-contrast variant draws as standard contrast: the _colorSchemeContrast environment key no longer sets colorSchemeContrast."
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

    /// `<name>.png` and `<name>.ax.txt` in `directory`.
    public static func write(_ rep: NSBitmapImageRep, tree: [AXNode], name: String, to directory: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let png = rep.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try png.write(to: directory.appending(path: "\(name).png"))
        try (tree.map(\.description).joined(separator: "\n") + "\n")
            .write(to: directory.appending(path: "\(name).ax.txt"), atomically: true, encoding: .utf8)
    }
}
