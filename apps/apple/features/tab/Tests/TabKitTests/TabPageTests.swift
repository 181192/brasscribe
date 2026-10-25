import CoreGraphics
import Foundation
import Testing
import WebKit
@testable import TabKit
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// The fixtures beside the apps (apps/fixtures), found from this file.
func fixture(_ name: String) throws -> Data {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appending(path: "../../../../../fixtures/\(name)").standardizedFileURL
    return try Data(contentsOf: root)
}

let light = TabPalette(ink: "#1a1a1a", string: "#8a8a8a", uncertain: "#c0392b", cursor: "#2f6fde", cursorTint: "#2f6fde33")
let dark = TabPalette(ink: "#f2f2f2", string: "#7a7a7a", uncertain: "#ff8a7a", cursor: "#7fb0ff", cursorTint: "#7fb0ff33")

@MainActor
func hosted(_ page: TabPage, width: CGFloat = 800, height: CGFloat = 900) -> AnyObject {
    page.webView.frame = CGRect(x: 0, y: 0, width: width, height: height)
    #if os(macOS)
    let window = NSWindow(contentRect: page.webView.frame, styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = page.webView
    window.setFrameOrigin(NSPoint(x: -10_000, y: -10_000))
    window.orderBack(nil)
    return window
    #else
    let window = UIWindow(frame: page.webView.frame)
    let vc = UIViewController()
    vc.view.addSubview(page.webView)
    window.rootViewController = vc
    window.isHidden = false
    return window
    #endif
}

/// The share of pixels in [image] that are close to [hex] (#rrggbb).
func share(of hex: String, in image: CGImage) -> Double {
    let w = image.width, h = image.height
    var px = [UInt8](repeating: 0, count: w * h * 4)
    let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
    let v = Int(hex.dropFirst(), radix: 16)!
    let (r, g, b) = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    var hits = 0
    for i in stride(from: 0, to: px.count, by: 4) where px[i + 3] > 200 {
        if abs(Int(px[i]) - r) < 24 && abs(Int(px[i + 1]) - g) < 24 && abs(Int(px[i + 2]) - b) < 24 { hits += 1 }
    }
    return Double(hits) / Double(w * h)
}

@MainActor
func snapshot(_ page: TabPage) async throws -> CGImage {
    let cfg = WKSnapshotConfiguration()
    cfg.afterScreenUpdates = true
    #if os(macOS)
    let image = try await page.webView.takeSnapshot(configuration: cfg)
    var rect = CGRect(origin: .zero, size: image.size)
    return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)!
    #else
    return try await page.webView.takeSnapshot(configuration: cfg).cgImage!
    #endif
}

func save(_ image: CGImage, _ name: String) {
    guard let dir = ProcessInfo.processInfo.environment["TAB_SHOTS"] else { return }
    let url = URL(fileURLWithPath: dir).appending(path: name)
    try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    if let d = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) {
        CGImageDestinationAddImage(d, image, nil)
        CGImageDestinationFinalize(d)
    }
}

/// Whether the page can be drawn here. A package's tests on the iPhone simulator run without a window scene, where a web
/// view does not draw: there the app's own tests take the page's pictures.
let pagesDraw: Bool = {
    #if os(macOS)
    true
    #else
    false
    #endif
}()

