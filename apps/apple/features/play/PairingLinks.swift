import SwiftUI
import TranscriptionKit
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// Another app of the family that may be on this device, and the URL scheme of its own that opens it.
struct SiblingApp: Hashable, Identifiable {
    let name: String
    let scheme: String
    var id: String { scheme }
}

/// Which app pairs when a pairing link is opened from outside (the camera, another app). The link names the family
/// (`scribe:`), and every app of it registers that scheme, so the system picks one of them. When another app of the
/// family is on this device too, the app the system opened asks which of them is to connect, and hands the link to the
/// other one under that app's own scheme (`brasscribe:`, `fretscribe:`) when the player chooses it.
enum PairingLinks {
    /// The pairing link in [url]: one with the family's scheme, or with this app's own ([ownScheme]), which a
    /// sibling handed over. Nil for any other URL.
    static func link(in url: URL, ownScheme: String) -> PairingLink? {
        guard let scheme = url.scheme?.lowercased(), scheme == Wire.pairScheme || scheme == ownScheme.lowercased() else { return nil }
        guard var c = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
        c.scheme = Wire.pairScheme
        return c.url.flatMap(PairingLink.init(url:))
    }

    /// [url] under [sibling]'s own scheme: the same link, for that app.
    static func handedOver(_ url: URL, to sibling: SiblingApp) -> URL? {
        guard var c = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
        c.scheme = sibling.scheme
        return c.url
    }

    /// The apps of [siblings] that are on this device.
    @MainActor static func installed(_ siblings: [SiblingApp]) -> [SiblingApp] {
        siblings.filter { s in
            guard let probe = URL(string: "\(s.scheme)://") else { return false }
            #if os(macOS)
            return NSWorkspace.shared.urlForApplication(toOpen: probe) != nil
            #else
            return UIApplication.shared.canOpenURL(probe)
            #endif
        }
    }

    @MainActor static func open(_ url: URL) {
        #if os(macOS)
        NSWorkspace.shared.open(url)
        #else
        UIApplication.shared.open(url)
        #endif
    }
}

/// Opens pairing links: straight in this app, or after asking which app is to connect when a sibling is installed.
/// Any other URL goes to [other].
struct PairingLinkHandler: ViewModifier {
    let appName: String
    let ownScheme: String
    let siblings: [SiblingApp]
    let pair: (PairingLink) -> Void
    let other: (URL) -> Void
    @State private var asking: Asking?

    struct Asking: Identifiable {
        let id = UUID()
        let url: URL
        let link: PairingLink
        let siblings: [SiblingApp]
    }

    func body(content: Content) -> some View {
        content
            .onOpenURL { url in
                guard let link = PairingLinks.link(in: url, ownScheme: ownScheme) else { other(url); return }
                // a link handed over by a sibling, or no sibling here: this app is the one
                let others = url.scheme?.lowercased() == Wire.pairScheme ? PairingLinks.installed(siblings) : []
                if others.isEmpty { pair(link) } else { asking = Asking(url: url, link: link, siblings: others) }
            }
            .confirmationDialog(Text("Which app should connect to your computer?"), isPresented: Binding(
                get: { asking != nil }, set: { if !$0 { asking = nil } }), titleVisibility: .visible, presenting: asking) { a in
                Button(appName) { pair(a.link) }
                ForEach(a.siblings) { s in
                    Button(s.name) { if let u = PairingLinks.handedOver(a.url, to: s) { PairingLinks.open(u) } }
                }
                Button("Cancel", role: .cancel) {}
            } message: { _ in
                Text("The pairing link is for any of them. Each app connects on its own.")
            }
    }
}

extension View {
    /// Opens pairing links for the app named [appName], whose own scheme is [ownScheme]; [siblings] are the other apps of
    /// the family. Any other URL goes to [other].
    func pairingLinks(appName: String, ownScheme: String, siblings: [SiblingApp], pair: @escaping (PairingLink) -> Void,
                      other: @escaping (URL) -> Void) -> some View {
        modifier(PairingLinkHandler(appName: appName, ownScheme: ownScheme, siblings: siblings, pair: pair, other: other))
    }
}
