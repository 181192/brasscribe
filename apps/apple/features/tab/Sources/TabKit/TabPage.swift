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

/// One line of the engraving, in the page's points: where it is, and its first and last bar (counted from 0).
public struct TabLine: Codable, Equatable, Sendable {
    public var top: Double, bottom: Double
    public var first: Int, last: Int

    public init(top: Double, bottom: Double, first: Int, last: Int) {
        self.top = top; self.bottom = bottom; self.first = first; self.last = last
    }
}

/// A mark the screen draws over the page ("?" above a doubtful note, a boxed "!" above a note with no place): the
/// column it stands over, and the notes there. `string` counts from the top line, as the tab's data does; a note on a
/// notation staff is found by its `pitchClass` (0 is C).
public struct TabMarkSpot: Encodable, Equatable, Sendable {
    public struct Note: Encodable, Equatable, Sendable {
        public var string: Int?
        public var fret: Int?
        public var pitchClass: Int?
        /// In doubt: its numeral (or note head) takes the doubt colour.
        public var doubt: Bool

        public init(string: Int?, fret: Int?, pitchClass: Int?, doubt: Bool) {
            self.string = string; self.fret = fret; self.pitchClass = pitchClass; self.doubt = doubt
        }
    }

    public var staff: Int
    /// The measure, counted from 0 as written.
    public var bar: Int
    /// From the start of the measure, in `TabIndex.ticks` to a quarter note.
    public var tick: Int
    public var notes: [Note]

    public init(staff: Int, bar: Int, tick: Int, notes: [Note]) {
        self.staff = staff; self.bar = bar; self.tick = tick; self.notes = notes
    }
}

/// Where a mark goes in the engraving, in the page's points: `mark` is its place in the spots the page was shown with,
/// `x` the middle of its column, `top` and `bottom` the mark itself, `columnBottom` how far down the column's numerals
/// go, and `width` how wide the mark and the numerals are.
public struct TabMarkBox: Codable, Equatable, Sendable {
    public var mark: Int
    public var x: Double
    public var top: Double, bottom: Double
    public var columnBottom: Double
    public var width: Double

    public init(mark: Int, x: Double, top: Double, bottom: Double, columnBottom: Double, width: Double) {
        self.mark = mark; self.x = x; self.top = top; self.bottom = bottom; self.columnBottom = columnBottom; self.width = width
    }
}

/// The engraving once alphaTab has laid the page out.
public struct TabEngraving: Equatable, Sendable {
    public var height: Double
    public var width: Double
    public var bars: [TabBarBox]
    /// The lines of the page, top to bottom.
    public var lines: [TabLine] = []
    /// Where the marks the page was shown with go; a mark the page has no beat for is left out.
    public var marks: [TabMarkBox] = []
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
    /// One engraving at a time: a call waits here until the one before it has its answer.
    @ObservationIgnored private var turn: [CheckedContinuation<Void, Never>] = []
    @ObservationIgnored private var inTurn = false
    /// The rule that keeps the page off the network is in place (it is, before the page is first loaded).
    @ObservationIgnored public private(set) var networkBlocked = false
    /// Why the page is not shown: the rule that keeps it off the network could not be put in place, so it is never
    /// loaded. Nil while it can be.
    public private(set) var unavailable: String?
    public private(set) var engraving: TabEngraving?
    @ObservationIgnored public var onEngraving: ((TabEngraving) -> Void)?
    @ObservationIgnored nonisolated static let log = Logger(subsystem: "no.kalli.scribe", category: "tab")

    public struct PageError: Error, CustomStringConvertible {
        public let description: String
    }

    public override convenience init() { self.init(rules: TabPage.noNetwork) }

    /// [rules] is the content rule list that keeps the page off the network; a test hands in one that does not compile.
    init(rules: String) {
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
        // The page is loaded only once the rule that blocks every request leaving the device is in place: a page that
        // needed the network would fail instead of fetching.
        // Without that rule the page is not loaded at all, and every call on it fails (`unavailable`).
        Task { [weak self] in
            guard let self else { return }
            if let why = await blockNetwork(rules: rules) {
                unavailable = why
                ready.forEach { $0.resume() }
                ready = []
                return
            }
            webView.load(URLRequest(url: URL(string: "\(Self.scheme)://page/index.html")!))
        }
    }

    static let noNetwork = #"[{"trigger":{"url-filter":"^https?://"},"action":{"type":"block"}},{"trigger":{"url-filter":"^wss?://"},"action":{"type":"block"}}]"#

    /// Puts the rule in place; returns why it could not be, nil when it is.
    func blockNetwork(rules: String = TabPage.noNetwork) async -> String? {
        do {
            let list = try await WKContentRuleListStore.default().compileContentRuleList(forIdentifier: "no-network", encodedContentRuleList: rules)
            guard let list else { return "no rule list" }
            webView.configuration.userContentController.add(list)
            networkBlocked = true
            return nil
        } catch {
            Self.log.error("the rule that keeps the tab page off the network could not be made: \(String(describing: error), privacy: .public)")
            return String(describing: error)
        }
    }

