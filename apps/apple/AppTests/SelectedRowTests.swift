import Foundation
import SwiftUI
import Testing
@testable import BrasscribePlay

/// The selected row of the review's note list stays readable in every palette: light, dark, high
/// contrast and Pink light and dark. (The system highlight used the tint, primary, under text in
/// the page's colour: near black on near black in light.)
@MainActor
@Suite(.serialized) struct SelectedRowTests {
    private func resolved(_ color: Color, dark: Bool, contrast: Bool) -> Color.Resolved {
        var env = EnvironmentValues()
        env.colorScheme = dark ? .dark : .light
        env._colorSchemeContrast = contrast ? .increased : .standard
        return color.resolve(in: env)
    }

    /// WCAG 2 contrast ratio of two opaque colours.
    static func ratio(_ a: Color.Resolved, _ b: Color.Resolved) -> Double {
        func lum(_ c: Color.Resolved) -> Double {
            // Color.Resolved holds linear sRGB components
            0.2126 * Double(c.linearRed) + 0.7152 * Double(c.linearGreen) + 0.0722 * Double(c.linearBlue)
        }
        let (x, y) = (lum(a), lum(b))
        return (max(x, y) + 0.05) / (min(x, y) + 0.05)
    }

    @Test func selectedRowIsReadableInEveryPalette() {
        defer { BrasscribePalette.shared.isPink = false }
        for pink in [false, true] {
            BrasscribePalette.shared.isPink = pink
            for dark in [false, true] {
                for contrast in [false, true] {
                    let name = "\(pink ? "pink" : "standard") \(dark ? "dark" : "light")\(contrast ? " high contrast" : "")"
                    let fill = resolved(SelectedRow.fill, dark: dark, contrast: contrast)
                    let text = resolved(SelectedRow.text, dark: dark, contrast: contrast)
                    let edge = resolved(SelectedRow.edge, dark: dark, contrast: contrast)
                    let page = resolved(Color.Scribe.surfaceRaised, dark: dark, contrast: contrast)
                    #expect(Self.ratio(text, fill) >= 4.5, "text on the selected row, \(name): \(Self.ratio(text, fill))")
                    // the "?" marks are bold glyphs: 3:1 as for large text and graphics
                    for mark in [Color.Scribe.uncertain, Color.Brasscribe.veryUncertain] {
                        let m = resolved(mark, dark: dark, contrast: contrast)
                        #expect(Self.ratio(m, fill) >= 3, "? mark on the selected row, \(name): \(Self.ratio(m, fill))")
                    }
                    // the row is told apart from the others by its edge
                    #expect(Self.ratio(edge, page) >= 3, "selected row edge, \(name): \(Self.ratio(edge, page))")
                }
            }
        }
    }

    /// Only the selected row gets the drawn background; the others keep the list's own.
    @Test func onlyTheSelectedRowHasTheBackground() {
        #expect(SelectedRow.background(true) != nil)
        #expect(SelectedRow.background(false) == nil)
    }
}

#if os(macOS)
import AppKit

/// On the Mac the review's note list is a sidebar list: when it has the focus, AppKit draws the
/// selection emphasised, in the accent colour. The harness window is never key, so the test sets
/// the row views emphasised itself, then reads the pixels beside the selected row's text.
@MainActor
@Suite(.serialized) struct SelectedRowHarnessTests {
    @Test(.enabled(if: fixtureDir() != nil)) func focusedReviewListKeepsTheSelectionReadable() async throws {
        defer { BrasscribePalette.shared.isPink = false }
        LayoutFixtures.freshLibrary()
        let app = LayoutFixtures.app()
        let piece = try LayoutFixtures.piece()
        for (dark, pink) in [(false, false), (true, false), (false, true), (true, true)] {
            BrasscribePalette.shared.isPink = pink
            let name = "\(pink ? "pink" : "standard") \(dark ? "dark" : "light")"
            let root = HarnessShell(sidebar: false) { ReviewView(piece: piece) }
                .environment(app)
                .environment(\.colorScheme, dark ? .dark : .light)
            let host = OffscreenHost(root, size: CGSize(width: 1100, height: 700))
            host.window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
            func table() -> NSTableView? {
                OffscreenHost.descendants(host.hosting).compactMap { $0 as? NSTableView }.first { $0.selectedRow >= 0 }
            }
            await host.settle(until: { table() != nil }, timeout: 20)
            let t = try #require(table(), "the note list shows with a selected note (\(name))")
            t.enumerateAvailableRowViews { row, _ in row.isEmphasized = true }
            t.needsDisplay = true
            await host.settle(0.2)
            let rep = host.bitmap()
            // just inside the row's right end, clear of the text and of the rounded corners
            let rect = t.convert(t.rect(ofRow: t.selectedRow), to: host.hosting)
            let scale = CGFloat(rep.pixelsWide) / host.hosting.bounds.width
            let x = Int((rect.maxX - 24) * scale)
            let y = Int((host.hosting.isFlipped ? rect.midY : host.hosting.bounds.height - rect.midY) * scale)
            let seen = try #require(rep.colorAt(x: x, y: y)?.usingColorSpace(.sRGB))
            var env = EnvironmentValues()
            env.colorScheme = dark ? .dark : .light
            let want = SelectedRow.fill.resolve(in: env)
            let d = max(abs(Float(seen.redComponent) - want.red), abs(Float(seen.greenComponent) - want.green),
                        abs(Float(seen.blueComponent) - want.blue))
            if Thumbnails.enabled, let png = rep.representation(using: .png, properties: [:]) {
                try? FileManager.default.createDirectory(at: Thumbnails.directory, withIntermediateDirectories: true)
                try? png.write(to: Thumbnails.directory.appending(path: "selected-row-\(name.replacingOccurrences(of: " ", with: "-")).png"))
            }
            host.close()
            #expect(d < 0.06, "the focused selection is drawn in \(seen), not the selection tint, \(name)")
        }
    }
}
#endif