@MainActor
@Suite(.serialized, .enabled(if: pagesDraw)) struct TabPageTests {
    @Test(.timeLimit(.minutes(2))) func engravesOfflineInBothAppearancesAndFollowsTheCursor() async throws {
        let page = TabPage()
        let window = hosted(page)
        defer { _ = window }
        let xml = try fixture("bass-line/tab.musicxml")

        let t0 = Date()
        let e = try await page.show(musicXML: xml, palette: light)
        let first = Date().timeIntervalSince(t0)
        #expect(page.networkBlocked)
        #expect(e.height > 50)
        #expect(e.bars.count == 15)
        #expect(!e.resources.isEmpty)
        #expect(e.resources.allSatisfy { $0.hasPrefix("\(TabPage.scheme)://") }, "\(e.resources)")
        #expect(e.resources.contains { $0.hasSuffix("Bravura.woff2") })
        #expect(e.fonts.contains { $0.hasSuffix(":loaded") }, "\(e.fonts)")
        let lightShot = try await snapshot(page)
        save(lightShot, "tab-light.png")
        let ink = share(of: light.ink, in: lightShot)
        #expect(ink > 0.001, "light ink share \(ink)")

        // The cursor: a beat in bar 3, from Swift to the page and back.
        var times: [Double] = []
        for i in 0..<60 {
            let t = Date()
            let r = try await page.cursor(bar: i % e.bars.count, tick: (i * 240) % 3840)
            times.append(Date().timeIntervalSince(t) * 1000)
            #expect(r != nil)
        }
        let r = try #require(try await page.cursor(bar: 2, tick: 960))
        let box = try #require(e.bars.first { $0.bar == 2 })
        #expect(r.minX >= box.x && r.minX <= box.x + box.w, "cursor \(r) in bar \(box)")
        let cursorShot = try await snapshot(page)
        save(cursorShot, "tab-cursor.png")
        #expect(share(of: light.cursor, in: cursorShot) > 0)

        let t1 = Date()
        _ = try await page.palette(dark)
        let again = Date().timeIntervalSince(t1)
        let darkShot = try await snapshot(page)
        save(darkShot, "tab-dark.png")
        #expect(share(of: dark.ink, in: darkShot) > 0.001)
        #expect(share(of: light.ink, in: darkShot) < 0.0001)

        times.sort()
        print("TAB spike: first engraving \(Int(first * 1000)) ms (alphaTab \(e.milliseconds) ms), dark again \(Int(again * 1000)) ms, "
              + "cursor round trip median \(String(format: "%.1f", times[times.count / 2])) ms, p95 \(String(format: "%.1f", times[times.count * 95 / 100])) ms, "
              + "resources \(e.resources.map { URL(string: $0)!.lastPathComponent }), fonts \(e.fonts)")
    }

    @Test(.timeLimit(.minutes(1))) func doubtfulNumeralsTakeTheDoubtColour() async throws {
        let page = TabPage()
        let window = hosted(page)
        defer { _ = window }
        // the first note of the bass line: bar 0, low E string (alphaTab counts strings from the lowest, 1), fret 0, tick 0
        let e = try await page.show(musicXML: try fixture("bass-line/tab.musicxml"), palette: light, doubtful: ["0:1:0:0"])
        #expect(e.bars.count == 15)
        let shot = try await snapshot(page)
        save(shot, "tab-doubt.png")
        #expect(share(of: light.uncertain, in: shot) > 0)
    }

    /// Two engravings asked for at once both get their answer, one after the other.
    @Test(.timeLimit(.minutes(1))) func twoEngravingsAskedAtOnceBothAnswer() async throws {
        let page = TabPage()
        let window = hosted(page)
        defer { _ = window }
        let xml = try fixture("bass-line/tab.musicxml")
        async let first = page.show(musicXML: xml, palette: light)
        async let second = page.show(musicXML: try fixture("guitar-line/tab.musicxml"), palette: dark, scale: 1.5)
        let (a, b) = try await (first, second)
        #expect(a.bars.count == 15)
        #expect(b.bars.count > 0 && b.bars.count != 15)
        #expect(page.engraving == b)
    }
}

/// What holds on every platform, also where a page cannot start: a package's tests on the iPhone simulator have no window
/// scene, and its web view may never load there. The rule that keeps the page off the network is in place before the
/// page is first loaded, and the web view is hidden from VoiceOver. Where the page does load (the Mac here, and
/// Fretscribe's app-hosted tests on the iPhone), it loads only the app's own files.
@MainActor
@Suite(.serialized) struct TabPageEverywhereTests {
    @Test(.timeLimit(.minutes(1))) func thePageIsOfflineAndHiddenFromVoiceOver() async throws {
        let page = TabPage()
        let end = Date().addingTimeInterval(20)
        while !page.networkBlocked, Date() < end { try await Task.sleep(for: .milliseconds(50)) }
        #expect(page.networkBlocked)
        #if os(macOS)
        await page.loaded()
        let asked = page.requested
        #expect(asked.allSatisfy { $0.hasPrefix("\(TabPage.scheme)://") }, "\(asked)")
        #expect(asked.contains { $0.hasSuffix("alphaTab.min.js") } && asked.contains { $0.hasSuffix("tab.js") })
        #expect(page.webView.isAccessibilityElement() == false)
        #expect(page.webView.isAccessibilityHidden())
        #else
        #expect(page.webView.accessibilityElementsHidden)
        #endif
    }
}
