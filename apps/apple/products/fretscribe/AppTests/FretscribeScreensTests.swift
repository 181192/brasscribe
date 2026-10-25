#if os(macOS)
import AppKit
import Foundation
import ScreenCatalogue
import SwiftUI
import Testing
import TabKit
import TranscriptionKit
@testable import Fretscribe

/// The screen catalogue of Fretscribe for Mac: every screen and sheet off screen at one window size, in light, dark and
/// increased contrast (light and dark), and in bokmål (`scripts/screenshots.sh record fretscribe` runs these tests a
/// second time under `-testLanguage nb`), with the shared checks (`ScreenCatalogue`) and a screenshot each. A new
/// screen gets an entry here.
@MainActor
@Suite(.serialized, .timeLimit(.minutes(10))) struct FretscribeScreensTests {
    struct Variant: Sendable {
        let name: String
        let dark: Bool
        let increasedContrast: Bool
    }

    static var variants: [Variant] {
        let light = Variant(name: "light", dark: false, increasedContrast: false)
        guard language == "en" else { return [light] }
        return [light, Variant(name: "dark", dark: true, increasedContrast: false), Variant(name: "contrast", dark: false, increasedContrast: true),
                Variant(name: "contrast-dark", dark: true, increasedContrast: true)]
    }

    static let window = CGSize(width: 1280, height: 800 - OffscreenHost.toolbarHeight)

    nonisolated static var language: String { Bundle.main.preferredLocalizations.first ?? "en" }

    /// CATALOGUE_OUT (TEST_RUNNER_CATALOGUE_OUT on the xcodebuild line), or build/catalogue/fretscribe.
    static var output: URL {
        if let dir = ProcessInfo.processInfo.environment["CATALOGUE_OUT"], !dir.isEmpty { return URL(fileURLWithPath: dir, isDirectory: true) }
        return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appending(path: "build/catalogue/fretscribe", directoryHint: .isDirectory)
    }

    /// The faces Fretscribe draws text in: the system font and Atkinson Hyperlegible Next.
    static let text = TextFit(fonts: ["AtkinsonHyperlegibleNext-Regular"])

    static func fixture(_ name: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appending(path: "../../../../fixtures/\(name)").standardizedFileURL
    }

    /// A model with its own songs folder and settings, connected (staged) to a computer that is not asked anything.
    static func model(connection: ConnectionState = .connected(serverName: ConnectionLifecycle.stagedServerName)) -> FretscribeModel {
        let m = FretscribeModel(defaults: UserDefaults(suiteName: "fs-catalogue-\(UUID().uuidString)")!)
        m.firstRunDone = true
        let record = connection == .offline ? nil
            : EngineRecord(serverID: "7f3a9c2e", serverName: ConnectionLifecycle.stagedServerName, deviceID: "d-41b2", token: "staged",
                           lastAddress: "http://192.0.2.20:8765", lastOK: Date().addingTimeInterval(-12))
        m.connection.stage(connection, record: record)
        return m
    }

    /// A song from a fixture, kept in the catalogue's songs folder.
    static func song(_ fixture: String, title: String) throws -> TabSong {
        let xml = try Data(contentsOf: Self.fixture("\(fixture)/tab.musicxml"))
        let tab = try Data(contentsOf: Self.fixture("\(fixture)/tab.json"))
        return try TabSong.create(title: title, jobID: nil, musicXML: xml, tab: tab, recording: nil)
    }

    private func record(_ host: OffscreenHost, _ screen: String, _ v: Variant, ready: () -> String? = { nil },
                        shows: ([AXNode]) -> String? = { _ in nil }) async throws {
        let name = Self.language == "en" ? "\(screen)-\(v.name)" : "\(screen)-\(v.name)-\(Self.language)"
        let nodes: [AXNode]
        var picture: NSBitmapImageRep?
        do {
            let take = try await host.take(name, ready: ready, shows: shows, output: Self.output)
            nodes = take.nodes
            picture = take.picture
            if let stale = take.stale { Issue.record(Comment(rawValue: stale)) }
        } catch let notTaken as ScreenNotTaken {
            Issue.record(Comment(rawValue: notTaken.description))
            guard !notTaken.nodes.isEmpty else { return }
            nodes = notTaken.nodes
        }
        if let broken = Guards.tree(nodes, screen: name, controls: true) { Issue.record(Comment(rawValue: broken)) }
        // The tempo and the speed are read in words longer than what they show: not text cut off.
        let findings = Checks.run(nodes, bounds: host.hosting.bounds, text: Self.text).filter { f in
            !(f.kind == .clippedText && (["beats a minute", "slag i minuttet", "“Speed ", "“Tempo "].contains { f.node.contains($0) }))
        }
        #expect(findings.isEmpty, "\(name):\n\(findings.map { "  \($0)" }.joined(separator: "\n"))")
        if let picture { try Pictures.write(picture, tree: nodes, name: name, to: Self.output) }
    }

    /// A screen in the window, in a navigation stack as `RootView` has it.
    private func window(_ screen: String, model: FretscribeModel, ready: @escaping () -> String? = { nil },
                        shows: @escaping ([AXNode]) -> String? = { _ in nil }, @ViewBuilder _ content: () -> some View) async throws {
        for v in Self.variants {
            let witness = AppearanceWitness()
            let root = NavigationStack { content().catalogueWitness(witness) }.tint(Color.Scribe.primary)
                .environment(model).playHost(model)
            let host = OffscreenHost(root, size: Self.window, dark: v.dark, increasedContrast: v.increasedContrast, witness: witness)
            defer { host.close() }
            try await record(host, screen, v, ready: ready, shows: shows)
        }
    }

    /// A sheet at the size it opens at.
    private func sheet(_ screen: String, model: FretscribeModel, @ViewBuilder _ content: () -> some View) async throws {
        let root = content().environment(model).playHost(model).tint(Color.Scribe.primary)
        let measured = Measure.sizes(root)
        let size = CGSize(width: min(max(measured.ideal.width, measured.min.width), measured.max.width),
                          height: min(max(measured.ideal.height, measured.min.height, 480), max(measured.max.height, 480)))
        for v in Self.variants {
            let host = OffscreenHost(root, size: size, dark: v.dark, increasedContrast: v.increasedContrast)
            defer { host.close() }
            try await record(host, "sheet-\(screen)", v)
        }
    }

    @Test func everyScreen() async throws {
        AXTree.enableInProcess()
        let songs = FileManager.default.temporaryDirectory.appending(path: "fs-catalogue-\(UUID().uuidString)", directoryHint: .isDirectory)
        setenv("SCRIBE_SONGS", songs.path, 1)
        defer { try? FileManager.default.removeItem(at: songs) }

        try await window("home-empty", model: Self.model()) { HomeView() }
        try await window("home-offline", model: Self.model(connection: .offline)) { HomeView() }
        let bass = try Self.song("bass-line-marks", title: "Bass line")
        _ = try Self.song("guitar-line", title: "Guitar riff")
        let full = Self.model()
        full.refresh()
        try await window("home-songs", model: full) { HomeView() }

        let src = PendingSource(audioURL: Self.fixture("bass-line/tab.json"), title: "Riff", name: "Riff.m4a")
        try await window("what-is-this", model: full) { WhatIsThisView(source: src) }
        let job = TabJob(source: src, recording: .song, request: TranscriptionRequest(audioURL: src.audioURL, profile: "tab"),
                         service: FixtureService(directory: Self.fixture("bass-line"), stepDelay: 0, outputName: "tab"))
        job.progress = TranscriptionProgress(stage: .transcribing, fraction: 0.42, etaSeconds: nil)
        full.jobs[job.id] = job
        try await window("transcribing", model: full) { TranscribingView(jobID: job.id) }
        try await window("check-the-song", model: full) { CheckTheSongView(song: bass) }
        try await window("tab", model: full, shows: { nodes in
            // the tab's summary is there once the page is engraved
            nodes.contains { $0.label.hasPrefix("Bass line.") } ? nil : "the engraved tab"
        }) { TabScreen(song: bass) }
        try await window("problem", model: full) { ProblemView(problem: .sheetMusic) }

        try await sheet("settings", model: full) { SettingsView() }
        try await sheet("first-run", model: Self.model()) { FirstRunView() }
        try await window("your-instrument", model: full) { YourInstrumentView(fromSettings: true) }
    }
}
#endif
