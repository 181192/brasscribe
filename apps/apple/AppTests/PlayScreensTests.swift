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
/// light, dark and increased contrast (light and dark), and in bokmål (`scripts/screenshots.sh record`, which runs
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
        []
    }

    /// Screens that are checked but get no screenshot: they do not draw the same twice yet, each with its issue.
    static let unsteady: [String: String] = [:]

    /// Screens whose own order differs from reading order, and why.
    static let ownOrder: [String: String] = [
        "score": "the controls drawn over the score come before it, so VoiceOver and the UI tests reach them (README)",
        "stand": "the controls drawn over the score come before it, so VoiceOver and the UI tests reach them (README)",
    ]

    nonisolated static var language: String { Bundle.main.preferredLocalizations.first ?? "en" }

    /// CATALOGUE_OUT (TEST_RUNNER_CATALOGUE_OUT on the xcodebuild line), or build/catalogue/screenshots.
    static var output: URL {
        if let dir = ProcessInfo.processInfo.environment["CATALOGUE_OUT"], !dir.isEmpty { return URL(fileURLWithPath: dir, isDirectory: true) }
        return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appending(path: "build/catalogue/screenshots", directoryHint: .isDirectory)
    }

    /// The faces Play draws text in: the system font and Instrument Serif (titles, the score's title).
    static let text = TextFit(fonts: ["InstrumentSerif-Regular", "InstrumentSerif-Italic"])

    /// Takes the screen on `host` by the catalogue's rule (`ScreenTake`), checks it, and writes its screenshot and tree.
    /// A screen that does not become the one asked for is not taken, and fails the run; after three, the catalogue stops.
    private func record(_ host: OffscreenHost, _ screen: String, _ v: Variant, controls: Bool = true, ready: () -> String? = { nil },
                        shows: ([AXNode]) -> String? = { _ in nil }) async throws {
        let name = Self.language == "en" ? "\(screen)-\(v.name)" : "\(screen)-\(v.name)-\(Self.language)"
        let nodes: [AXNode]
        var picture: NSBitmapImageRep?
        if Self.unsteady[screen] == nil {
            do {
                let take = try await host.take(name, controls: controls, ready: ready, shows: shows, output: Self.output)
                nodes = take.nodes
                picture = take.picture
                if let stale = take.stale { Issue.record(Comment(rawValue: stale)) }
            } catch let notTaken as ScreenNotTaken {
                // No screenshot; its checks still run on the tree it had, when it had one.
                Issue.record(Comment(rawValue: notTaken.description))
                guard !notTaken.nodes.isEmpty else { return }
                nodes = notTaken.nodes
            }
        } else {
            await host.settle(0.8)
            nodes = AXTree.read(host.hosting)
        }
        if let broken = Guards.tree(nodes, screen: name, controls: controls) { Issue.record(Comment(rawValue: broken)) }
        let findings = Checks.run(nodes, bounds: host.hosting.bounds, text: Self.text).filter { f in
            !(f.kind == .outOfOrder && Self.ownOrder[screen] != nil)
                && !Self.known.contains { ($0.screen == nil || $0.screen == screen) && $0.kind == f.kind && f.node.contains($0.words) }
        }
        #expect(findings.isEmpty, "\(name):\n\(findings.map { "  \($0)" }.joined(separator: "\n"))")
        if let picture { try Pictures.write(picture, tree: nodes, name: name, to: Self.output) }
    }

    /// A screen in the window, the library beside it, as `RootView` lays it out. `opened` is run once the screen is
    /// up; `ready` says what the screen still waits for (nil when it is the screen to take), and `shows` the same of
    /// its accessibility tree.
    private func window(_ screen: String, app: AppModel, sidebar: Bool = true, opened: (() -> Void)? = nil,
                        ready: () -> String? = { nil }, shows: ([AXNode]) -> String? = { _ in nil },
                        @ViewBuilder _ content: () -> some View) async throws {
        for v in Self.variants {
            // Where the screen's own views are: in the detail column's navigation stack.
            let witness = AppearanceWitness()
            let host = OffscreenHost(HarnessShell(sidebar: sidebar) { content().catalogueWitness(witness) }.environment(app), size: Self.window,
                                     dark: v.dark, increasedContrast: v.increasedContrast, witness: witness)
            defer { host.close() }
            if let opened { await host.settle(0.8); opened() }
            try await record(host, screen, v, ready: ready, shows: shows)
        }
    }

    /// A sheet at the size it opens at: its ideal, within its minimum and maximum.
    private func sheet(_ screen: String, app: AppModel, controls: Bool = true, @ViewBuilder _ content: () -> some View) async throws {
        let root = content().environment(app).tint(Color.Scribe.primary)
        let measured = Measure.sizes(root)
        let size = CGSize(width: min(max(measured.ideal.width, measured.min.width), measured.max.width),
                          height: min(max(measured.ideal.height, measured.min.height), measured.max.height))
        for v in Self.variants {
            let host = OffscreenHost(root, size: size, dark: v.dark, increasedContrast: v.increasedContrast)
            defer { host.close() }
            try await record(host, "sheet-\(screen)", v, controls: controls)
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
        // Engraved, and scrolled to the bar it opens at with that bar's parts laid out: the pages come in after the model has them.
        let opensAt = score.barLabel(score.currentBar) + ","
        try await window("score", app: full, ready: { !score.pages.isEmpty && !score.engraving ? nil : "its score is not engraved yet" },
                         shows: { nodes in
                             nodes.contains { !$0.isOutOfView && $0.label.hasPrefix(opensAt) } ? nil : "its score's bars are not in view yet"
                         }) {
            PracticeView(model: score).pageBackground()
        }
        score.stopAll()
        let stand = try await LayoutFixtures.model(piece)
        try await window("stand", app: full, opened: { if stand.stand == nil { stand.enterStand(from: .toolbar) } },
                         ready: { stand.stand != nil && !stand.pages.isEmpty && !stand.engraving ? nil : "its score is not on the stand yet" }) {
            ScoreOrStand(model: stand)
        }
        stand.leaveStand()
        stand.stopAll()
        try await window("review", app: full) { ReviewView(piece: piece) }
        try await window("problem-silence", app: full) { ProblemView(problem: .silence) }

        try await sheet("settings", app: full) { SettingsView() }
        try await sheet("what-you-play", app: full) { NavigationStack { WhatDoYouPlayView(mode: .settings, initial: full.seat) { _ in } } }
        let exportModel = try await LayoutFixtures.model(piece)
        try await sheet("export", app: full) { ExportView(model: exportModel) }
        try await sheet("talking-score", app: full) { TalkingScoreView(model: exportModel) }
        exportModel.stopAll()
        try await sheet("first-run", app: full) { FirstRunView() }
        try await sheet("record-mic", app: full) { MicRecordView() }
        // On the surface, which stands in here for the Settings row the app shows it in: the view has no ground of
        // its own, and the row's is the form's.
        try await sheet("match-code", app: full, controls: false) {
            MatchCodeView(code: "4821").padding(Space.s5).background(Color.Scribe.surface)
        }
    }

    /// The hooks still do what the catalogue needs, and the run is in the language it says.
    @Test func hooksStillWork() async {
        if let wrong = Guards.language(Self.language, localized: String(localized: "Record with the microphone"), english: "Record with the microphone") {
            Issue.record(Comment(rawValue: wrong))
        }
        let host = OffscreenHost(NavigationStack { ContrastProbe() }, size: CGSize(width: 200, height: 200), increasedContrast: true)
        await host.settle(0.2)
        if let broken = Guards.contrast(Pictures.bitmap(of: host.hosting)) { Issue.record(Comment(rawValue: broken)) }
        host.close()
    }
}
#endif
