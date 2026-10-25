import Foundation
import WebKit
import os

/// The colours the page draws in, as CSS colours (`#rrggbb`, or `#rrggbbaa` for a wash).
public struct TabPalette: Codable, Equatable, Sendable {
    public var ink: String
    public var string: String
    public var uncertain: String
    public var cursor: String
    /// The wash behind the beat being played; nil in high contrast, which has shapes only.
    public var cursorTint: String?

    public init(ink: String, string: String, uncertain: String, cursor: String, cursorTint: String?) {
        self.ink = ink; self.string = string; self.uncertain = uncertain; self.cursor = cursor; self.cursorTint = cursorTint
    }
}

/// One bar of the engraving, in the page's points: its box. `bar` counts from 0, as written.
public struct TabBarBox: Codable, Equatable, Sendable {
    public var bar: Int
    public var x: Double, y: Double, w: Double, h: Double
}

/// The engraving once alphaTab has laid the page out.
public struct TabEngraving: Equatable, Sendable {
    public var height: Double
    public var width: Double
    public var bars: [TabBarBox]
    /// How long alphaTab took, from the song to the laid-out page.
    public var milliseconds: Int
    /// Every resource the page loaded, as URLs: all of them are the app's own.
    public var resources: [String]
    /// The page's fonts and whether each loaded ("family:loaded").
    public var fonts: [String]
}

/// The tab page: alphaTab in a web view, loaded from the app's own files under a scheme of its own, with no network.
/// The view is hidden from VoiceOver: the screen that shows it describes the tab with its own elements.
@MainActor @Observable
public final class TabPage: NSObject {
    public static let scheme = "tabpage"
    @ObservationIgnored public let webView: WKWebView
    @ObservationIgnored private let assets = TabAssets()
    @ObservationIgnored private var ready: [CheckedContinuation<Void, Never>] = []
    @ObservationIgnored private var isReady = false
    @ObservationIgnored private var waiting: CheckedContinuation<TabEngraving, Error>?
    public private(set) var engraving: TabEngraving?
    @ObservationIgnored public var onEngraving: ((TabEngraving) -> Void)?
    @ObservationIgnored nonisolated static let log = Logger(subsystem: "no.kalli.scribe", category: "tab")

    public struct PageError: Error, CustomStringConvertible {
        public let description: String
    }

