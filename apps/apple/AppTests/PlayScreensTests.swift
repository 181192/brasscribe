#if os(macOS)
import AppKit
import Foundation
import ScoreKit
import ScreenCatalogue
import SwiftUI
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// The screen catalogue of Play for Mac (README, Testing): every screen and sheet off screen at one window size, in
/// light, dark and increased contrast (light and dark), and in bokmål (`scripts/screenshots.sh compare`, which runs
/// these tests a second time under `-testLanguage nb`), with the shared checks (`ScreenCatalogue`) and a screenshot
/// each. `ResponsiveLayoutTests` keeps the layout at every window size. A new screen gets an entry here.
@MainActor
@Suite(.serialized, .timeLimit(.minutes(10)), .enabled(if: fixtureDir() != nil)) struct PlayScreensTests {
    struct Variant: Sendable {
        let name: String
        let dark: Bool
        let increasedContrast: Bool
    }

    /// macOS has no Dynamic Type for an app's windows and Play no text size of its own, so there is no large-text
    /// variant here; the score's own zoom is checked by `ResponsiveLayoutTests` and the music stand's tests.
    static var variants: [Variant] {
        let light = Variant(name: "light", dark: false, increasedContrast: false)
        guard language == "en" else { return [light] }
        return [light, Variant(name: "dark", dark: true, increasedContrast: false), Variant(name: "contrast", dark: false, increasedContrast: true),
                Variant(name: "contrast-dark", dark: true, increasedContrast: true)]
    }

    /// The window: the usual size of a laptop's window (ResponsiveLayoutTests has the others).
    static let window = CGSize(width: 1280, height: 800 - OffscreenHost.toolbarHeight)

    /// Findings that are known and not yet fixed, each with its issue: the screen, the kind, and words the finding names.
    /// The words in the run's language, as the app looks them up.
    static var known: [(screen: String?, kind: Finding.Kind, words: String, issue: String)] {
        [
            ("sheet-settings", .outOfOrder, "comes after AXButton “\(String(localized: "Done"))”", "#254"),
            ("sheet-settings", .smallTarget, "“\(String(localized: "Version \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")"))”", "#256"),
        ]
    }

    /// Screens that are checked but get no screenshot: they do not draw the same twice yet, each with its issue.
    static let unsteady: [String: String] = ["review": "#260"]

    /// Screens whose own order differs from reading order, and why.
    static let ownOrder: [String: String] = [
        "score": "the controls drawn over the score come before it, so VoiceOver and the UI tests reach them (README)",
        "stand": "the controls drawn over the score come before it, so VoiceOver and the UI tests reach them (README)",
    ]

    nonisolated static var language: String { Bundle.main.preferredLocalizations.first ?? "en" }
    nonisolated static var checks: Bool { ProcessInfo.processInfo.environment["CATALOGUE_CHECKS"] != "0" }

    /// CATALOGUE_OUT (TEST_RUNNER_CATALOGUE_OUT on the xcodebuild line), or build/catalogue/screenshots.
    static var output: URL {
        if let dir = ProcessInfo.processInfo.environment["CATALOGUE_OUT"], !dir.isEmpty { return URL(fileURLWithPath: dir, isDirectory: true) }
        return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "build/catalogue/screenshots", directoryHint: .isDirectory)
    }

    /// The faces Play draws text in: the system font and Instrument Serif (titles, the score's title).
    static let text = TextFit(fonts: ["InstrumentSerif-Regular", "InstrumentSerif-Italic"])

    /// Checks the screen on `host`, then writes its screenshot and tree.
    private func record(_ host: OffscreenHost, _ screen: String, _ v: Variant, controls: Bool = true) async throws {
        let name = Self.language == "en" ? "\(screen)-\(v.name)" : "\(screen)-\(v.name)-\(Self.language)"
        let picture = await steady(host)
        let nodes = AXTree.read(host.hosting)
        if let broken = Guards.tree(nodes, screen: name, controls: controls) { Issue.record(Comment(rawValue: broken)) }
        let findings = Checks.run(nodes, bounds: host.hosting.bounds, text: Self.text).filter { f in
            !(f.kind == .outOfOrder && Self.ownOrder[screen] != nil)
                && !Self.known.contains { ($0.screen == nil || $0.screen == screen) && $0.kind == f.kind && f.node.contains($0.words) }
        }
        if Self.checks {
            #expect(findings.isEmpty, "\(name):\n\(findings.map { "  \($0)" }.joined(separator: "\n"))")
        }
        guard Self.unsteady[screen] == nil else { return }
        try Pictures.write(picture, tree: nodes, name: name, to: Self.output)
    }

    /// The picture once it stops changing (a score scrolling to its note, a list settling), or the last of a few tries:
    /// the same screen must give the same pixels every time.
    private func steady(_ host: OffscreenHost) async -> NSBitmapImageRep {
        var rep = host.bitmap()
        for _ in 0..<10 {
            await host.settle(0.3)
            let next = host.bitmap()
            if next.tiffRepresentation == rep.tiffRepresentation { return next }
            rep = next
        }
        return rep
    }

    /// A screen in the window, the library beside it, as `RootView` lays it out.
    private func window(_ screen: String, app: AppModel, sidebar: Bool = true, opened: (() -> Void)? = nil,
                        wait: (() -> Bool)? = nil, @ViewBuilder _ content: () -> some View) async throws {
        for v in Self.variants {
            let host = OffscreenHost(HarnessShell(sidebar: sidebar) { content() }.environment(app), size: Self.window,
                                     dark: v.dark, increasedContrast: v.increasedContrast)
            if let opened { await host.settle(0.8); opened() }
            if let wait { await host.settle(until: wait) } else { await host.settle(0.8) }
            try await record(host, screen, v)
            host.close()
        }
    }

    /// A sheet at the size it opens at: its ideal, within its minimum and maximum.
    private func sheet(_ screen: String, app: AppModel, controls: Bool = true, @ViewBuilder _ content: () -> some View) async throws {
        let root = content().environment(app).tint(Color.Brasscribe.primary)
        let measured = Measure.sizes(root)
        let size = CGSize(width: min(max(measured.ideal.width, measured.min.width), measured.max.width),
                          height: min(max(measured.ideal.height, measured.min.height), measured.max.height))
        for v in Self.variants {
            let host = OffscreenHost(root, size: size, dark: v.dark, increasedContrast: v.increasedContrast)
            await host.settle(0.8)
            try await record(host, "sheet-\(screen)", v, controls: controls)
            host.close()
        }
    }

    @Test func everyScreen() async throws {
        AXTree.enableInProcess()
        LayoutFixtures.freshLibrary()

        let empty = LayoutFixtures.app()
        try await window("home-empty", app: empty) { HomeView() }
        let full = LayoutFixtures.app()
        try LayoutFixtures.library(full)
        try await window("home-scores", app: full) { HomeView() }
        try await window("home-offline", app: LayoutFixtures.app(connection: .offline)) { HomeView() }

        let src = PendingSource(audioURL: ScreenshotScenes.sceneRecording, title: "Band practice", name: "Band practice.m4a")
        try await window("source", app: full) { SourceView(source: src) }
        let job = TranscriptionJob(source: src, profile: .brassBand, output: OutputChoice(), service: FrozenService())
        full.jobs[job.id] = job
        job.start { _ in }
        try await window("transcribing", app: full) { TranscribeView(jobID: job.id) }

        let piece = try LayoutFixtures.piece()
        try await window("output", app: full) { OutputView(piece: piece) }
        let score = try await LayoutFixtures.model(piece)
        try await window("score", app: full, wait: { !score.pages.isEmpty && !score.engraving }) { PracticeView(model: score).pageBackground() }
        score.stopAll()
        let stand = try await LayoutFixtures.model(piece)
        try await window("stand", app: full, opened: { if stand.stand == nil { stand.enterStand(from: .toolbar) } },
                         wait: { stand.stand != nil && !stand.pages.isEmpty && !stand.engraving }) { ScoreOrStand(model: stand) }
        stand.leaveStand()
        stand.stopAll()
        try await window("review", app: full) { ReviewView(piece: piece) }
        try await window("problem-silence", app: full) { ProblemView(problem: .silence) }

        try await sheet("settings", app: full) { SettingsView() }
        let exportModel = try await LayoutFixtures.model(piece)
        try await sheet("export", app: full) { ExportView(model: exportModel) }
        try await sheet("talking-score", app: full) { TalkingScoreView(model: exportModel) }
        exportModel.stopAll()
        try await sheet("first-run", app: full) { FirstRunView() }
        try await sheet("record-mic", app: full) { MicRecordView() }
        try await sheet("match-code", app: full, controls: false) { MatchCodeView(code: "4821").padding(Space.s5) }
    }

    /// The undocumented hooks still do what the catalogue needs, and the run is in the language it says.
    @Test func hooksStillWork() async {
        if let wrong = Guards.language(Self.language, localized: String(localized: "Record with the microphone"), english: "Record with the microphone") {
            Issue.record(Comment(rawValue: wrong))
        }
        let host = OffscreenHost(ContrastProbe().frame(width: 20, height: 20), size: CGSize(width: 20, height: 20), increasedContrast: true)
        await host.settle(0.2)
        if let broken = Guards.contrast(Pictures.bitmap(of: host.hosting)) { Issue.record(Comment(rawValue: broken)) }
        host.close()
    }
}
#endif
