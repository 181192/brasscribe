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

    @Test(arguments: Screen.allCases)
    func screen(_ screen: Screen) async throws {
        let app = await model(for: screen)
        for variant in Variant.all {
            let r = await Rendering(view(for: screen, app: app), width: width(of: screen), variant: variant, app: app)
            await r.settle(until: { ready(screen, app) })
            try Catalogue.record(r, name: Catalogue.name(screen.rawValue, variant)) { f in
                Self.known.contains { ($0.screen == nil || $0.screen == screen) && $0.kind == f.kind && f.node.contains($0.words) }
            }
            r.close()
        }
    }

    /// The undocumented hooks still do what the catalogue needs, and the run is in the language it says.
    @Test func hooksStillWork() async {
        if let wrong = Guards.language(Catalogue.language, localized: String(localized: "Pair a phone"), english: "Pair a phone") {
            Issue.record(Comment(rawValue: wrong))
        }
        let app = await Catalogue.model(busy: false)
        let r = await Rendering(ContrastProbe(), width: 20, height: 20, variant: .contrast, app: app)
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
            return AnyView(StatusPanel().background(Color.Brasscribe.bg))
        case .phones:
            app.panelPage = .phones
            return AnyView(StatusPanel().background(Color.Brasscribe.bg))
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

    /// What the screen waits for before its picture is taken.
    private func ready(_ screen: Screen, _ app: AppModel) -> Bool {
        switch screen {
        case .pair: app.pairing.displayCode != nil
        case .panelRequest: !app.monitor.requests.isEmpty
        case .phones: !app.monitor.devices.isEmpty
        default: true
        }
    }
}