    public override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.setURLSchemeHandler(assets, forURLScheme: Self.scheme)
        config.suppressesIncrementalRendering = true
        #if os(iOS)
        config.dataDetectorTypes = []
        #endif
        let controller = WKUserContentController()
        config.userContentController = controller
        webView = WKWebView(frame: CGRect(x: 0, y: 0, width: 600, height: 400), configuration: config)
        super.init()
        controller.add(WeakHandler(self), name: "tab")
        #if os(macOS)
        webView.setValue(false, forKey: "drawsBackground")
        webView.setAccessibilityElement(false)
        webView.setAccessibilityHidden(true)
        #else
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false
        webView.accessibilityElementsHidden = true
        webView.isAccessibilityElement = false
        #endif
        webView.load(URLRequest(url: URL(string: "\(Self.scheme)://page/index.html")!))
    }

    /// Blocks every request that would leave the device, so a page that needs the network fails instead of fetching.
    public func blockNetwork() async throws {
        let rules = #"[{"trigger":{"url-filter":"^https?://"},"action":{"type":"block"}},{"trigger":{"url-filter":"^wss?://"},"action":{"type":"block"}}]"#
        let list = try await WKContentRuleListStore.default().compileContentRuleList(forIdentifier: "no-network", encodedContentRuleList: rules)
        if let list { webView.configuration.userContentController.add(list) }
    }

    /// Waits for the page's script to be loaded.
    public func loaded() async {
        if isReady { return }
        await withCheckedContinuation { ready.append($0) }
    }

    /// Engraves [musicXML] in [palette]; returns once the page is laid out.
    public func show(musicXML: Data, palette: TabPalette, scale: Double = 1, staff: String = "tab", doubtful: [String] = []) async throws -> TabEngraving {
        await loaded()
        struct Options: Encodable { let scale: Double; let palette: TabPalette; let staff: String; let doubtful: [String] }
        let opts = String(decoding: try JSONEncoder().encode(Options(scale: scale, palette: palette, staff: staff, doubtful: doubtful)), as: UTF8.self)
        return try await withCheckedThrowingContinuation { c in
            waiting = c
            webView.evaluateJavaScript("tab.show('\(musicXML.base64EncodedString())', \(opts)); 0") { _, error in
                if let error { self.finish(.failure(error)) }
            }
        }
    }

    /// The same page in other colours (another appearance).
    public func palette(_ palette: TabPalette) async throws -> TabEngraving {
        let p = String(decoding: try JSONEncoder().encode(palette), as: UTF8.self)
        return try await withCheckedThrowingContinuation { c in
            waiting = c
            webView.evaluateJavaScript("tab.palette(\(p)); 0") { _, error in
                if let error { self.finish(.failure(error)) }
            }
        }
    }

    /// Stands the cursor at [tick] (960 to a quarter, from the bar's start) of [bar] (from 0); nil hides it.
    /// Returns where it stands, in the page's points.
    @discardableResult
    public func cursor(bar: Int?, tick: Int = 0) async throws -> CGRect? {
        let js = bar.map { "tab.cursorAt(\($0), \(tick))" } ?? "tab.cursorAt(null, 0)"
        let r = try await webView.evaluateJavaScript(js)
        guard let d = r as? [String: Any], let x = d["x"] as? Double, let y = d["y"] as? Double, let h = d["h"] as? Double else { return nil }
        return CGRect(x: x, y: y, width: 2, height: h)
    }

    private func finish(_ result: Result<TabEngraving, Error>) {
        let c = waiting
        waiting = nil
        c?.resume(with: result)
    }

    fileprivate func received(_ body: Any) {
        guard let m = body as? [String: Any], let kind = m["kind"] as? String else { return }
        switch kind {
        case "ready":
            isReady = true
            ready.forEach { $0.resume() }
            ready = []
        case "error":
            let message = m["message"] as? String ?? "?"
            Self.log.error("tab page: \(message, privacy: .public)")
            finish(.failure(PageError(description: message)))
        case "rendered":
            let bars = (m["bars"] as? [[String: Any]] ?? []).compactMap { b -> TabBarBox? in
                guard let bar = b["bar"] as? Int else { return nil }
                return TabBarBox(bar: bar, x: b["x"] as? Double ?? 0, y: b["y"] as? Double ?? 0, w: b["w"] as? Double ?? 0, h: b["h"] as? Double ?? 0)
            }
            let e = TabEngraving(height: m["height"] as? Double ?? 0, width: m["width"] as? Double ?? 0, bars: bars,
                                 milliseconds: m["ms"] as? Int ?? 0, resources: assets.requested, fonts: m["fonts"] as? [String] ?? [])
            engraving = e
            onEngraving?(e)
            finish(.success(e))
        default:
            break
        }
    }

    private final class WeakHandler: NSObject, WKScriptMessageHandler {
        weak var page: TabPage?
        init(_ page: TabPage) { self.page = page }
        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            let body = message.body
            MainActor.assumeIsolated { page?.received(body) }
        }
    }
}

/// Serves the page's files from the package's resources. Every request is recorded.
final class TabAssets: NSObject, WKURLSchemeHandler {
    private let root = Bundle.module.url(forResource: "page", withExtension: nil)!
    nonisolated(unsafe) private(set) var requested: [String] = []

    func webView(_ webView: WKWebView, start task: any WKURLSchemeTask) {
        guard let url = task.request.url else { return }
        requested.append(url.absoluteString)
        let path = url.path.drop(while: { $0 == "/" })
        let file = root.appending(path: String(path))
        guard file.standardizedFileURL.path.hasPrefix(root.standardizedFileURL.path), let data = try? Data(contentsOf: file) else {
            task.didFailWithError(URLError(.fileDoesNotExist))
            return
        }
        let type: String = switch file.pathExtension {
        case "html": "text/html"
        case "js": "text/javascript"
        case "woff2": "font/woff2"
        default: "application/octet-stream"
        }
        task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                        headerFields: ["Content-Type": type, "Content-Length": "\(data.count)"])!)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: any WKURLSchemeTask) {}
}
