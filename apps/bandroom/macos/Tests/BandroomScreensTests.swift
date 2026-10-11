import AppKit
import ScreenCatalogue
import SwiftUI
import Testing
@testable import Brasscribe_Bandroom

/// The screen catalogue of Bandroom for Mac: every screen in light, dark, increased contrast (light and dark) and
/// Bandroom's largest text size, and in bokmål (`scripts/screenshots.sh`), with the checks (`Checks`) and a screenshot
/// each. A new screen or state gets a `Screen` here.
@MainActor
@Suite(.serialized, .timeLimit(.minutes(5))) struct BandroomScreensTests {
    enum Screen: String, CaseIterable, Sendable {
        case panelBusy = "panel-busy"
        case panelReady = "panel-ready"
        case panelRequest = "panel-request"
        case panelSettingUp = "panel-setting-up"
        case phones
        case pair
        case setupCheck = "setup-check"
        case setupLicence = "setup-licence"
        case setupDownload = "setup-download"
        case setupReady = "setup-ready"
        case settings
    }

    /// Findings that are known and not yet fixed, each with its issue: the screen, the kind, and words the finding names.
    static let known: [(screen: Screen?, kind: Finding.Kind, words: String, issue: String)] = []

    /// Texts drawn in the colour of what is behind them in light with Increase Contrast: black, the system's text colour
    /// there, on the black of the high-contrast colours. These, and no others, are not asked to be in the picture; an
    /// entry whose text is drawn, or gone, fails the run. The second "Setting up" is the line over the progress bar;
    /// the first, in the headline, is drawn.
    static let unreadable = Unreadable(issue: "#368", screens: ["panel-setting-up-contrast": [.init("Setting up", nth: 2)]])

    @Test(arguments: Screen.allCases)
    func screen(_ screen: Screen) async throws {
        let app = await model(for: screen)
        for variant in Variant.all {
            let r = await Rendering(view(for: screen, app: app), width: width(of: screen), variant: variant, app: app)
            defer { r.close() }
            let name = Catalogue.name(screen.rawValue, variant)
            try await Catalogue.record(r, name: name, ready: { waitsFor(screen, app) }, unreadable: Self.unreadable) { f in
                Self.known.contains { ($0.screen == nil || $0.screen == screen) && $0.kind == f.kind && f.node.contains($0.words) }
            }
        }
    }

    /// The ⋯ menu takes clicks on 28 × 28 pt: its frame in the tree, and any AppKit control under it (for an AppKit-backed
    /// control the tree can report a SwiftUI wrapper's frame, while clicks outside the control itself go nowhere).
    @Test func theMoreMenuTakesClicksOn28Points() async throws {
        let app = await Catalogue.model(busy: false)
        let r = await Rendering(StatusPanel().background(Color.Scribe.bg), width: 360, variant: .light, app: app)
        defer { r.close() }
        let more = try #require(AXTree.read(r.hosting).first { ["AXMenuButton", "AXPopUpButton"].contains($0.role) && $0.frame.minX > 280 })
        #expect(more.frame.width >= 28 && more.frame.height >= 28, "\(more)")
        func views(_ v: NSView) -> [NSView] { v.subviews + v.subviews.flatMap(views) }
        for control in views(r.hosting) where control is NSControl {
            let f = control.convert(control.bounds, to: r.hosting)
            guard f.intersects(more.frame) else { continue }
            #expect(f.width >= 24 && f.height >= 24, "the AppKit control under the ⋯ menu is \(f.size)")
        }
    }

    /// The hooks still do what the catalogue needs, and the run is in the language it says.
    @Test func hooksStillWork() async {
        if let wrong = Guards.language(Catalogue.language, localized: String(localized: "Pair a phone"), english: "Pair a phone") {
            Issue.record(Comment(rawValue: wrong))
        }
        let app = await Catalogue.model(busy: false)
        let r = await Rendering(NavigationStack { ContrastProbe() }, width: 200, height: 200, variant: .contrast, app: app)
        if let broken = Guards.contrast(Pictures.bitmap(of: r.hosting)) { Issue.record(Comment(rawValue: broken)) }
        r.close()
    }

    private func model(for screen: Screen) async -> AppModel {
        switch screen {
        case .panelBusy, .phones: await Catalogue.model(busy: true)
        case .panelRequest: await Catalogue.model(busy: true, request: true)
        case .panelReady, .pair, .settings: await Catalogue.model(busy: false)
        case .panelSettingUp, .setupCheck, .setupLicence, .setupDownload, .setupReady:
            await {
                let app = await Catalogue.model(busy: false)
                // The first run, before the engine is installed (the demo starts as if it were).
                app.setupComplete = false
                return app
            }()
        }
    }

    private func view(for screen: Screen, app: AppModel) -> AnyView {
        switch screen {
        case .panelBusy, .panelReady, .panelRequest, .panelSettingUp:
            app.panelPage = .status
            return AnyView(StatusPanel().background(Color.Scribe.bg))
        case .phones:
            app.panelPage = .phones
            return AnyView(StatusPanel().background(Color.Scribe.bg))
        case .pair: return AnyView(PairWindow())
        case .setupCheck: return AnyView(SetupView(step: 0))
        case .setupLicence: return AnyView(SetupView(step: 1))
        case .setupDownload: return AnyView(SetupView(step: 2))
        case .setupReady: return AnyView(SetupView(step: 3))
        case .settings: return AnyView(SettingsView())
        }
    }

    /// The window's width: the panel's 360 pt, the others at their smallest.
    private func width(of screen: Screen) -> CGFloat {
        switch screen {
        case .panelBusy, .panelReady, .panelRequest, .panelSettingUp, .phones: 360
        case .pair: 720
        case .setupCheck, .setupLicence, .setupDownload, .setupReady: 760
        case .settings: 480
        }
    }

    /// What the screen still waits for before its picture counts, or nil.
    private func waitsFor(_ screen: Screen, _ app: AppModel) -> String? {
        switch screen {
        case .pair: app.pairing.displayCode != nil ? nil : "its pairing code is not there yet"
        case .panelRequest: !app.monitor.requests.isEmpty ? nil : "its request is not there yet"
        case .phones: !app.monitor.devices.isEmpty ? nil : "its phones are not there yet"
        default: nil
        }
    }
}
