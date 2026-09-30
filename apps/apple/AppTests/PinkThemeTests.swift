#if os(macOS)
import AppKit
import Foundation
import SwiftUI
import Testing
@testable import BrasscribePlay

/// The hidden Pink palette (design/system.md §10) on the Mac: the semantic colours switch with the
/// palette, the notation keeps its ink, and, with BRASSCRIBE_PINK_SHOTS set, the layout harness writes
/// the screens in Pink to design/pink.
@MainActor
@Suite(.serialized) struct PinkThemeTests {
    private func resolved(_ color: Color, dark: Bool) -> Color.Resolved {
        var env = EnvironmentValues()
        env.colorScheme = dark ? .dark : .light
        return color.resolve(in: env)
    }

    @Test func paletteSwitchesTheChromeButKeepsTheInk() {
        defer { BrasscribePalette.shared.isPink = false }
        for dark in [false, true] {
            BrasscribePalette.shared.isPink = false
            let bg = resolved(Color.Brasscribe.bg, dark: dark), primary = resolved(Color.Brasscribe.primary, dark: dark)
            let ink = resolved(Color.Brasscribe.ink, dark: dark), uncertain = resolved(Color.Brasscribe.uncertain, dark: dark)
            BrasscribePalette.shared.isPink = true
            #expect(resolved(Color.Brasscribe.bg, dark: dark) != bg)
            #expect(resolved(Color.Brasscribe.primary, dark: dark) != primary)
            #expect(resolved(Color.Brasscribe.ink, dark: dark) == ink)
            #expect(resolved(Color.Brasscribe.uncertain, dark: dark) == uncertain)
        }
        // the Pink paper is blush in light (#FFF6F9) and aubergine in dark (#1B1017)
        let light = resolved(Color.Brasscribe.bg, dark: false)
        #expect(abs(light.red - 1) < 0.01 && abs(light.blue - Float(0xF9) / 255) < 0.01)
        let darkBg = resolved(Color.Brasscribe.bg, dark: true)
        #expect(abs(darkBg.red - Float(0x1B) / 255) < 0.01)
    }

    /// A view that reads a colour in its body redraws when the palette changes (Observation), so a
    /// choice in Settings recolours the open window without rebuilding it.
    @Test func openViewsFollowThePalette() async {
        defer { BrasscribePalette.shared.isPink = false }
        BrasscribePalette.shared.isPink = false
        let host = OffscreenHost(Swatch(), size: CGSize(width: 40, height: 40))
        await host.settle(0.2)
        let before = host.bitmap().colorAt(x: 20, y: 20)
        BrasscribePalette.shared.isPink = true
        await host.settle(0.3)
        let after = host.bitmap().colorAt(x: 20, y: 20)
        host.close()
        #expect(before != nil)
        #expect(after != nil)
        #expect(before != after, "the open view kept \(String(describing: before)) after the palette changed")
    }

    /// Reads the colour in its body, as every screen does.
    private struct Swatch: View {
        var body: some View { Color.Brasscribe.bg.frame(width: 40, height: 40) }
    }

    // MARK: screenshots

    nonisolated static var shotsEnabled: Bool { ProcessInfo.processInfo.environment["BRASSCRIBE_PINK_SHOTS"] != nil }

    static var shotsDirectory: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appending(path: "design/pink")
    }

    private func save(_ rep: NSBitmapImageRep, _ name: String) {
        try? FileManager.default.createDirectory(at: Self.shotsDirectory, withIntermediateDirectories: true)
        if let data = rep.representation(using: .png, properties: [:]) {
            try? data.write(to: Self.shotsDirectory.appending(path: "\(name).png"))
        }
    }

    private func render(_ view: some View, size: CGSize, dark: Bool, toEnd: Bool = false, wait: (() -> Bool)? = nil) async -> NSBitmapImageRep {
        let host = OffscreenHost(view.environment(\.colorScheme, dark ? .dark : .light), size: size)
        host.window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        if let wait { await host.settle(until: wait) } else { await host.settle(0.8) }
        if toEnd {
            // Appearance and About sit at the end of the form
            for case let scroll as NSScrollView in OffscreenHost.descendants(host.hosting) {
                guard let doc = scroll.documentView else { continue }
                let y = doc.isFlipped ? max(0, doc.bounds.height - scroll.contentView.bounds.height) : 0
                scroll.contentView.scroll(to: NSPoint(x: 0, y: y))
                scroll.reflectScrolledClipView(scroll.contentView)
            }
            await host.settle(0.4)
        }
        let rep = host.bitmap()
        host.close()
        return rep
    }

    @Test(.enabled(if: shotsEnabled && fixtureDir() != nil)) func screensInPink() async throws {
        defer { BrasscribePalette.shared.isPink = false }
        BrasscribePalette.shared.isPink = true
        LayoutFixtures.freshLibrary()
        let app = LayoutFixtures.app()
        try LayoutFixtures.library(app)
        let piece = try LayoutFixtures.piece()
        // Settings reads its own store: Pink chosen and unlocked, without touching this Mac's settings
        let store = try #require(UserDefaults(suiteName: "pink-shots"))
        store.set(true, forKey: PinkUnlock.key)
        let window = CGSize(width: 1280, height: 800 - OffscreenHost.toolbarHeight)

        for (choice, suffix) in [(AppearanceSetting.pinkLight, "pink"), (.pinkDark, "pink-dark")] {
            let dark = choice == .pinkDark
            store.set(choice.rawValue, forKey: AppearanceSetting.key)
            save(await render(HarnessShell { HomeView() }.environment(app), size: window, dark: dark), "apple-home-\(suffix)")
            let model = try await LayoutFixtures.model(piece)
            save(await render(HarnessShell { PracticeView(model: model).pageBackground() }.environment(app), size: window, dark: dark,
                              wait: { !model.pages.isEmpty && !model.engraving }), "apple-score-\(suffix)")
            model.stopAll()
            let settings = SettingsView().environment(app).tint(Color.Brasscribe.primary).defaultAppStorage(store)
            save(await render(settings, size: CGSize(width: 600, height: 1100), dark: dark, toEnd: true), "apple-settings-\(suffix)")
        }
        store.removePersistentDomain(forName: "pink-shots")
    }
}
#endif