    /// Waits for the engraving before this one to have its answer.
    private func takeTurn() async {
        if !inTurn { inTurn = true; return }
        await withCheckedContinuation { turn.append($0) }
    }

    private func endTurn() {
        if turn.isEmpty { inTurn = false } else { turn.removeFirst().resume() }
    }

    /// The files the page asked for, as URLs: all of them are the app's own.
    public var requested: [String] { assets.requested }

    /// Waits for the page's script to be loaded.
    public func loaded() async {
        if isReady || unavailable != nil { return }
        await withCheckedContinuation { ready.append($0) }
    }

    /// Fails when the page is not shown (`unavailable`).
    private func usable() throws {
        if let unavailable { throw PageError(description: "the tab page is not shown: \(unavailable)") }
    }

    /// Engraves [musicXML] in [palette]; returns once the page is laid out. [doubtful] notes ("bar:string:fret:tick", the
    /// string counted from the lowest) take the doubt colour, and so do the notes in doubt of [marks], whose places the
    /// engraving says. [markStaff] is the staff the marks and the cursor stand on.
    public func show(musicXML: Data, palette: TabPalette, scale: Double = 1, staff: String = "tab", doubtful: [String] = [],
                     marks: [TabMarkSpot] = [], markStaff: Int = 0) async throws -> TabEngraving {
        await loaded()
        try usable()
        await takeTurn()
        defer { endTurn() }
        struct Options: Encodable {
            let scale: Double; let palette: TabPalette; let staff: String; let doubtful: [String]; let marks: [TabMarkSpot]; let markStaff: Int
        }
        let opts = String(decoding: try JSONEncoder().encode(Options(scale: scale, palette: palette, staff: staff, doubtful: doubtful,
                                                                     marks: marks, markStaff: markStaff)), as: UTF8.self)
        return try await withCheckedThrowingContinuation { c in
            replace(with: c)
            webView.evaluateJavaScript("tab.show('\(musicXML.base64EncodedString())', \(opts)); 0") { _, error in
                if let error { self.finish(.failure(error)) }
            }
        }
    }

    /// The same page in other colours (another appearance).
    public func palette(_ palette: TabPalette) async throws -> TabEngraving {
        await loaded()
        try usable()
        await takeTurn()
        defer { endTurn() }
        let p = String(decoding: try JSONEncoder().encode(palette), as: UTF8.self)
        return try await withCheckedThrowingContinuation { c in
            replace(with: c)
            webView.evaluateJavaScript("tab.palette(\(p)); 0") { _, error in
                if let error { self.finish(.failure(error)) }
            }
        }
    }

    /// Stands the cursor at [tick] (960 to a quarter, from the bar's start) of [bar] (from 0); nil hides it.
    /// Returns where it stands, in the page's points.
    @discardableResult
    public func cursor(bar: Int?, tick: Int = 0) async throws -> CGRect? {
        try usable()
        let js = bar.map { "tab.cursorAt(\($0), \(tick))" } ?? "tab.cursorAt(null, 0)"
        let r = try await webView.evaluateJavaScript(js)
        guard let d = r as? [String: Any], let x = d["x"] as? Double, let y = d["y"] as? Double, let h = d["h"] as? Double else { return nil }
        return CGRect(x: x, y: y, width: 2, height: h)
    }

    /// A new engraving asked for while one is being laid out: the one asked for before is told it was replaced.
    private func replace(with c: CheckedContinuation<TabEngraving, Error>) {
        finish(.failure(PageError(description: "replaced by a newer engraving")))
        waiting = c
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
            let lines = (m["lines"] as? [[String: Any]] ?? []).compactMap { l -> TabLine? in
                guard let first = l["first"] as? Int, let last = l["last"] as? Int else { return nil }
                return TabLine(top: l["top"] as? Double ?? 0, bottom: l["bottom"] as? Double ?? 0, first: first, last: last)
            }
            let marks = (m["marks"] as? [[String: Any]] ?? []).compactMap { b -> TabMarkBox? in
                guard let mark = b["mark"] as? Int else { return nil }
                return TabMarkBox(mark: mark, x: b["x"] as? Double ?? 0, top: b["top"] as? Double ?? 0, bottom: b["bottom"] as? Double ?? 0,
                                  columnBottom: b["columnBottom"] as? Double ?? 0, width: b["w"] as? Double ?? 0)
            }
            let e = TabEngraving(height: m["height"] as? Double ?? 0, width: m["width"] as? Double ?? 0, bars: bars, lines: lines, marks: marks,
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
