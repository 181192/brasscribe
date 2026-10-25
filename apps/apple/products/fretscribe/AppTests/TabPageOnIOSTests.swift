#if os(iOS)
import Foundation
import Testing
import UIKit
import WebKit
import TabKit
@testable import Fretscribe

/// The tab page on an iPhone or iPad, in the app's own window scene: it engraves offline, in both appearances, and its
/// cursor follows what the app tells it. (The package's own tests draw it on the Mac only: they have no window scene.)
@MainActor
@Suite(.serialized) struct TabPageOnIOSTests {
    static func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "../../../../fixtures/\(name)").standardizedFileURL)
    }

    /// The share of opaque pixels in `image` that are dark (`dark`) or light.
    static func inked(_ image: UIImage, dark: Bool) -> Double {
        guard let cg = image.cgImage else { return 0 }
        let w = cg.width, h = cg.height
        var px = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        var hits = 0
        for i in stride(from: 0, to: px.count, by: 4) where px[i + 3] > 200 {
            let l = (Int(px[i]) + Int(px[i + 1]) + Int(px[i + 2])) / 3
            if dark ? l < 60 : l > 200 { hits += 1 }
        }
        return Double(hits) / Double(w * h)
    }

    @Test(.timeLimit(.minutes(2))) func theTabPageEngravesAndFollowsTheCursor() async throws {
        let scene = try #require(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let window = UIWindow(windowScene: scene)
        window.frame = CGRect(x: 0, y: 0, width: 400, height: 700)
        let vc = UIViewController()
        window.rootViewController = vc
        window.isHidden = false
        defer { window.isHidden = true }
        let page = TabPage()
        page.webView.frame = vc.view.bounds
        vc.view.addSubview(page.webView)
        let light = TabPalette(ink: "#1a1a1a", string: "#8a8a8a", uncertain: "#c0392b", cursor: "#2f6fde", cursorTint: nil)
        let e = try await page.show(musicXML: try Self.fixture("bass-line/tab.musicxml"), palette: light)
        #expect(e.bars.count == 15)
        #expect(page.networkBlocked)
        #expect(page.requested.allSatisfy { $0.hasPrefix("\(TabPage.scheme)://") })
        #expect(e.fonts.contains { $0.hasSuffix(":loaded") }, "\(e.fonts)")
        let shot = try await page.webView.takeSnapshot(configuration: WKSnapshotConfiguration())
        #expect(Self.inked(shot, dark: true) > 0.001)
        let at = try #require(try await page.cursor(bar: 2, tick: 960))
        let bar = try #require(e.bars.first { $0.bar == 2 })
        #expect(at.minX >= bar.x && at.minX <= bar.x + bar.w)
        let dark = TabPalette(ink: "#f2f2f2", string: "#7a7a7a", uncertain: "#ff8a7a", cursor: "#7fb0ff", cursorTint: nil)
        _ = try await page.palette(dark)
        let darkShot = try await page.webView.takeSnapshot(configuration: WKSnapshotConfiguration())
        #expect(Self.inked(darkShot, dark: false) > 0.001)
        #expect(page.webView.accessibilityElementsHidden)
    }
}
#endif
