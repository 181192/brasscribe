#if os(iOS)
import Foundation
import ScoreKit
import ScreenCatalogue
import SwiftUI
import Testing
import TranscriptionKit
import UIKit
@testable import BrasscribePlay

/// The screen catalogue of Play on an iPhone (README, Screen catalogue (iPhone)): every screen and sheet as the phone
/// shows it, in a navigation stack filling the screen of the simulator it runs on. On an iPhone 17e (the smallest phone
/// of the newest iOS): upright at the default text size in light and dark and at XXL, and on its side; on an iPhone SE
/// (375 × 667, the shortest screen): upright at the default text size and at XXL. In English, and in bokmål when the run
/// is (`make test-iphone-catalogue` runs both, on both phones). Each with the catalogue's checks (`ScreenCatalogue`):
/// every control has a name and a target of at least 44 × 44 pt, no text is cut off or outside the screen, the controls
/// are in reading order, and every text can be read on its ground; and a screenshot each. A new screen gets an entry
/// here and in the Mac's `PlayScreensTests`.
@MainActor
@Suite(.serialized, .timeLimit(.minutes(15)), .enabled(if: fixtureDir() != nil)) struct PhoneScreensTests {
    static var language: String { Bundle.main.preferredLocalizations.first ?? "en" }

    /// The shortest screen: an iPhone SE, 375 × 667 pt.
    static var shortScreen: Bool { (UIApplication.shared.connectedScenes.first as? UIWindowScene).map { max($0.screen.bounds.width, $0.screen.bounds.height) < 700 } ?? false }

    /// A modern phone: upright at the default size, light and dark, and at XXL; on its side at the default size. The
    /// shortest screen: upright at the default size and at XXL.
    static var variants: [PhoneAsked] {
        shortScreen ? [PhoneAsked(), PhoneAsked(textSize: .xxLarge)]
            : [PhoneAsked(), PhoneAsked(dark: true), PhoneAsked(textSize: .xxLarge), PhoneAsked(landscape: true)]
    }

    /// The least target on a phone, where a finger is the pointer (Android's catalogue asks 48 dp).
    static let target: CGFloat = 44

    /// Findings that are known and not yet fixed, each with why: the screen (nil for every screen), the kind, and the
    /// words the finding names, in English and in bokmål.
    static let known: [(screen: String?, kind: Finding.Kind, words: [String], why: String)] = [
        ("score", .smallTarget, ["AXButton “Bar ", "AXButton “Takt "],
         "a bar of the score is a VoiceOver stop the height of its staff (about 36 pt); a finger taps the music, not the bar's frame"),
        ("talking-score", .smallTarget, ["“Part, ", "“Stemme, "],
         "the part picker is a system menu 34 pt high; its row takes the whole width, with nothing beside it to hit instead"),
    ]

    /// Screens whose own order differs from reading order, and why.
    static let ownOrder: [String: String] = [
        "score": "the controls drawn over the score come before it, so VoiceOver and the UI tests reach them (README)",
    ]

    /// CATALOGUE_OUT (TEST_RUNNER_CATALOGUE_OUT on the xcodebuild line), or build/catalogue/iphone.
    static var output: URL {
        if let dir = ProcessInfo.processInfo.environment["CATALOGUE_OUT"], !dir.isEmpty { return URL(fileURLWithPath: dir, isDirectory: true) }
        return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appending(path: "build/catalogue/iphone", directoryHint: .isDirectory)
    }

    /// The faces Play draws text in: the system font and Instrument Serif (titles).
    static let text = TextFit(fonts: ["InstrumentSerif-Regular", "InstrumentSerif-Italic"])

    /// `content` in a navigation stack, as the phone shows a screen, in every variant: taken, checked and written.
    private func screen(_ screen: String, app: AppModel, controls: Bool = true, opened: (() -> Void)? = nil,
                        ready: @escaping () -> String? = { nil }, shows: @escaping ([AXNode]) -> String? = { _ in nil },
                        @ViewBuilder _ content: () -> some View) async throws {
        for v in Self.variants {
            if v.landscape != (UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first?.effectiveGeometry
                .interfaceOrientation.isLandscape ?? false) { await PhoneHost.turn(landscape: v.landscape) }
            let host = PhoneHost(NavigationStack { content() }.environment(app).playHost(app).tint(Color.Scribe.primary), asked: v)
            defer { host.close() }
            await host.settle(0.5)
            if let opened { opened(); await host.settle(0.5) }
            let phone = Self.shortScreen ? "se-" : ""
            let name = Self.language == "en" ? "\(phone)\(screen)-\(v.name)" : "\(phone)\(screen)-\(v.name)-\(Self.language)"
            var nodes: [AXNode] = []
            do {
                let taken = try await host.take(name, controls: controls, ready: ready, shows: shows, output: Self.output)
                nodes = taken.nodes
                try Pictures.write(taken.picture, tree: nodes, name: name, to: Self.output)
            } catch let notTaken as ScreenNotTaken {
                Issue.record(Comment(rawValue: notTaken.description))
                guard !notTaken.nodes.isEmpty else { continue }
                nodes = notTaken.nodes
            }
            if let broken = Guards.tree(nodes, screen: name, controls: controls) { Issue.record(Comment(rawValue: broken)) }
            let findings = Checks.run(nodes, bounds: host.window.bounds, text: Self.text, target: Self.target).filter { f in
                !(f.kind == .outOfOrder && Self.ownOrder[screen] != nil)
                    && !Self.known.contains { k in (k.screen == nil || k.screen == screen) && k.kind == f.kind && k.words.contains { f.node.contains($0) } }
            }
            #expect(findings.isEmpty, "\(name):\n\(findings.map { "  \($0)" }.joined(separator: "\n"))")
        }
        await PhoneHost.turn(landscape: false)
    }

    @Test func everyScreen() async throws {
        AXTree.enableInProcess()
        LayoutFixtures.freshLibrary()

        let empty = LayoutFixtures.app()
        try await screen("home-empty", app: empty) { HomeView() }
        let full = LayoutFixtures.app()
        try LayoutFixtures.library(full)
        try await screen("home-scores", app: full) { HomeView() }
        try await screen("home-offline", app: LayoutFixtures.app(connection: .offline)) { HomeView() }

        let src = PendingSource(audioURL: ScreenshotScenes.sceneRecording, title: "Band practice", name: "Band practice.m4a")
        try await screen("source", app: full) { SourceView(source: src) }
        let job = TranscriptionJob(source: src, profile: .brassBand, output: OutputChoice(), service: FrozenService())
        full.jobs[job.id] = job
        job.start { _ in }
        try await screen("transcribing", app: full) { TranscribeView(jobID: job.id) }

        let piece = try LayoutFixtures.piece()
        try await screen("output", app: full) { OutputView(piece: piece) }
        let score = try await LayoutFixtures.model(piece)
        try await screen("score", app: full, ready: { !score.pages.isEmpty && !score.engraving ? nil : "its score is not engraved yet" }) {
            PracticeView(model: score).pageBackground()
        }
        score.stopAll()
        let composition = try LayoutFixtures.makeFirstNoteVeryUnsure(piece)
        try await screen("review", app: full) { ReviewView(piece: piece) }
        try piece.saveComposition(composition)
        try await screen("problem-silence", app: full) { ProblemView(problem: .silence) }

        try await screen("settings", app: full) { SettingsView() }
        try await screen("what-you-play", app: full) { WhatDoYouPlayView(mode: .settings, initial: full.seat) { _ in } }
        let exportModel = try await LayoutFixtures.model(piece)
        try await screen("export", app: full) { ExportView(model: exportModel) }
        try await screen("talking-score", app: full) { TalkingScoreView(model: exportModel) }
        exportModel.stopAll()
        try await screen("first-run", app: full) { FirstRunView() }
        try await screen("record-mic", app: full) { MicRecordView() }
    }
}
#endif
