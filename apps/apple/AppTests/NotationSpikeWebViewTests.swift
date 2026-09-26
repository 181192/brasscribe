#if os(macOS)
import AppKit
import Foundation
import NotationKit
import SVGRender
import Testing
import WebKit

/// The WKWebView side of the notation spike (docs/notation-spike.md): the same Verovio
/// pages shown in a web view, measuring time to first paint, WebContent memory and what
/// VoiceOver can reach. Runs hosted in the app so WebKit has a run loop.
@MainActor
@Suite(.serialized, .enabled(if: fixtureDir() != nil)) struct NotationSpikeWebView {
    func pagesSVG(height: Int) throws -> [String] {
        let xml = try String(contentsOf: fixtureDir()!.appending(path: "brass-band.musicxml"), encoding: .utf8)
        let tk = try #require(VerovioToolkit(resourcePath: VerovioToolkit.defaultResourcePath(bundle: .main)))
        tk.setOptions(["pageWidth": 2050, "pageHeight": height, "adjustPageHeight": true, "scale": 40, "breaks": "auto",
                       "header": "none", "footer": "none"])
        #expect(tk.loadData(xml))
        return (1...tk.pageCount).map { tk.renderToSVG(page: $0) }
    }

    @Test(.timeLimit(.minutes(3))) func webViewFirstPageAndAccessibility() async throws {
        let pages = try pagesSVG(height: 2900)
        let before = webContentRSS()
        let t0 = Date()
        let wv = WKWebView(frame: CGRect(x: 0, y: 0, width: 840, height: 1200))
        let window = NSWindow(contentRect: wv.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = wv
        window.orderFront(nil)
        let nav = NavWaiter()
        wv.navigationDelegate = nav
        wv.loadHTMLString("<!doctype html><html><body style='margin:0'>" + pages[0] + "</body></html>", baseURL: nil)
        try await waitLoaded(wv, nav)
        _ = try await wv.takeSnapshot(configuration: WKSnapshotConfiguration())
        let firstPaint = Date().timeIntervalSince(t0)
        print("SPIKE webview first page loaded+painted \(Int(firstPaint * 1000)) ms")

        // all pages in one document (a scrolling score)
        let t1 = Date()
        let nav2 = NavWaiter()
        wv.navigationDelegate = nav2
        wv.loadHTMLString("<!doctype html><html><body style='margin:0'>" + pages.joined() + "</body></html>", baseURL: nil)
        try await waitLoaded(wv, nav2)
        _ = try await wv.takeSnapshot(configuration: WKSnapshotConfiguration())
        let allPaint = Date().timeIntervalSince(t1)
        print("SPIKE webview all \(pages.count) pages painted \(Int(allPaint * 1000)) ms")
        try await Task.sleep(for: .milliseconds(800))
        let after = webContentRSS()

        var count = 0, labelled = 0
        var roles: [String: Int] = [:]
        let deadline = Date().addingTimeInterval(20)
        func walk(_ e: Any, depth: Int) {
            guard depth < 40, let o = e as? NSObject, count < 3000, Date() < deadline else { return }
            count += 1
            let role = o.accessibilityAttributeValue(.role) as? String ?? "?"
            roles[role, default: 0] += 1
            let label = (o.accessibilityAttributeValue(.description) as? String) ?? (o.accessibilityAttributeValue(.title) as? String) ?? ""
            if !label.isEmpty { labelled += 1 }
            for c in (o.accessibilityAttributeValue(.children) as? [Any]) ?? [] { walk(c, depth: depth + 1) }
        }
        walk(wv, depth: 0)
        let report = "webview: pages \(pages.count); first page loaded+painted \(Int(firstPaint * 1000)) ms; all pages painted \(Int(allPaint * 1000)) ms; "
            + "WebContent RSS before \(Int(before)) MB after \(Int(after)) MB; AX elements \(count), labelled \(labelled), roles \(roles.sorted { $0.value > $1.value }.prefix(6).map { "\($0.key)=\($0.value)" })"
        print("SPIKE", report)
        let out = FileManager.default.temporaryDirectory.appending(path: "notation-spike-webview.txt")
        try report.write(to: out, atomically: true, encoding: .utf8)
        print("SPIKE written to \(out.path)")
        window.close()
    }

    @Test func nativeFirstPage() throws {
        let t0 = Date()
        let xml = try String(contentsOf: fixtureDir()!.appending(path: "brass-band.musicxml"), encoding: .utf8)
        let r = try #require(ScoreRenderer(musicXML: xml, resourcePath: VerovioToolkit.defaultResourcePath(bundle: .main)))
        #expect(r.apply(.init(width: 820, height: 1160)))
        let page = try #require(r.page(1))
        let ctx = CGContext(data: nil, width: 1640, height: Int(page.svg.size.height * 2), bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        ctx.scaleBy(x: 2, y: 2)
        page.svg.draw(in: ctx)
        let first = Date().timeIntervalSince(t0)
        let t1 = Date()
        let all = r.renderAllPages()
        let rest = Date().timeIntervalSince(t1)
        let elements = all.reduce(0) { $0 + $1.staves.values.reduce(0) { $0 + $1.count } }
        let report = "native: first page engraved+parsed+drawn \(Int(first * 1000)) ms; remaining \(all.count - 1) pages \(Int(rest * 1000)) ms; per-part-per-bar accessibility elements \(elements)"
        print("SPIKE", report)
    }
}

/// Poll instead of awaiting the delegate so a stalled WebContent process shows up in the log.
@MainActor func waitLoaded(_ wv: WKWebView, _ nav: NavWaiter) async throws {
    let start = Date()
    while !nav.done {
        try await Task.sleep(for: .milliseconds(20))
        if Date().timeIntervalSince(start) > 30 {
            print("SPIKE webview stalled: isLoading=\(wv.isLoading) progress=\(wv.estimatedProgress)")
            throw CancellationError()
        }
    }
}

@MainActor final class NavWaiter: NSObject, WKNavigationDelegate {
    var cont: CheckedContinuation<Void, Error>?
    var done = false
    func wait() async throws {
        if done { return }
        try await withCheckedThrowingContinuation { cont = $0 }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { done = true; cont?.resume(); cont = nil }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { cont?.resume(throwing: error); cont = nil }
}

/// Resident memory of all WebKit WebContent processes, in MB.
func webContentRSS() -> Double {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/ps")
    p.arguments = ["-axo", "rss=,comm="]
    let pipe = Pipe()
    p.standardOutput = pipe
    try? p.run()
    // read before waiting: ps writes more than a pipe buffer holds
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    let out = String(decoding: data, as: UTF8.self)
    return out.split(separator: "\n").filter { $0.contains("WebContent") }
        .compactMap { Double($0.split(separator: " ").first ?? "") }.reduce(0, +) / 1024
}
#endif
